"""Low-overhead MariaDB status sampling for PleskDiag."""
from __future__ import print_function

import subprocess

STATUS_KEYS = [
    "Queries", "Questions", "Slow_queries", "Created_tmp_tables",
    "Created_tmp_disk_tables", "Threads_connected", "Threads_running",
]


def _db(sql):
    try:
        p = subprocess.run(["plesk", "db", "-NBe", sql], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, universal_newlines=True,
                           timeout=8, check=False)
        if p.returncode != 0:
            return ""
        return p.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _status():
    rows = _db("SHOW GLOBAL STATUS WHERE Variable_name IN ({});".format(
        ",".join("'{}'".format(k) for k in STATUS_KEYS)))
    out = {}
    for line in rows.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            try:
                out[parts[0]] = int(parts[1])
            except ValueError:
                pass
    return out


class MariaDBSampler(object):
    def __init__(self):
        self.before = _status()
        self.available = bool(self.before)

    def sample(self):
        # Intentionally no per-sample SQL polling: `plesk db` itself adds measurable load.
        return None

    def finish(self):
        after = _status() if self.available else {}
        delta = {}
        for key in STATUS_KEYS:
            if key in self.before and key in after:
                delta[key] = after[key] - self.before[key]
        return {
            "available": self.available,
            "status_before": self.before,
            "status_after": after,
            "status_delta": delta,
            "activity": [],
            "domain_map": {},
        }


def report(data, samples=None):
    lines = ["\nLIVE MARIADB CORRELATION", "------------------------"]
    if not data or not data.get("available"):
        lines.append("Unavailable: Plesk database status snapshot could not be collected.")
        return "\n".join(lines)
    d = data.get("status_delta", {})
    lines.append(
        "During sample: Queries +{}   Questions +{}   Temp tables +{}   Disk temp +{}   Threads running {}   connected {}".format(
            d.get("Queries", 0), d.get("Questions", 0),
            d.get("Created_tmp_tables", 0), d.get("Created_tmp_disk_tables", 0),
            data.get("status_after", {}).get("Threads_running", "n/a"),
            data.get("status_after", {}).get("Threads_connected", "n/a"),
        )
    )
    lines.append("No application database queries captured during the sample.")
    return "\n".join(lines)
