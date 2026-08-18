#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR=/etc/pleskdiag
CONFIG_FILE="$CONFIG_DIR/pleskdiag.conf"
ARCHIVE_DIR=/var/log/pleskdiag
BIN_LINK=/usr/local/bin/pleskdiag
STATUS_NAME=pleskdiag-status.conf

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo "install.sh must be run as root" >&2
    exit 1
fi

command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
python3 - <<'PY'
import sys
if sys.version_info < (3, 6):
    raise SystemExit("Python 3.6 or newer is required")
PY
command -v plesk >/dev/null 2>&1 || { echo "Plesk CLI not found; this does not appear to be a Plesk server" >&2; exit 1; }

chmod 0755 "$SCRIPT_DIR/pleskdiag" "$SCRIPT_DIR/pleskdiag_cli.py"
mkdir -p "$CONFIG_DIR" "$ARCHIVE_DIR"
chmod 0750 "$CONFIG_DIR" "$ARCHIVE_DIR"

if [[ ! -f "$CONFIG_FILE" ]]; then
    cp "$SCRIPT_DIR/config.example.ini" "$CONFIG_FILE"
    chmod 0640 "$CONFIG_FILE"
    echo "Created $CONFIG_FILE"
else
    echo "Preserved existing $CONFIG_FILE"
fi

ln -sfn "$SCRIPT_DIR/pleskdiag_cli.py" "$BIN_LINK"
echo "Installed command: $BIN_LINK -> $SCRIPT_DIR/pleskdiag_cli.py"

APACHECTL="$(command -v apachectl || command -v apache2ctl || true)"
if [[ -n "$APACHECTL" ]] && "$APACHECTL" -M 2>&1 | grep -q 'status_module'; then
    if [[ -d /etc/httpd/conf.d ]]; then
        STATUS_FILE="/etc/httpd/conf.d/$STATUS_NAME"
        RELOAD_CMD=(systemctl reload httpd)
    elif [[ -d /etc/apache2/conf-available ]]; then
        STATUS_FILE="/etc/apache2/conf-available/$STATUS_NAME"
        RELOAD_CMD=(systemctl reload apache2)
    else
        STATUS_FILE=""
    fi

    if [[ -n "${STATUS_FILE:-}" && ! -f "$STATUS_FILE" ]]; then
        cp "$SCRIPT_DIR/extras/apache-status.conf" "$STATUS_FILE"
        chmod 0644 "$STATUS_FILE"
        if [[ "$STATUS_FILE" == /etc/apache2/conf-available/* ]] && command -v a2enconf >/dev/null 2>&1; then
            a2enconf pleskdiag-status >/dev/null
        fi
        if "$APACHECTL" -t; then
            "${RELOAD_CMD[@]}" || true
            echo "Configured localhost Apache status endpoint: $STATUS_FILE"
        else
            rm -f "$STATUS_FILE"
            echo "WARNING: Apache config test failed; status endpoint was not installed" >&2
        fi
    fi
else
    echo "WARNING: Apache mod_status not detected; live request correlation will be unavailable" >&2
fi

echo
echo "Installation complete. Run:"
echo "  pleskdiag doctor"
echo "  pleskdiag scan"
