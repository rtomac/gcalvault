import os
from setuptools import setup, find_packages
import pathlib


dirname = os.path.dirname(__file__)
version_file_path = os.path.join(dirname, "src", "VERSION.txt")
readme_file_path = os.path.join(dirname, "README.md")


setup(
    name="gcalvault",
    version=pathlib.Path(version_file_path).read_text().strip(),
    description="Command-line utility which exports all of a user's Google Calendars to iCal/ICS format for backup (or portability)",
    long_description=pathlib.Path(readme_file_path).read_text(),
    long_description_content_type="text/markdown",
    keywords = ["Google Calendar", "gcal", "backup", "export", "iCal", "ICS", "CalDav"],
    url="http://github.com/rtomac/gcalvault",
    author="Ryan Tomac",
    author_email="rtomac@gmail.com",
    license="MIT",
    packages=["gcalvault"],
    package_dir={"gcalvault":"src"},
    package_data={"gcalvault":["*.txt"]},
    include_package_data=True,
    scripts=["bin/gcalvault"],
    python_requires=">=3.6",
    install_requires=[
        "google-api-python-client==2.7.*",
        "google-auth-httplib2==0.1.*",
        "google-auth-oauthlib==0.4.*",
        "requests==2.25.*",
        "GitPython==3.1.*",
    ],
    extras_require={
        "test": [
            "pytest==6.*",
        ],
        "release": [
            "twine",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "Natural Language :: English",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Topic :: System :: Archiving :: Backup",
    ],
)
