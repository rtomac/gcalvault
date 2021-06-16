import os
import re
import json
from pathlib import Path
import shutil
import glob
import pytest
from unittest.mock import MagicMock, patch
from gcalvault import Gcalvault, GcalvaultError
from gcalvault.gcalvault import GoogleOAuth2, GoogleApis
from git import Repo


# Note: Tests are meant to run in a container (see `make test`), so
# tests here are written against the actual file system, including
# git functionalities. All HTTP requests out to Google APIs are
# mocked, however.


dirname = os.path.dirname(__file__)
data_dir_path = os.path.join(dirname, "data")


@pytest.mark.parametrize(
    "args", [
        ["--unknown"], # bad long option
        ["-u"], # bad short option
        ["badcommand", "foo.bar@gmail.com"], # bad command
        ["--export-only"], # valid option with no command
        ["noop"], # valid command with no user
        ["noop", "foo.bar@gmail.com", "--ignore-role"], # opt requiring value not provided
    ])
def test_invalid_args(args):
    gc = Gcalvault()
    with pytest.raises(GcalvaultError):
        gc.run(args)

@pytest.mark.parametrize(
    "args", [
        ["--help"],
        ["-h"],
        [],
    ])
def test_help(capsys, args):
    gc = Gcalvault()
    gc.run(args)

    captured = capsys.readouterr()
    assert "Usage:" in captured.out
    assert "Options:" in captured.out

@pytest.mark.parametrize(
    "args", [
        ["--version"],
    ])
def test_version(capsys, args):
    gc = Gcalvault()
    gc.run(args)

    # Success if output casts to a float w/o throwing exception
    captured = capsys.readouterr()
    assert re.match(r"^\d\.\d(\.\d)?$", captured.out.strip())

@pytest.mark.parametrize(
    "args, expected_properties", [
        (["noop", "foo.bar@gmail.com"],
            {'command': "noop", 'user': "foo.bar@gmail.com", 'includes': []}),
        (["noop", "foo.bar@gmail.com", "foo.bar@gmail.com", "foo.baz@gmail.com"],
            {'command': "noop", 'user': "foo.bar@gmail.com", 'includes': ["foo.bar@gmail.com", "foo.baz@gmail.com"]}),
        (["noop", "foo.bar@gmail.com", "--export-only"],
            {'export_only': True}),
        (["noop", "foo.bar@gmail.com", "-e"],
            {'export_only': True}),
        (["noop", "foo.bar@gmail.com", "--ignore-role", "reader"],
            {'ignore_roles': ["reader"]}),
        (["noop", "foo.bar@gmail.com", "-i", "reader", "-i", "writer"],
            {'ignore_roles': ["reader", "writer"]}),
        (["noop", "foo.bar@gmail.com", "-c", "/tmp/conf"],
            {'conf_dir': "/tmp/conf"}),
        (["noop", "foo.bar@gmail.com", "--conf-dir", "/tmp/conf"],
            {'conf_dir': "/tmp/conf"}),
        (["noop", "foo.bar@gmail.com", "-o", "/tmp/output"],
            {'output_dir': "/tmp/output"}),
        (["noop", "foo.bar@gmail.com", "--output-dir", "/tmp/output"],
            {'output_dir': "/tmp/output"}),
        (["noop", "foo.bar@gmail.com", "--vault-dir", "/tmp/output"],
            {'output_dir': "/tmp/output"}),
        (["noop", "foo.bar@gmail.com", "--client-id", "0123456789abcdef"],
            {'client_id': "0123456789abcdef"}),
        (["noop", "foo.bar@gmail.com", "--client-secret", "!@#$%^&*"],
            {'client_secret': "!@#$%^&*"}),
    ])
def test_arg_parsing(args, expected_properties):
    gc = Gcalvault()
    gc.run(args)

    for key, expected_value in expected_properties.items():
        actual_value = getattr(gc, key)
        assert actual_value == expected_value

def test_creates_dirs():
    (conf_dir, output_dir) =  _setup_dirs()
    gc = Gcalvault()
    gc.run(["noop", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    assert conf_dir.is_dir() and conf_dir.exists()
    assert output_dir.is_dir() and output_dir.exists()

def test_sync():
    (conf_dir, output_dir) =  _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    expected_files = [
        "foo.bar@gmail.com.ics",
        "foo.baz@gmail.com.ics",
        "family123456789@group.calendar.google.com.ics",
        "en.usa#holiday@group.v.calendar.google.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files)

def test_sync_with_include():
    (conf_dir, output_dir) =  _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    gc.run(["sync", "foo.bar@gmail.com", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    expected_files = [
        "foo.bar@gmail.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files)

def test_sync_with_multi_include():
    (conf_dir, output_dir) =  _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    gc.run(["sync", "foo.bar@gmail.com", "foo.bar@gmail.com", "foo.baz@gmail.com", "-c", conf_dir, "-o", output_dir])

    expected_files = [
        "foo.bar@gmail.com.ics",
        "foo.baz@gmail.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files)

def test_sync_with_include_not_found():
    (conf_dir, output_dir) =  _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    with pytest.raises(GcalvaultError):
        gc.run(["sync", "foo.bar@gmail.com", "john.doe@gmail.com", "-c", conf_dir, "-o", output_dir])

def test_sync_with_ignore():
    (conf_dir, output_dir) =  _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir, "-i", "reader"])

    expected_files = [
        "foo.bar@gmail.com.ics",
        "family123456789@group.calendar.google.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files)

def test_sync_with_multi_ignore():
    (conf_dir, output_dir) =  _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir, "-i", "reader", "-i", "writer"])

    expected_files = [
        "foo.bar@gmail.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files)

def test_sync_new_authorization_doesnt_match():
    (conf_dir, output_dir) =  _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(new_authorization=True, email="john.doe@gmail.com"),
        google_apis=_get_google_apis_mock(empty_cal_list=True))
    with pytest.raises(GcalvaultError):
        gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

def test_sync_new_authorization_does_match():
    (conf_dir, output_dir) =  _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(new_authorization=True, email="foo.bar@gmail.com"),
        google_apis=_get_google_apis_mock(empty_cal_list=True))
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

def test_sync_export_only():
    (conf_dir, output_dir) =  _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    gc.run(["sync", "foo.bar@gmail.com", "foo.bar@gmail.com", "-e", "-c", conf_dir, "-o", output_dir])

    assert not os.path.exists(os.path.join(output_dir, ".git"))
    assert os.path.exists(os.path.join(output_dir, "foo.bar@gmail.com.ics"))

def test_new_git_repo():
    (conf_dir, output_dir) =  _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock(empty_cal_list=True))
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    assert os.path.exists(os.path.join(output_dir, ".git"))
    assert len(_get_git_commits(output_dir)) == 1 # initial commit

def test_git_commits():
    (conf_dir, output_dir) =  _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    assert os.path.exists(os.path.join(output_dir, ".git"))
    assert len(_get_git_commits(output_dir)) == 2 # initial commit + 1
    assert _get_git_commits(output_dir)[0].stats.total['files'] == 4 # ics files


def _get_google_oauth2_mock(new_authorization=False, email="foo.bar@gmail.com"):
    google_oauth2 = GoogleOAuth2()

    credentials = MagicMock(token="phony")
    google_oauth2.get_credentials = MagicMock(return_value=(credentials, new_authorization))

    user_info = {"email": email}
    google_oauth2.request_user_info = MagicMock(return_value=user_info)

    return google_oauth2

def _get_google_apis_mock(empty_cal_list=False):
    def request_cal_as_ical(cal_id, credentials):
        return _read_data_file(cal_id + ".ics")

    google_apis = GoogleApis()

    cal_list_file = "cal_list_empty.json" if empty_cal_list else "cal_list.json"
    google_apis.request_cal_list = MagicMock(return_value=_read_data_file_json(cal_list_file))
    
    google_apis.request_cal_as_ical = request_cal_as_ical

    return google_apis

def _assert_ics_files_match(output_dir, expected_files):
    actual_files = [os.path.basename(f) for f in glob.glob(os.path.join(output_dir, "*.ics"))]
    assert len(expected_files) == len(actual_files)
    for file_name in expected_files:
        assert file_name in actual_files
        assert _read_file(output_dir, file_name) == _read_data_file(file_name)

def _setup_dirs():
    conf_dir = Path("/tmp/conf")
    output_dir = Path("/tmp/output")

    for dir in [conf_dir, output_dir]:
        if dir.exists(): shutil.rmtree(dir)

    return (conf_dir.resolve(), output_dir.resolve())

def _read_data_file(file_name):
    return _read_file(data_dir_path, file_name)

def _read_data_file_json(file_name):
    return json.loads(_read_data_file(file_name))

def _read_file(dir_path, file_name):
    return Path(dir_path, file_name).read_text()

def _get_git_commits(output_dir):
    repo = Repo(output_dir)
    return list(repo.iter_commits('master', max_count=10))
