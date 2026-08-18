#!/usr/bin/env bash
set -euo pipefail

PURGE=false
[[ "${1:-}" == "--purge" ]] && PURGE=true

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo "uninstall.sh must be run as root" >&2
    exit 1
fi

rm -f /usr/local/bin/pleskdiag

if [[ -f /etc/httpd/conf.d/pleskdiag-status.conf ]]; then
    rm -f /etc/httpd/conf.d/pleskdiag-status.conf
    apachectl -t >/dev/null 2>&1 && systemctl reload httpd || true
elif [[ -f /etc/apache2/conf-available/pleskdiag-status.conf ]]; then
    if command -v a2disconf >/dev/null 2>&1; then
        a2disconf pleskdiag-status >/dev/null 2>&1 || true
    fi
    rm -f /etc/apache2/conf-available/pleskdiag-status.conf
    apache2ctl -t >/dev/null 2>&1 && systemctl reload apache2 || true
fi

if $PURGE; then
    rm -rf /etc/pleskdiag
    echo "Removed /etc/pleskdiag"
else
    echo "Preserved /etc/pleskdiag (use --purge to remove it)"
fi

echo "Preserved /var/log/pleskdiag archives"
echo "PleskDiag command uninstalled."
