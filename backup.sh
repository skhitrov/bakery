#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/opt/diary/backups"
DB_PATH="/opt/diary/diary.db"

mkdir -p "$BACKUP_DIR"

# Hot-safe SQLite backup
sqlite3 "$DB_PATH" ".backup ${BACKUP_DIR}/diary_$(date +%Y%m%d_%H%M%S).db"

# Remove backups older than 2 days
find "$BACKUP_DIR" -name "*.db" -mtime +2 -delete
