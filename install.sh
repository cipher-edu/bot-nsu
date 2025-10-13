#!/bin/bash

# Installation Script
# Ishlatish: ./install.sh

echo "🤖 Telegram So'rovnoma Boti - O'rnatish"
echo "========================================"
echo ""

# Docker va Docker Compose mavjudligini tekshirish
echo "🔍 Docker tekshirilmoqda..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker topilmadi! Iltimos, Docker o'rnating."
    echo "   https://docs.docker.com/get-docker/"
    exit 1
fi
echo "✅ Docker mavjud"

echo "🔍 Docker Compose tekshirilmoqda..."
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose topilmadi! Iltimos, Docker Compose o'rnating."
    echo "   https://docs.docker.com/compose/install/"
    exit 1
fi
echo "✅ Docker Compose mavjud"

# .env fayl mavjudligini tekshirish
echo ""
echo "🔍 Sozlamalar fayli tekshirilmoqda..."
if [ ! -f .env ]; then
    echo "⚠️  .env fayl topilmadi. Yangi fayl yaratilmoqda..."
    cp .env.example .env
    echo "📝 .env fayl yaratildi!"
    echo ""
    echo "⚠️  MUHIM: .env faylini tahrirlang!"
    echo "   1. Bot tokenini kiriting (BotFather dan)"
    echo "   2. Admin ID ni kiriting (@userinfobot dan)"
    echo ""
    read -p "Hozir tahrirlaysizmi? (yes/no): " edit_now
    if [ "$edit_now" == "yes" ]; then
        ${EDITOR:-nano} .env
    else
        echo "⚠️  Keyin tahrirlashni unutmang: nano .env"
        exit 0
    fi
else
    echo "✅ .env fayl mavjud"
fi

# Sozlamalarni tekshirish
source .env

if [ -z "$BOT_TOKEN" ] || [ "$BOT_TOKEN" == "YOUR_BOT_TOKEN" ]; then
    echo "❌ BOT_TOKEN sozlanmagan!"
    echo "   .env faylida BOT_TOKEN ni o'zgartiring"
    exit 1
fi

if [ -z "$ADMIN_IDS" ]; then
    echo "⚠️  ADMIN_IDS sozlanmagan!"
    echo "   .env faylida ADMIN_IDS ni o'zgartiring"
fi

echo ""
echo "🏗️  Docker container yaratilmoqda..."
docker-compose build

if [ $? -ne 0 ]; then
    echo "❌ Build jarayonida xatolik!"
    exit 1
fi

echo ""
echo "🚀 Bot ishga tushirilmoqda..."
docker-compose up -d

if [ $? -ne 0 ]; then
    echo "❌ Bot ishga tushmadi!"
    exit 1
fi

echo ""
echo "⏳ PostgreSQL kutilmoqda..."
sleep 5

echo ""
echo "✅ O'rnatish muvaffaqiyatli yakunlandi!"
echo ""
echo "📊 Bot holati:"
docker-compose ps

echo ""
echo "📝 Foydali buyruqlar:"
echo "   docker-compose logs -f bot    - Loglarni ko'rish"
echo "   docker-compose restart bot    - Botni qayta ishga tushirish"
echo "   docker-compose down           - Botni to'xtatish"
echo "   ./manage_db.sh stats          - Statistika"
echo "   ./backup.sh                   - Backup yaratish"
echo ""
echo "🎉 Botingiz tayyor! Telegram da /start ni bosing"
