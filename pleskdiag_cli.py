#!/usr/bin/env python3
"""Portable launcher for the Webcore PleskDiag collector."""
from __future__ import print_function

import importlib.util
import os
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pleskdiag_config

BASE_DIR = Path(__file__).resolve().parent
CORE_PATH = BASE_DIR / "pleskdiag"


def _load_core():
    loader = SourceFileLoader("pleskdiag_core", str(CORE_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def _value(config, section, option, default, kind="str"):
    try:
        if kind == "int":
            return config.getint(section, option)
        if kind == "bool":
            return config.getboolean(section, option)
        return config.get(section, option)
    except Exception:
        return default


def _configure_core(core, config):
    vhost_root = Path(_value(config, "general", "vhost_system_dir", "/var/www/vhosts/system"))
    sample_seconds = _value(config, "sampling", "seconds", 10, "int")
    sample_interval = _value(config, "sampling", "interval", 2, "int")
    status_url = _value(config, "apache", "status_url",
                        "http://127.0.0.1:7080/pleskdiag-server-status")

    core.SAMPLE_SECONDS = sample_seconds
    core.SAMPLE_INTERVAL = sample_interval
    core.APACHE_STATUS_URL = status_url

    def configured_domains():
        out = []
        if not vhost_root.is_dir():
            return out
        for entry in sorted(vhost_root.iterdir(), key=lambda item: item.name):
            if not entry.is_dir():
                continue
            logdir = entry / "logs"
            out.append({
                "domain": entry.name,
                "http_log": core.choose_log(logdir, ["proxy_access_log", "access_log"]),
                "https_log": core.choose_log(logdir, ["proxy_access_ssl_log", "access_ssl_log"]),
            })
        return out

    core.domains = configured_domains

    original_sample_runtime = core.sample_runtime

    def configured_sample_runtime(names, seconds=None, interval=None):
        return original_sample_runtime(
            names,
            sample_seconds if seconds is None else seconds,
            sample_interval if interval is None else interval,
        )

    core.sample_runtime = configured_sample_runtime

    core_has_db = getattr(core, "pleskdiag_db", None) is not None
    if not core_has_db:
        try:
            import pleskdiag_db
        except ImportError:
            pleskdiag_db = None

        if pleskdiag_db:
            original_snapshot = core.snapshot
            original_report = core.report

            def configured_snapshot(minutes):
                db_sampler = pleskdiag_db.MariaDBSampler()
                data = original_snapshot(minutes)
                data["mariadb"] = db_sampler.finish()
                return data

            def configured_report(data):
                original_report(data)
                print(pleskdiag_db.report(
                    data.get("mariadb", {}),
                    int(data.get("sample_seconds", sample_seconds) /
                        float(data.get("sample_interval", sample_interval))) + 1,
                ))

            core.snapshot = configured_snapshot
            core.report = configured_report

    return core


def _has_arg(name):
    return any(arg == name or arg.startswith(name + "=") for arg in sys.argv[1:])


def main():
    config = pleskdiag_config.load_config()
    argv = sys.argv[1:]

    if argv and argv[0] == "publish-setup":
        if os.geteuid() != 0:
            raise SystemExit("pleskdiag must be run as root.")
        from pleskdiag_publish_setup import main as publish_setup
        return publish_setup(argv[1:])

    if "doctor" in argv:
        command = "doctor"
    elif "publish" in argv:
        command = "publish"
    elif "export" in argv:
        command = "export"
    else:
        command = "scan"

    if command == "doctor":
        if os.geteuid() != 0:
            raise SystemExit("pleskdiag must be run as root.")
        from pleskdiag_doctor import doctor
        return doctor(
            config,
            vhost_system_dir=Path(_value(config, "general", "vhost_system_dir", "/var/www/vhosts/system")),
            apache_status_url=_value(config, "apache", "status_url",
                                     "http://127.0.0.1:7080/pleskdiag-server-status"),
            repo_dir=_value(config, "publish", "repo_dir", "/opt/webcore-diagnostics"),
            archive_dir=_value(config, "general", "archive_dir", "/var/log/pleskdiag"),
        )

    if command == "publish":
        if not _value(config, "publish", "enabled", False, "bool"):
            raise SystemExit("Publish is not configured. Run: pleskdiag publish-setup --github-repo owner/repo")
        if not _has_arg("--repo"):
            sys.argv.extend(["--repo", _value(config, "publish", "repo_dir", "/opt/webcore-diagnostics")])
        if not _has_arg("--archive"):
            sys.argv.extend(["--archive", _value(config, "general", "archive_dir", "/var/log/pleskdiag")])

    core = _configure_core(_load_core(), config)
    return core.main()


if __name__ == "__main__":
    sys.exit(main())
