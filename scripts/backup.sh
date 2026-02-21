#!/bin/bash
set -euo pipefail

# This script assumes it runs on the host or has access to the docker socket.
# For standard deployments, run this from the project root.

BACKUP_DIR="./backups"
DATE=$(date +%Y-%m-%d_%H%M)
BACKUP_FILE="${BACKUP_DIR}/zero_db_${DATE}.sql"

mkdir -p "$BACKUP_DIR"

echo "Starting database backup..."

# Dump database from Docker
# Note: Ensure DB_USER and DB_NAME are consistent with your .env
if command -v docker &> /dev/null; then
    docker compose exec -T postgres pg_dump -U zero zero_db > "$BACKUP_FILE"
    
    # Encrypt with GPG if a passphrase file exists
    if [ -f ~/.backup_passphrase ]; then
        gpg --batch --yes --symmetric --cipher-algo AES256 \
            --passphrase-file ~/.backup_passphrase \
            "$BACKUP_FILE"
        rm "$BACKUP_FILE"
        echo "Backup encrypted: ${BACKUP_FILE}.gpg"
    else
        echo "Backup completed (unencrypted): ${BACKUP_FILE}"
        echo "Tip: Create ~/.backup_passphrase and install gpg to enable encryption."
    fi

    # Keep only last 30 days
    find "$BACKUP_DIR" -name "*.sql*" -mtime +30 -delete
else
    echo "Error: Docker not found. Cannot perform backup."
    exit 1
fi
