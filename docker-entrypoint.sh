#!/bin/sh
# Hosting services mount the data disk as root. Make it writable for the app, then run the app as a normal user.
set -e
mkdir -p "${DATA_DIR:-/data}" "${UPLOAD_DIR:-/data/uploads}" 2>/dev/null || true
if [ "$(id -u)" = "0" ]; then
  chown -R talentbridge:talentbridge "${DATA_DIR:-/data}" 2>/dev/null || true
  exec gosu talentbridge "$@"
fi
exec "$@"
