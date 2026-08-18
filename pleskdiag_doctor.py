"""Deployment/capability checks for Webcore PleskDiag."""
from __future__ import print_function

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from urllib.request import urlopen
except ImportError:
    from urllib2 import urlopen


def _run(command, timeout=5, cwd=None):
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=timeout, check=False,
                              cwd=str(cwd) if cwd else None)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)


def _result(label, ok, detail, required=False):
    return ("OK" if ok else ("FAIL" if required else "WARN"), label, detail)


def _check_status_url(url):
    try:
        body = urlopen(url, timeout=2).read().decode("utf-8", "replace")
    except Exception as exc:
        return False, str(exc)
    good = ("Server Version" in body or "Srv" in body) and ("Request" in body or "Scoreboard" in body)
    return good, "reachable" if good else "reachable, but response does not look like mod_status"


def _publish_enabled(config):
    try:
        return config.getboolean("publish", "enabled")
    except Exception:
        return False


def doctor(config, vhost_system_dir, apache_status_url, repo_dir, archive_dir):
    results = []
    results.append(_result("Python", sys.version_info >= (3, 6), platform.python_version(), required=True))

    plesk = shutil.which("plesk")
    results.append(_result("Plesk CLI", bool(plesk), plesk or "not found", required=True))

    vroot = Path(vhost_system_dir)
    count = 0
    if vroot.is_dir():
        try:
            count = sum(1 for item in vroot.iterdir() if item.is_dir())
        except OSError:
            pass
    results.append(_result("Plesk vhost tree", vroot.is_dir(), "{} ({} entries)".format(vroot, count), required=True))

    apachectl = shutil.which("apachectl") or shutil.which("apache2ctl")
    if apachectl:
        rc, out, err = _run([apachectl, "-M"])
        loaded = rc == 0 and "status_module" in (out + "\n" + err)
        results.append(_result("Apache mod_status", loaded, "loaded" if loaded else "not detected"))
    else:
        results.append(_result("Apache", False, "apachectl/apache2ctl not found"))

    status_ok, detail = _check_status_url(apache_status_url)
    results.append(_result("PleskDiag status URL", status_ok, "{} ({})".format(apache_status_url, detail)))

    nginx = shutil.which("nginx")
    results.append(_result("nginx", bool(nginx), nginx or "not installed"))

    rc, out, err = _run(["ps", "-eo", "args="])
    pools = sum(1 for line in out.splitlines() if "php-fpm: pool " in line) if rc == 0 else 0
    results.append(_result("PHP-FPM pools", pools > 0, "{} active pool workers detected".format(pools)))

    db_ok = False
    ps_state = "unknown"
    if plesk:
        rc, out, err = _run([plesk, "db", "-NBe", "SELECT 1;"])
        db_ok = rc == 0 and out.strip() == "1"
        if db_ok:
            rc2, out2, err2 = _run([plesk, "db", "-NBe", "SELECT @@performance_schema;"])
            if rc2 == 0:
                ps_state = "ON" if out2.strip().upper() in ("1", "ON", "YES", "TRUE") else "OFF"
    results.append(_result("Plesk database access", db_ok, "read-only query succeeded" if db_ok else "plesk db query failed"))
    results.append(_result("Performance Schema", ps_state == "ON", ps_state))

    f2b = shutil.which("fail2ban-client")
    f2b_ok = False
    detail = "not installed"
    if f2b:
        rc, out, err = _run([f2b, "ping"])
        f2b_ok = rc == 0 and "pong" in out.lower()
        detail = "running" if f2b_ok else "installed, daemon not responding"
    results.append(_result("Fail2ban", f2b_ok, detail))

    publish_enabled = _publish_enabled(config)
    repo = Path(repo_dir)
    if not publish_enabled:
        results.append(_result("Publishing", True, "disabled (run pleskdiag publish-setup to enable)"))
    else:
        git_ok = repo.is_dir() and (repo / ".git").exists()
        results.append(_result("Publish repository", git_ok,
                               "{} ({})".format(repo, "git checkout" if git_ok else "not configured")))
        if git_ok:
            rc, out, err = _run(["git", "ls-remote", "origin", "HEAD"], timeout=15, cwd=repo)
            read_ok = rc == 0
            results.append(_result("Publish read access", read_ok,
                                   "origin reachable" if read_ok else (err or out or "failed")))

            rc, out, err = _run(["git", "push", "--dry-run", "origin",
                                 "HEAD:refs/heads/pleskdiag-write-test"], timeout=20, cwd=repo)
            write_ok = rc == 0
            results.append(_result("Publish write access", write_ok,
                                   "dry-run push succeeded" if write_ok else (err or out or "failed")))

    archive = Path(archive_dir)
    archive_ok = archive.is_dir() and os.access(str(archive), os.W_OK)
    if not archive.exists():
        archive_ok = archive.parent.is_dir() and os.access(str(archive.parent), os.W_OK)
    results.append(_result("Archive path", archive_ok, str(archive)))

    cfg_path = getattr(config, "_pleskdiag_path", "/etc/pleskdiag/pleskdiag.conf") if config else "defaults only"
    cfg_exists = bool(config) and bool(getattr(config, "_pleskdiag_exists", False))
    results.append(_result("Configuration", cfg_exists, cfg_path if cfg_exists else "defaults active; {} not found".format(cfg_path)))

    width = max(len(row[1]) for row in results)
    print("Webcore PleskDiag doctor")
    print("Server: {}\n".format(platform.node()))
    for state, label, detail in results:
        print("{:<5}  {:<{}}  {}".format(state, label, width, detail))

    fails = [row for row in results if row[0] == "FAIL"]
    warns = [row for row in results if row[0] == "WARN"]
    print("")
    if fails:
        print("Result: NOT READY ({} required check(s) failed, {} warning(s))".format(len(fails), len(warns)))
        return 2
    if warns:
        print("Result: READY WITH DEGRADED FEATURES ({} warning(s))".format(len(warns)))
        return 0
    print("Result: READY")
    return 0
