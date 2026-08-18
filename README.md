# Webcore Plesk Diagnostics

Incident-oriented diagnostics for Linux Plesk servers. PleskDiag correlates server load, PHP-FPM workers, Plesk access logs and live Apache requests so an apparently modest traffic event can be tied back to the domain, source IP and request pattern that is actually consuming resources.

The collector is read-only. It does not ban IPs, change PHP handlers, modify customer sites or restart services during a scan.

## What it currently does

- discovers Plesk subscriptions/vhosts and their active HTTP/HTTPS logs
- samples PHP-FPM CPU/workers over a short live window
- correlates Apache `mod_status` requests with hot PHP pools
- separates static, redirect and application traffic
- identifies concentrated IP/URL workloads, WordPress login/XML-RPC activity, WP-Cron, REST API and Action Scheduler activity
- recognises Events Calendar/archive crawling and suspicious PHP/webshell-style probes
- captures low-overhead MariaDB status information through `plesk db`
- exports machine-readable JSON
- publishes sanitised diagnostic bundles to a private Git checkout
- verifies suspicious requested files against the subscription document root during publishing
- provides `pleskdiag doctor` for deployment/capability checks
- provides guided per-server deploy-key setup with `pleskdiag publish-setup`

## Requirements

- Linux Plesk server
- Python 3.6+
- root privileges
- Apache `mod_status` for live request correlation (optional but strongly recommended)
- `plesk db` for MariaDB status collection (optional)
- Git checkout with push access for `publish` (optional)

The collector deliberately uses the Python standard library and normal Plesk/Linux utilities so no virtualenv is required.

## Installation

```bash
git clone https://github.com/craggyh/pleskdiag.git /opt/pleskdiag
cd /opt/pleskdiag
sudo bash install.sh
sudo pleskdiag doctor
```

The installer creates `/usr/local/bin/pleskdiag`, `/etc/pleskdiag/pleskdiag.conf` if absent, `/var/log/pleskdiag`, and a localhost-only Apache `mod_status` endpoint when available. Existing configuration is preserved on subsequent installs.

Publishing is optional and disabled on fresh installs until `publish-setup` succeeds.

## Configuration

Default configuration file:

```text
/etc/pleskdiag/pleskdiag.conf
```

Defaults:

```ini
[general]
vhost_system_dir = /var/www/vhosts/system
archive_dir = /var/log/pleskdiag

[sampling]
seconds = 10
interval = 2

[apache]
status_url = http://127.0.0.1:7080/pleskdiag-server-status

[publish]
enabled = false
repo_dir = /opt/webcore-diagnostics
github_repo =
ssh_host =
```

For testing an alternate configuration:

```bash
PLESKDIAG_CONFIG=/tmp/pleskdiag-test.conf pleskdiag doctor
```

## Commands

```bash
sudo pleskdiag scan
sudo pleskdiag scan --minutes 30
sudo pleskdiag export > diagnostic.json
sudo pleskdiag doctor
sudo pleskdiag publish-setup --github-repo owner/private-diagnostics-repo
sudo pleskdiag publish
```

The configured repository and archive can be overridden:

```bash
sudo pleskdiag publish --repo /opt/other-diagnostics --archive /srv/pleskdiag
```

## Guided publish setup

Publishing is designed to use a unique SSH deploy key for each Plesk server. No GitHub account token is stored on the server.

Run:

```bash
sudo pleskdiag publish-setup --github-repo owner/private-diagnostics-repo
```

On the first run PleskDiag:

1. creates `/root/.ssh/pleskdiag_publish` (Ed25519 where supported, with RSA fallback),
2. adds a dedicated GitHub SSH host alias to `/root/.ssh/config`,
3. prints the public key and a suggested deploy-key title,
4. asks you to add that key to the private diagnostics repository with **Allow write access** enabled.

After adding the deploy key, rerun the same command. It will then:

1. verify GitHub read access,
2. clone or verify the diagnostics checkout (default `/opt/webcore-diagnostics`),
3. enable publishing in `/etc/pleskdiag/pleskdiag.conf`,
4. verify write permission using a `git push --dry-run`, which does not create a branch or change the remote,
5. report that `pleskdiag publish` is ready.

Example:

```text
PleskDiag publish key created:
------------------------------------------------------------
ssh-ed25519 AAAA... pleskdiag@server.example.com
------------------------------------------------------------

Add this key to GitHub repository owner/private-diagnostics-repo as a Deploy key with WRITE access.
Suggested title: PleskDiag - server.example.com
```

The setup is idempotent: rerunning it reuses the existing server key and checkout rather than generating additional keys.

## Publishing

`publish` writes an archive locally and commits a sanitised bundle into the configured Git checkout. Query-string values with common secret/token names are redacted. Suspicious PHP requests are checked against the Plesk document root so probes can be distinguished from files that actually exist.

Keep published diagnostic repositories private: scan bundles can contain customer domains, IP addresses, request paths and server hostnames.

Once publishing is enabled, `pleskdiag doctor` additionally checks:

```text
OK     Publish repository
OK     Publish read access
OK     Publish write access
```

Write access is checked using a dry-run push only; `doctor` does not modify the remote repository.

## MariaDB behaviour

PleskDiag intentionally avoids repeated database polling because invoking `plesk db` itself creates measurable MariaDB activity. The collector uses low-overhead status snapshots. Performance Schema state is reported but query-digest collection is not required.

## Portability

Plesk-standard paths are defaults rather than fixed requirements. The installed `/usr/local/bin/pleskdiag` command points to `pleskdiag_cli.py`, a thin launcher which applies host configuration to the collector at runtime.

Use `pleskdiag doctor` on every new host before relying on live correlation. Apache status, nginx, Fail2ban, PHP-FPM and Performance Schema are capability-detected and reported independently.

## Uninstall

```bash
cd /opt/pleskdiag
sudo bash uninstall.sh
```

The default uninstall removes the command symlink and PleskDiag Apache status configuration but preserves `/etc/pleskdiag` and `/var/log/pleskdiag`. To remove configuration too:

```bash
sudo bash uninstall.sh --purge
```

Historical scan archives and SSH publishing keys are never deleted automatically.

## Safety

PleskDiag is intended to be read-only during diagnosis. Collection does not block IPs, restart services, modify Plesk configuration or change customer sites. The installer only creates its own configuration, command symlink, archive directory and localhost-only Apache status stanza. `publish-setup` only manages its dedicated SSH key/config block, diagnostics checkout and PleskDiag publish settings.
