#!/usr/bin/env python3
"""Guided setup for publishing PleskDiag bundles to a private Git repository."""
from __future__ import print_function

import argparse
import configparser
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_KEY = Path("/root/.ssh/pleskdiag_publish")
DEFAULT_CHECKOUT = Path("/opt/webcore-diagnostics")
DEFAULT_CONFIG = Path("/etc/pleskdiag/pleskdiag.conf")


def _run(command, timeout=20, cwd=None):
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=timeout, check=False,
                              cwd=str(cwd) if cwd else None)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", str(exc)


def _slug(value):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return value.strip("-.") or "server"


def _ensure_key(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(str(path.parent), 0o700)
    pub = Path(str(path) + ".pub")
    if path.exists() and pub.exists():
        return pub, False

    comment = "pleskdiag@{}".format(platform.node() or "server")
    rc, out, err = _run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", comment, "-f", str(path)])
    if rc != 0:
        rc, out, err = _run(["ssh-keygen", "-q", "-t", "rsa", "-b", "3072", "-N", "", "-C", comment, "-f", str(path)])
    if rc != 0:
        raise RuntimeError("ssh-keygen failed: {}".format(err or out))
    os.chmod(str(path), 0o600)
    os.chmod(str(pub), 0o644)
    return pub, True


def _write_ssh_config(alias, key_path):
    ssh_dir = key_path.parent
    cfg = ssh_dir / "config"
    existing = cfg.read_text() if cfg.exists() else ""
    start = "# BEGIN PLESKDIAG PUBLISH {}".format(alias)
    end = "# END PLESKDIAG PUBLISH {}".format(alias)
    block = "\n".join([
        start,
        "Host {}".format(alias),
        "    HostName github.com",
        "    User git",
        "    IdentityFile {}".format(key_path),
        "    IdentitiesOnly yes",
        end,
        "",
    ])
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\n?", re.S)
    if pattern.search(existing):
        updated = pattern.sub(block, existing)
    else:
        updated = existing.rstrip() + ("\n\n" if existing.strip() else "") + block
    cfg.write_text(updated)
    os.chmod(str(cfg), 0o600)


def _repo_url(alias, repo):
    return "git@{}:{}.git".format(alias, repo)


def _read_access(alias, repo):
    return _run(["git", "ls-remote", _repo_url(alias, repo), "HEAD"], timeout=20)


def _clone_or_verify(checkout, alias, repo):
    url = _repo_url(alias, repo)
    if checkout.exists():
        if not (checkout / ".git").exists():
            raise RuntimeError("{} exists but is not a Git checkout".format(checkout))
        rc, out, err = _run(["git", "remote", "get-url", "origin"], cwd=checkout)
        if rc != 0:
            raise RuntimeError("cannot read origin for {}: {}".format(checkout, err or out))
        if out != url:
            _run(["git", "remote", "set-url", "origin", url], cwd=checkout)
        rc, out, err = _run(["git", "fetch", "--quiet", "origin"], timeout=30, cwd=checkout)
        if rc != 0:
            raise RuntimeError("git fetch failed: {}".format(err or out))
        return
    checkout.parent.mkdir(parents=True, exist_ok=True)
    rc, out, err = _run(["git", "clone", "--quiet", url, str(checkout)], timeout=60)
    if rc != 0:
        raise RuntimeError("git clone failed: {}".format(err or out))


def _write_config(config_path, repo, checkout, alias):
    parser = configparser.ConfigParser()
    if config_path.exists():
        parser.read(str(config_path))
    if not parser.has_section("publish"):
        parser.add_section("publish")
    parser.set("publish", "enabled", "true")
    parser.set("publish", "repo_dir", str(checkout))
    parser.set("publish", "github_repo", repo)
    parser.set("publish", "ssh_host", alias)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w") as handle:
        parser.write(handle)
    os.chmod(str(config_path), 0o640)


def _write_test(checkout):
    rc, out, err = _run(["git", "push", "--dry-run", "origin", "HEAD:refs/heads/pleskdiag-write-test"],
                        timeout=30, cwd=checkout)
    text = (out + "\n" + err).strip()
    return rc == 0, text


def main(argv=None):
    parser = argparse.ArgumentParser(prog="pleskdiag publish-setup",
                                     description="Configure a per-server SSH deploy key for private scan publishing")
    parser.add_argument("--github-repo", help="private diagnostics repository in owner/repo form")
    parser.add_argument("--checkout", default=str(DEFAULT_CHECKOUT), help="local diagnostics checkout")
    parser.add_argument("--key", default=str(DEFAULT_KEY), help="private SSH key path")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="PleskDiag config path")
    args = parser.parse_args(argv)

    if os.geteuid() != 0:
        raise SystemExit("pleskdiag publish-setup must be run as root")
    for command in ("git", "ssh-keygen", "ssh"):
        if not shutil.which(command):
            raise SystemExit("{} is required".format(command))

    repo = (args.github_repo or "").strip()
    if not repo and sys.stdin.isatty():
        repo = input("GitHub diagnostics repository (owner/repo): ").strip()
    if not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo):
        raise SystemExit("Specify the private diagnostics repository with --github-repo owner/repo")

    key_path = Path(args.key)
    checkout = Path(args.checkout)
    config_path = Path(args.config)
    host = _slug(platform.node().split(".")[0] if platform.node() else "server")
    alias = "github-pleskdiag-{}".format(host)

    try:
        pub_path, created = _ensure_key(key_path)
        _write_ssh_config(alias, key_path)
    except Exception as exc:
        raise SystemExit("Publish setup failed: {}".format(exc))

    public_key = pub_path.read_text().strip()
    print("\nPleskDiag publish key{}:".format(" created" if created else ""))
    print("------------------------------------------------------------")
    print(public_key)
    print("------------------------------------------------------------")
    print("\nAdd this key to GitHub repository {} as a Deploy key with WRITE access.".format(repo))
    print("Suggested title: PleskDiag - {}".format(platform.node() or host))

    rc, out, err = _read_access(alias, repo)
    if rc != 0:
        print("\nGitHub access is not active yet.")
        print("After adding the key, rerun:")
        print("  pleskdiag publish-setup --github-repo {}".format(repo))
        return 3

    print("\nOK     GitHub read access")
    try:
        _clone_or_verify(checkout, alias, repo)
        _write_config(config_path, repo, checkout, alias)
    except Exception as exc:
        raise SystemExit("Publish setup failed: {}".format(exc))

    write_ok, detail = _write_test(checkout)
    if not write_ok:
        print("WARN   GitHub write access not confirmed")
        print("       Ensure 'Allow write access' is enabled on the deploy key.")
        if detail:
            print("       {}".format(detail.splitlines()[-1]))
        return 4

    print("OK     GitHub write access")
    print("OK     Diagnostics checkout  {}".format(checkout))
    print("OK     PleskDiag config       {}".format(config_path))
    print("\nPublish setup complete.")
    print("Run:")
    print("  pleskdiag publish")
    print("  pleskdiag doctor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
