#!/bin/bash

# Database Backup Script
# Ishlatish: ./backup.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="./backups"
BACKUP_FILE="$BACKUP_DIR/backup_$DATE.sql"

# Backup papkasini yaratish
mkdir -p $BACKUP_DIR

echo "🔄 Ma'lumotlar bazasi zaxiralanmoqda..."

# Docker container orqali backup
docker-compose exec -T postgres pg_dump -U botuser telegram_bot > $BACKUP_FILE

if [ $? -eq 0 ]; then
    echo "✅ Backup muvaffaqiyatli: $BACKUP_FILE"
    
    # Siqish
    gzip $BACKUP_FILE
    echo "✅ Backup siqildi: ${BACKUP_FILE}.gz"
    
    # 7 kundan eski backuplarni o'chirish
    find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete
    echo "🗑️  Eski backuplar o'chirildi"
else
    echo "❌ Backup xatolik bilan yakunlandi!"
    exit 1
fi
