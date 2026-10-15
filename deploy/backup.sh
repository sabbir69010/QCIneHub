#!/bin/sh
# Daily consistent SQLite backup (safe while the bot is running). Keeps 14 days.
set -eu
SRC=/opt/qcine_bot/data/qcine.db
DEST=/opt/qcine_bot/backups
mkdir -p "$DEST"
sqlite3 "$SRC" ".backup '$DEST/qcine-$(date +%F).db'"
find "$DEST" -name 'qcine-*.db' -mtime +14 -delete
