#!/usr/bin/env bash
# Консистентный бэкап SQLite-БД (sqlite3 .backup) + ротация (14 копий).
# Использование: ./deploy/backup.sh [путь_к_БД] [папка_бэкапов]
# Cron (ежедневно в 3:00):
#   0 3 * * * /home/<user>/bot_reminder/deploy/backup.sh >> ~/backup.log 2>&1
set -euo pipefail

DB="${1:-./data/tasks.db}"
DEST="${2:-./backups}"
KEEP=14

mkdir -p "$DEST"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="$DEST/tasks-$TS.db"

sqlite3 "$DB" ".backup '$OUT'"

# Ротация: оставить последние $KEEP
ls -1t "$DEST"/tasks-*.db 2>/dev/null | tail -n "+$((KEEP + 1))" | xargs -r rm -f

echo "backup: $OUT"
