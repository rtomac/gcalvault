# Overview

Gcalvault is a command-line utility which exports all of a user's Google Calendars to iCal/ICS format for backup (or portability).

Features:
- Automatically discovers all calendars visible the user
- Downloads them in iCal/ICS format and saves them to disk for archival
- Optionally manages version history for each calendar in an on-disk "vault" (a git repo under the covers)
- Can be run via Docker image (multi-arch) or installed directly as a Python package with command-line interface

# How it works

- Uses Google's [Identity Provider](https://developers.google.com/identity/protocols/oauth2) to authenticate (via OAuth2/OIDC)
- Uses Google's [Calendar API](https://developers.google.com/calendar/api/v3/reference) to discover a user's calendars
- Uses Google's [CalDAV endpoints](https://developers.google.com/calendar/caldav/v2/guide) to download iCal/ICS calendars
- Uses [GitPython](https://gitpython.readthedocs.io) to manage local git repo for version history under the covers

# Usage

Some example commands...

Sync all calendars for `foo.bar@gmail.com` user:
```
gcalvault sync foo.bar@gmail.com
```

Sync one specific calendar:
```
gcalvault sync foo.bar@gmail.com family123@group.calendar.google.com
```

Sync only "writable" calendars:
```
gcalvault sync foo.bar@gmail.com --ignore-role reader
```

Simply export calendars, do not save version history:
```
gcalvault sync foo.bar@gmail.com --export-only
```

See the [CLI help](https://github.com/rtomac/gcalvault/blob/main/src/USAGE.txt) for full usage and other notes.

# Requirements

- Python 3.9+

# Installation

## Via PyPi

```
pip install gcalvault
gcalvault sync foo.bar@gmail.com
```

## Via Docker

```
docker run -it --rm \
    -v ${HOME}/.gcalvault:/root/.gcalvault \
    -v ${PWD}/gcalvault:/root/gcalvault \
    rtomac/gcalvault sync foo.bar@gmail.com
```

# OAuth2 authentication

The CLI initiates an OAuth2 authentication the first time it is run (interactive), and then uses refresh tokens for subsequent runs (headless).

When you use Gcalvault in its default configuration, you are initiating the OAuth2 flow with Google using Gcalvault's client ID. There is nothing inherently insecure about this, since the application is running locally and therefore only *you* will have access to the data it reads from Google.

That said, it is recommended to create your own client ID through the [Google API Console](https://console.developers.google.com/), since the shared client ID may be used by others and subject to limits which may cause unpredictable failures.

[rclone](https://rclone.org) has a good write-up on [making your own client ID](https://rclone.org/drive/#making-your-own-client-id).

You can provide your client ID and secret to gcalvault as follows:
```
gcalvault sync foo.bar@gmail.com --client-id my_client_id --client-secret my_client_secret
```

# Development

Source repository:<br>
http://github.com/rtomac/gcalvault

## Install dependencies and run locally
```
pip install virtualenv
make devenv
. ./.devenv/bin/activate
gcalvault --help
```

## Run tests
```
pytest
```

## Build distribution
```
make dist
```

## Build Docker image
```
make docker-build
```

## Run via Docker image
```
make docker-run user=foo.bar@gmail.com
```

## Release to PyPi and Docker Hub
```
make release
```

See targets and variables in [Makefile](https://github.com/rtomac/gcalvault/blob/main/Makefile) for more options.

# License

MIT License
