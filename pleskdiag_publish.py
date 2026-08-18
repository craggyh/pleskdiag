"""Sanitised PleskDiag bundle publisher."""
from __future__ import print_function

import io
import json
import os
import re
import socket
import subprocess
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

SECRET_QS_RE = re.compile(r'(?i)([?&](?:token|nonce|key|secret|password|passwd|pwd|auth|signature|sig)=)[^&\s\"]+')


def _run(command, cwd=None):
    p = subprocess.run(command, cwd=str(cwd) if cwd else None,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, timeout=30, check=False)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "command failed").strip())
    return p.stdout.strip()


def _sanitise_text(text):
    return SECRET_QS_RE.sub(r'\1[REDACTED]', text)


def _sanitise_obj(value):
    if isinstance(value, dict):
        return {k: _sanitise_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitise_obj(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_sanitise_obj(v) for v in value)
    if isinstance(value, str):
        return _sanitise_text(value)
    return value


def publish(data, report_func, repo_path=None, archive_root=None):
    repo = Path(repo_path or "/opt/webcore-diagnostics")
    archive = Path(archive_root or "/var/log/pleskdiag")
    if not (repo / ".git").exists():
        raise RuntimeError("diagnostics repository is not a Git checkout: {}".format(repo))

    now = datetime.now()
    host = data.get("hostname") or socket.getfqdn()
    stamp = now.strftime("%Y-%m-%d/%H%M%S")
    rel = Path("scans") / host / stamp
    repo_out = repo / rel
    archive_out = archive / host / stamp
    repo_out.mkdir(parents=True, exist_ok=True)
    archive_out.mkdir(parents=True, exist_ok=True)

    clean = _sanitise_obj(data)
    buf = io.StringIO()
    with redirect_stdout(buf):
        report_func(clean)
    report_text = _sanitise_text(buf.getvalue())
    json_text = json.dumps(clean, indent=2, sort_keys=True)

    for base in (repo_out, archive_out):
        (base / "report.txt").write_text(report_text, encoding="utf-8")
        (base / "scan.json").write_text(json_text + "\n", encoding="utf-8")

    _run(["git", "add", str(rel)], cwd=repo)
    status = _run(["git", "status", "--porcelain", "--", str(rel)], cwd=repo)
    if status:
        _run(["git", "commit", "-m", "pleskdiag: publish {} {}".format(host, now.strftime("%Y-%m-%d %H:%M:%S"))], cwd=repo)
        _run(["git", "push"], cwd=repo)
    commit = _run(["git", "rev-parse", "HEAD"], cwd=repo)

    return {
        "commit": commit,
        "repo_path": str(repo_out),
        "archive_path": str(archive_out),
    }
