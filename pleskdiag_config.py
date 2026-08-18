"""Configuration loading for Webcore PleskDiag."""
from __future__ import print_function

import configparser
import os
from pathlib import Path

DEFAULT_CONFIG = "/etc/pleskdiag/pleskdiag.conf"

DEFAULTS = {
    "general": {
        "vhost_system_dir": "/var/www/vhosts/system",
        "archive_dir": "/var/log/pleskdiag",
    },
    "sampling": {
        "seconds": "10",
        "interval": "2",
    },
    "apache": {
        "status_url": "http://127.0.0.1:7080/pleskdiag-server-status",
    },
    "publish": {
        "enabled": "true",
        "repo_dir": "/opt/webcore-diagnostics",
    },
}


def config_path():
    return Path(os.environ.get("PLESKDIAG_CONFIG", DEFAULT_CONFIG))


def load_config(path=None):
    parser = configparser.ConfigParser()
    parser.read_dict(DEFAULTS)
    target = Path(path) if path else config_path()
    if target.is_file():
        parser.read(str(target))
    parser._pleskdiag_path = str(target)
    parser._pleskdiag_exists = target.is_file()
    return parser
