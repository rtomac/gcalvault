import os
import re
import json
from pathlib import Path
import shutil
import glob
import pytest
from unittest.mock import MagicMock
from git import Repo
from gcalvault import Gcalvault, GcalvaultError
from gcalvault.gcalvault import GoogleOAuth2, GoogleApis

# Note: Tests are meant to run in a container (see `make test`), so
# tests here are written against the actual file system, including
# git functionalities. All HTTP requests out to Google APIs are
# mocked, however.


dirname = os.path.dirname(__file__)
data_dir_path = os.path.join(dirname, "data")


@pytest.mark.parametrize(
    "args", [
        ["--unknown"],  # bad long option
        ["-u"],  # bad short option
        ["badcommand", "foo.bar@gmail.com"],  # bad command
        ["--export-only"],  # valid option with no command
        ["noop"],  # valid command with no user
        ["noop", "foo.bar@gmail.com", "--ignore-role"],  # opt requiring value not provided
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
    assert re.match(r"^\d+\.\d+(\.\d+)?$", captured.out.strip())


@pytest.mark.parametrize(
    "args, expected_properties", [
        (["noop", "foo.bar@gmail.com"],
            {'command': "noop", 'user': "foo.bar@gmail.com", 'includes': []}),
        (["noop", "foo.bar@gmail.com", "foo.bar@gmail.com", "foo.baz@gmail.com"],
            {'command': "noop", 'user': "foo.bar@gmail.com", 'includes': ["foo.bar@gmail.com", "foo.baz@gmail.com"]}),
        (["noop", "foo.bar@gmail.com", "-e"],
            {'export_only': True}),
        (["noop", "foo.bar@gmail.com", "--export-only"],
            {'export_only': True}),
        (["noop", "foo.bar@gmail.com", "-f"],
            {'clean': True}),
        (["noop", "foo.bar@gmail.com", "--clean"],
            {'clean': True}),
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
    (conf_dir, output_dir) = _setup_dirs()
    gc = Gcalvault()
    gc.run(["noop", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    assert conf_dir.is_dir() and conf_dir.exists()
    assert output_dir.is_dir() and output_dir.exists()


def test_sync():
    (conf_dir, output_dir) = _setup_dirs()

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
    (conf_dir, output_dir) = _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    gc.run(["sync", "foo.bar@gmail.com", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    expected_files = [
        "foo.bar@gmail.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files)


def test_sync_with_multi_include():
    (conf_dir, output_dir) = _setup_dirs()

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
    (conf_dir, output_dir) = _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    with pytest.raises(GcalvaultError):
        gc.run(["sync", "foo.bar@gmail.com", "john.doe@gmail.com", "-c", conf_dir, "-o", output_dir])


def test_sync_with_ignore():
    (conf_dir, output_dir) = _setup_dirs()

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
    (conf_dir, output_dir) = _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir, "-i", "reader", "-i", "writer"])

    expected_files = [
        "foo.bar@gmail.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files)


def test_clean():
    (conf_dir, output_dir) = _setup_dirs()

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

    _assert_git_repo_state(output_dir, commit_count=2, last_commit_file_count=4)  # initial commit + 1, 4 ics files

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock(cal_list='less'))
    gc.run(["sync", "foo.bar@gmail.com", "--clean", "-c", conf_dir, "-o", output_dir])
    expected_files_after = [
        "foo.bar@gmail.com.ics",
        "family123456789@group.calendar.google.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files_after)

    _assert_git_repo_state(output_dir, commit_count=3, last_commit_file_count=2)  # 1 additional commit, 2 file removals


def test_without_clean():
    (conf_dir, output_dir) = _setup_dirs()

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

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock(cal_list='less'))
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    expected_files_after = expected_files
    _assert_ics_files_match(output_dir, expected_files_after)


def test_etags_none_changed():
    (conf_dir, output_dir) = _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock(cal_list="less"))
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    expected_files = [
        "foo.bar@gmail.com.ics",
        "family123456789@group.calendar.google.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files)

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock(cal_list="less", cal_files={}, cal_files_as_allowlist=True))
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    expected_files_after = expected_files
    _assert_ics_files_match(output_dir, expected_files_after)


def test_etags_none_changed_but_files_missing():
    (conf_dir, output_dir) = _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock(cal_list="less"))
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    expected_files = [
        "foo.bar@gmail.com.ics",
        "family123456789@group.calendar.google.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files)

    os.remove(os.path.join(output_dir, "family123456789@group.calendar.google.com.ics"))

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock(
            cal_list="less",
            cal_files={"family123456789@group.calendar.google.com": None},
            cal_files_as_allowlist=True))
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    expected_files_after = expected_files
    _assert_ics_files_match(output_dir, expected_files_after)


def test_etags_some_changed():
    (conf_dir, output_dir) = _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock(cal_list="less"))
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    expected_files = [
        "foo.bar@gmail.com.ics",
        "family123456789@group.calendar.google.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files)

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock(
            cal_list="less_alt_etag",
            cal_files={"foo.bar@gmail.com": "foo.bar@gmail.com_alt.ics"},
            cal_files_as_allowlist=True))
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    expected_files_after = expected_files
    _assert_ics_files_match(output_dir, expected_files_after, check_file_content=False)
    _assert_ics_file_content_match(output_dir, "foo.bar@gmail.com.ics", "foo.bar@gmail.com_alt.ics")
    _assert_ics_file_content_match(output_dir, "family123456789@group.calendar.google.com.ics")


def test_etags_some_added():
    (conf_dir, output_dir) = _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock(cal_list="less"))
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    expected_files = [
        "foo.bar@gmail.com.ics",
        "family123456789@group.calendar.google.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files)

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock(
            cal_files={
                "foo.baz@gmail.com": None,
                "en.usa#holiday@group.v.calendar.google.com": None,
            },
            cal_files_as_allowlist=True))
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])
    expected_files_after = [
        "foo.bar@gmail.com.ics",
        "foo.baz@gmail.com.ics",
        "family123456789@group.calendar.google.com.ics",
        "en.usa#holiday@group.v.calendar.google.com.ics",
    ]
    _assert_ics_files_match(output_dir, expected_files_after)


def test_sync_export_only():
    (conf_dir, output_dir) = _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    gc.run(["sync", "foo.bar@gmail.com", "foo.bar@gmail.com", "-e", "-c", conf_dir, "-o", output_dir])

    _assert_git_repo_state(output_dir, repo_exists=False)
    assert os.path.exists(os.path.join(output_dir, "foo.bar@gmail.com.ics"))


def test_new_git_repo():
    (conf_dir, output_dir) = _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock(cal_list='empty'))
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    _assert_git_repo_state(output_dir, commit_count=1)  # initial commit


def test_git_commits():
    (conf_dir, output_dir) = _setup_dirs()

    gc = Gcalvault(
        google_oauth2=_get_google_oauth2_mock(),
        google_apis=_get_google_apis_mock())
    gc.run(["sync", "foo.bar@gmail.com", "-c", conf_dir, "-o", output_dir])

    _assert_git_repo_state(output_dir, commit_count=2, last_commit_file_count=4)  # initial commit + 1, 4 ics files


def _get_google_oauth2_mock(new_authorization=False, email="foo.bar@gmail.com"):
    google_oauth2 = GoogleOAuth2("gcalvault", "gcalvault authorize")

    credentials = MagicMock(token="phony")
    google_oauth2.get_credentials = MagicMock(return_value=(credentials, new_authorization))

    user_info = {"email": email}
    google_oauth2.request_user_info = MagicMock(return_value=user_info)

    return google_oauth2


def _get_google_apis_mock(cal_list=None, cal_files={}, cal_files_as_allowlist=False):
    google_apis = GoogleApis()

    def request_cal_list(credentials):
        cal_list_file = f"cal_list_{cal_list}.json" if cal_list else "cal_list.json"
        return _read_data_file_json(cal_list_file)
    google_apis.request_cal_list = request_cal_list

    def request_cal_as_ical(cal_id, credentials):
        if cal_files_as_allowlist:
            assert cal_id in cal_files
        cal_file = cal_files[cal_id] if cal_id in cal_files else None
        cal_file = cal_id + ".ics" if cal_file is None else cal_file
        return _read_data_file(cal_file)
    google_apis.request_cal_as_ical = request_cal_as_ical

    return google_apis


def _assert_ics_files_match(output_dir, expected_files, check_file_content=True):
    actual_files = [os.path.basename(f) for f in glob.glob(os.path.join(output_dir, "*.ics"))]
    assert len(expected_files) == len(actual_files)
    for file_name in expected_files:
        assert file_name in actual_files
        if check_file_content:
            _assert_ics_file_content_match(output_dir, file_name, file_name)


def _assert_ics_file_content_match(output_dir, output_file_name, data_file_name=None):
    data_file_name = data_file_name if data_file_name else output_file_name
    assert _read_file(output_dir, output_file_name) == _read_data_file(data_file_name)


def _setup_dirs():
    conf_dir = Path("/tmp/conf")
    output_dir = Path("/tmp/output")

    for dir in [conf_dir, output_dir]:
        if dir.exists():
            shutil.rmtree(dir)

    return (conf_dir.resolve(), output_dir.resolve())


def _read_data_file(file_name):
    return _read_file(data_dir_path, file_name)


def _read_data_file_json(file_name):
    return json.loads(_read_data_file(file_name))


def _read_file(dir_path, file_name):
    return Path(dir_path, file_name).read_text()


def _assert_git_repo_state(output_dir, repo_exists=True, commit_count=None, last_commit_file_count=None):
    assert os.path.exists(os.path.join(output_dir, ".git")) == repo_exists
    if commit_count is not None or last_commit_file_count is not None:
        repo = Repo(output_dir)
        commits = list(repo.iter_commits(rev=repo.head.reference, max_count=10))
        if commit_count is not None:
            assert len(commits) == commit_count
        if last_commit_file_count is not None:
            assert commits[0].stats.total['files'] == last_commit_file_count
