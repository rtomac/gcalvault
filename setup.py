import os
from setuptools import setup, find_packages
import pathlib


dirname = os.path.dirname(__file__)
version_file_path = os.path.join(dirname, "src", "VERSION.txt")


setup(
    name="gcalvault",
    version=pathlib.Path(version_file_path).read_text().strip(),
    description="Command-line utility which exports all of a user's Google Calendars to iCal/ICS format for backup (or portability)",
    url="http://github.com/rtomac/gcalvault",
    author="Ryan Tomac",
    author_email="ryan@tomacfamily.com",
    license="MIT",
    packages=["gcalvault"],
    package_dir={"gcalvault":"src"},
    package_data={"gcalvault":["*.txt"]},
    include_package_data=True,
    scripts=["bin/gcalvault"],
    python_requires=">=3.6",
    install_requires=[
        "pytest==6.*",
        "google-api-python-client==2.7.*",
        "google-auth-httplib2==0.1.*",
        "google-auth-oauthlib==0.4.*",
        "requests==2.25.*",
        "GitPython==3.1.*",
    ],
)
