#!/bin/bash

# Database Restore Script
# Ishlatish: ./restore.sh backup_file.sql.gz

if [ -z "$1" ]; then
    echo "❌ Faylni ko'rsating!"
    echo "Ishlatish: ./restore.sh backup_file.sql.gz"
    exit 1
fi

BACKUP_FILE=$1

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Fayl topilmadi: $BACKUP_FILE"
    exit 1
fi

echo "⚠️  OGOHLANTIRISH: Bu barcha mavjud ma'lumotlarni o'chiradi!"
read -p "Davom etasizmi? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "❌ Bekor qilindi"
    exit 0
fi

echo "🔄 Ma'lumotlar bazasi tiklanmoqda..."

# Faylni ochish (agar siqilgan bo'lsa)
if [[ $BACKUP_FILE == *.gz ]]; then
    gunzip -c $BACKUP_FILE | docker-compose exec -T postgres psql -U botuser telegram_bot
else
    cat $BACKUP_FILE | docker-compose exec -T postgres psql -U botuser telegram_bot
fi

if [ $? -eq 0 ]; then
    echo "✅ Ma'lumotlar bazasi muvaffaqiyatli tiklandi!"
else
    echo "❌ Xatolik yuz berdi!"
    exit 1
fi
