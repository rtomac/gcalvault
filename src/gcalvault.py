#!/usr/bin/env python3

from copy import error
import os
from collections import namedtuple
import glob
import requests
import urllib.parse
import pathlib
import getopt
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from git import Repo, exc


GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_CERTS_URI = "https://www.googleapis.com/oauth2/v1/certs"
SCOPES = ['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/calendar.readonly']
GOOGLE_CALDAV_URI_FORMAT = "https://apidata.googleusercontent.com/caldav/v2/{cal_id}/events"

# Note: OAuth2 auth code flow for "installed applications" assumes the client secret
# cannot actually be kept secret (must be embedded in application/source code).
# Access to user data must be consented by the user and [more importantly] the
# access & refresh tokens are stored locally with the user running the program.
DEFAULT_CLIENT_ID = "261805543927-7p1s5ee657kg0427vs2r1f90dins6hdd.apps.googleusercontent.com"
DEFAULT_CLIENT_SECRET = "pLKRSKrIIWw7K-CD1DWWV2_Y"

COMMANDS = ['sync', 'noop']

dirname = os.path.dirname(__file__)
usage_file_path = os.path.join(dirname, "USAGE.txt")
version_file_path = os.path.join(dirname, "VERSION.txt")


class Gcalvault:

    def __init__(self, google_oauth2=None, google_apis=None):
        self.command = None
        self.user = None
        self.includes = []
        self.export_only = False
        self.clean = False
        self.ignore_roles = []
        self.conf_dir = os.path.expanduser("~/.gcalvault")
        self.output_dir = os.getcwd()
        self.client_id = DEFAULT_CLIENT_ID
        self.client_secret = DEFAULT_CLIENT_SECRET
        self.show_help = self.show_version = False

        self._repo = None
        self._google_oauth2 = google_oauth2 if google_oauth2 is not None else GoogleOAuth2()
        self._google_apis = google_apis if google_apis is not None else GoogleApis()

    def run(self, cli_args):
        if cli_args is not None:
            self._parse_options(cli_args)

        if self.show_help or self.show_version:
            file_path = version_file_path if self.show_version else usage_file_path
            print(pathlib.Path(file_path).read_text().strip())
            return
        
        for dir in [self.conf_dir, self.output_dir]:
            pathlib.Path(dir).mkdir(parents=True, exist_ok=True)
        
        if self.command == "noop":
            return

        credentials = self._get_oauth2_credentials()
        getattr(self, '_' + self.command)(credentials)

    def _sync(self, credentials):
        if not self.export_only:
            self._repo = GitVaultRepo("gcalvault", self.output_dir, [".ics"])
        
        calendars = self._get_calendars(credentials)
        
        if self.ignore_roles:
            calendars = [cal for cal in calendars if cal.access_role not in self.ignore_roles]

        if self.includes:
            calendars = [cal for cal in calendars if cal.id in self.includes]
        
        cal_ids = [cal.id for cal in calendars]
        for include in self.includes:
            if include not in cal_ids:
                raise GcalvaultError(f"Specified calendar '{include}' was not found")
        
        if self.clean:
            self._clean_output_dir(calendars)

        self._dl_and_save_calendars(calendars, credentials)

        if self._repo:
            self._repo.commit("gcalvault sync")

    def _parse_options(self, cli_args):
        try:
            (opts, pos_args) = getopt.gnu_getopt(
                cli_args,
                'efi:c:o:h',
                ['export-only', 'clean', 'ignore-role=',
                    'conf-dir=', 'output-dir=', 'vault-dir=',
                    'client-id=', 'client-secret=',
                    'help', 'version',]
            )
        except getopt.GetoptError as e:
            raise GcalvaultError(e, exit_code=2)

        for opt, val in opts:
            if opt in ['-e', '--export-only']:
                self.export_only = True
            elif opt in ['-f', '--clean']:
                self.clean = True
            elif opt in ['-i', '--ignore-role']:
                self.ignore_roles.append(val.lower())
            elif opt in ['-c', '--conf-dir']:
                self.conf_dir = val
            elif opt in ['-o', '--output-dir', '--vault-dir']:
                self.output_dir = val
            elif opt in ['--client-id']:
                self.client_id = val
            elif opt in ['--client-secret']:
                self.client_secret = val
            elif opt in ['-h', '--help']:
                self.show_help = True
            elif opt in ['--version']:
                self.show_version = True

        if len(pos_args) >= 1:
            self.command = pos_args[0]
        if len(pos_args) >= 2:
            self.user = pos_args[1].lower().strip()
        for arg in pos_args[2:]:
            self.includes.append(arg.lower())

        if len(opts) == 0 and len(pos_args) == 0:
            self.show_help = True
        
        if self.show_help or self.show_version:
            return

        if self.command is None:
            raise GcalvaultError("<command> argument is required", exit_code=2)
        if self.command not in COMMANDS:
            raise GcalvaultError("Invalid <command> argument", exit_code=2)
        if self.user is None:
            raise GcalvaultError("<user> argument is required", exit_code=2)

    def _get_oauth2_credentials(self):
        token_file_path = os.path.join(self.conf_dir, f"{self.user}.token.json")

        (credentials, new_authorization) = self._google_oauth2 \
            .get_credentials(token_file_path, self.client_id, self.client_secret, self.user)
        
        if new_authorization:
            user_info = self._google_oauth2.request_user_info(credentials)
            profile_email = user_info['email'].lower().strip()
            if self.user != profile_email:
                raise GcalvaultError(f"Authenticated user - {profile_email} - was different than <user> argument specified")
        
        return credentials

    def _get_calendars(self, credentials):
        calendars = []
        calendar_list = self._google_apis.request_cal_list(credentials)
        for item in calendar_list['items']:
            calendars.append(
                Calendar(item['id'], item['summary'], item['etag'], item['accessRole']))
        return calendars

    def _clean_output_dir(self, calendars):
        cal_file_names = [cal.file_name for cal in calendars]
        file_names_on_disk = [os.path.basename(file).lower() for file in glob.glob(os.path.join(self.output_dir, "*.ics"))]
        for file_name_on_disk in file_names_on_disk:
            if file_name_on_disk not in cal_file_names:
                os.remove(os.path.join(self.output_dir, file_name_on_disk))
                if self._repo:
                    self._repo.remove_file(file_name_on_disk)
                print(f"Removed file '{file_name_on_disk}'")
    
    def _dl_and_save_calendars(self, calendars, credentials):
        etags = ETagManager(self.conf_dir)
        for calendar in calendars:
            self._dl_and_save_calendar(calendar, credentials, etags)
    
    def _dl_and_save_calendar(self, calendar, credentials, etags):
        cal_file_path = os.path.join(self.output_dir, calendar.file_name)
        
        etag_changed = etags.test_for_change_and_save(calendar.id, calendar.etag)
        if os.path.exists(cal_file_path) and not etag_changed:
            print(f"Calendar '{calendar.name}' is up to date")
            return

        print(f"Downloading calendar '{calendar.name}'")
        ical = self._google_apis.request_cal_as_ical(calendar.id, credentials)
        
        with open(cal_file_path, 'w') as file:
            file.write(ical)
        print(f"Saved calendar '{calendar.id}'")

        if self._repo:
            self._repo.add_file(calendar.file_name)


class Calendar():

    def __init__(self, id, name, etag, access_role):
        self.id = id
        self.name = name
        self.etag = etag
        self.access_role = access_role

        self.file_name = f"{self.id.strip().lower()}.ics"


class GcalvaultError(Exception):

    def __init__(self, message, exit_code=1):
        self.message = message
        self.exit_code = exit_code


class GitVaultRepo():

    def __init__(self, name, dir_path, extensions):
        self._name = name
        self._repo = None
        try:
            self._repo = Repo(dir_path)
        except exc.InvalidGitRepositoryError:
            self._repo = Repo.init(dir_path)
            self._add_gitignore(extensions)
            print(f"Created {self._name} repository")
    
    def add_file(self, file_name):
        self._repo.index.add(file_name)
    
    def remove_file(self, file_name):
        self._repo.index.remove([file_name], working_tree=True)
    
    def commit(self, message):
        changes = self._repo.index.diff(self._repo.head.commit)
        if (changes):
            self._repo.index.commit(message)
            print(f"Committed {len(changes)} revision(s) to {self._name} repository:")
            for change in changes:
                print(f"- {change.a_path}")
        else:
            print(f"No revisions to commit to {self._name} repository")
    
    def _add_gitignore(self, extensions):
        gitignore_path = os.path.join(self._repo.working_dir, ".gitignore")
        with open(gitignore_path, 'w') as file:
            print('*', file=file)
            print('!.gitignore', file=file)
            for ext in extensions:
                print(f'!*{ext}', file=file)
        self._repo.index.add('.gitignore')
        self._repo.index.commit("Add .gitignore")


class GoogleOAuth2():

    def get_credentials(self, token_file_path, client_id, client_secret, login_hint):
        credentials = None
        new_authorization = False

        if os.path.exists(token_file_path):
            credentials = Credentials.from_authorized_user_file(token_file_path, SCOPES)

        if not credentials or not credentials.valid:

            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_config(
                    {
                        "installed": {
                            "auth_uri": GOOGLE_AUTH_URI,
                            "token_uri": GOOGLE_TOKEN_URI,
                            "auth_provider_x509_cert_url": GOOGLE_AUTH_CERTS_URI,
                            "client_id": client_id,
                            "client_secret": client_secret
                        }
                    },
                    scopes=SCOPES)
                credentials = flow.run_console(login_hint=login_hint)
                new_authorization = True

            with open(token_file_path, 'w') as token:
                token.write(credentials.to_json())

        return (credentials, new_authorization)
    
    def request_user_info(self, credentials):
        with build('oauth2', 'v2', credentials=credentials) as service:
            return service.userinfo().get().execute()


class GoogleApis():
    
    def request_cal_list(self, credentials):
        with build('calendar', 'v3', credentials=credentials) as service:
            return service.calendarList().list().execute()

    def request_cal_as_ical(self, cal_id, credentials):
        url = GOOGLE_CALDAV_URI_FORMAT.format(cal_id=urllib.parse.quote(cal_id))
        return self._request_with_token(url, credentials).text

    def _request_with_token(self, url, credentials, raise_for_status=True):
        headers = {'Authorization': f"Bearer {credentials.token}"}
        response = requests.get(url, headers=headers)
        if raise_for_status:
            response.raise_for_status()
        return response


class ETagManager():

    def __init__(self, conf_dir):
        self._etag_cache_file_path = os.path.join(conf_dir, ".etags")
        self._cache = self._read_cache_file()

    def test_for_change_and_save(self, object_name, etag):
        key = "_".join(object_name.strip().lower().split())
        value = "_".join(etag.strip().strip('"').split())

        if key in self._cache and self._cache[key] == value:
            return False

        self._cache[key] = value
        self._write_cache_file()
        return True

    def _read_cache_file(self):
        cache = {}
        if os.path.exists(self._etag_cache_file_path):
            with open(self._etag_cache_file_path, 'r') as file:
                for line in file:
                    (key, value) = line.split()
                    cache[key] = value
        return cache

    def _write_cache_file(self):
        with open(self._etag_cache_file_path, 'w') as file:
            for key in self._cache:
                value = self._cache[key]
                print(f"{key}\t{value}", file=file)
