import os
import glob
import requests
import urllib.parse
import pathlib
from getopt import gnu_getopt, GetoptError
from googleapiclient.discovery import build
from dotenv import load_dotenv

from .google_oauth2 import GoogleOAuth2
from .git_vault_repo import GitVaultRepo
from .etag_manager import ETagManager


# Note: OAuth2 auth code flow for "installed applications" assumes the client secret
# cannot actually be kept secret (must be embedded in application/source code).
# Access to user data must be consented by the user and [more importantly] the
# access & refresh tokens are stored locally with the user running the program.
DEFAULT_CLIENT_ID = "261805543927-7p1s5ee657kg0427vs2r1f90dins6hdd.apps.googleusercontent.com"
DEFAULT_CLIENT_SECRET = "pLKRSKrIIWw7K-CD1DWWV2_Y"
OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.readonly",
]

GOOGLE_CALDAV_URI_FORMAT = "https://apidata.googleusercontent.com/caldav/v2/{cal_id}/events"

COMMANDS = ['sync', 'login', 'authorize', 'noop']

load_dotenv()

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
        self.conf_dir = os.getenv("GCALVAULT_CONF_DIR", os.path.expanduser("~/.gcalvault"))
        self.output_dir = os.getenv("GCALVAULT_OUTPUT_DIR", os.path.join(os.getcwd(), 'gcalvault'))
        self.client_id = DEFAULT_CLIENT_ID
        self.client_secret = DEFAULT_CLIENT_SECRET

        self._repo = None
        self._google_oauth2 = google_oauth2 if google_oauth2 is not None else GoogleOAuth2(
            app_name="gcalvault",
            authorize_command="gcalvault authorize {email_addr}",
        )
        self._google_apis = google_apis if google_apis is not None else GoogleApis()

    def run(self, cli_args):
        if not self._parse_options(cli_args):
            return
        getattr(self, self.command)()

    def noop(self):
        self._ensure_dirs()
        pass

    def sync(self):
        self._ensure_dirs()

        (credentials, _) = self._google_oauth2.get_credentials(
            self._token_file_path(), self.client_id, self.client_secret, OAUTH_SCOPES, self.user)

        if not self.export_only:
            self._repo = GitVaultRepo("gcalvault", self.version(), self.output_dir, [".ics"])

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

    def login(self):
        self._ensure_dirs()
        self._google_oauth2.authz_and_save_token(
            self._token_file_path(), self.client_id, self.client_secret, OAUTH_SCOPES, self.user)

    def authorize(self):
        self._ensure_dirs()
        self._google_oauth2.authz_and_export_token(
            self.client_id, self.client_secret, OAUTH_SCOPES, self.user)

    def usage(self):
        return pathlib.Path(usage_file_path).read_text().strip()

    def version(self):
        return pathlib.Path(version_file_path).read_text().strip()

    def _parse_options(self, cli_args):
        show_help = show_version = False

        try:
            (opts, pos_args) = gnu_getopt(
                cli_args,
                'efi:c:o:h',
                ['export-only', 'clean', 'ignore-role=',
                    'conf-dir=', 'output-dir=', 'vault-dir=',
                    'client-id=', 'client-secret=',
                    'help', 'version', ]
            )
        except GetoptError as e:
            raise GcalvaultError(e) from e

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
                show_help = True
            elif opt in ['--version']:
                show_version = True

        if len(opts) == 0 and len(pos_args) == 0:
            show_help = True

        if show_help:
            print(self.usage())
            return False
        if show_version:
            print(self.version())
            return False

        if len(pos_args) >= 1:
            self.command = pos_args[0]
        if len(pos_args) >= 2:
            self.user = pos_args[1].lower().strip()
        for arg in pos_args[2:]:
            self.includes.append(arg.lower())

        if self.command is None:
            raise GcalvaultError("<command> argument is required")
        if self.command not in COMMANDS:
            raise GcalvaultError("Invalid <command> argument")
        if self.user is None:
            raise GcalvaultError("<user> argument is required")

        return True

    def _ensure_dirs(self):
        for dir in [self.conf_dir, self.output_dir]:
            pathlib.Path(dir).mkdir(parents=True, exist_ok=True)
    
    def _token_file_path(self):
        return os.path.join(self.conf_dir, f"{self.user}.token.json")

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


class GcalvaultError(ValueError):
    pass


class Calendar():

    def __init__(self, id, name, etag, access_role):
        self.id = id
        self.name = name
        self.etag = etag
        self.access_role = access_role

        self.file_name = f"{self.id.strip().lower()}.ics"


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
