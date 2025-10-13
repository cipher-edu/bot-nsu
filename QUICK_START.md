# ⚡ Tez Boshlash (Quick Start)

## 1️⃣ Bot Token Olish (3 daqiqa)

1. Telegram da [@BotFather](https://t.me/BotFather) ga o'ting
2. `/newbot` yuboring
3. Bot nomini kiriting: `Mening So'rovnoma Botim`
4. Username kiriting: `my_poll_bot`
5. Token ni nusxalang: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

## 2️⃣ Admin ID Olish (1 daqiqa)

1. [@userinfobot](https://t.me/userinfobot) ga o'ting
2. O'z ID ingizni nusxalang: `123456789`

## 3️⃣ O'rnatish (5 daqiqa)

```bash
# 1. Fayllarni yuklab oling
cd telegram_bot

# 2. .env faylini yarating
cp .env.example .env

# 3. .env ni tahrirlang
nano .env
# BOT_TOKEN va ADMIN_IDS ni o'zgartiring

# 4. O'rnatish scriptini ishga tushiring
chmod +x install.sh
./install.sh
```

## 4️⃣ Ishlayotganini Tekshirish

```bash
# Loglarni ko'ring
docker-compose logs -f bot

# Holat
docker-compose ps

# Statistika
./manage_db.sh stats
```

## 5️⃣ Telegram da Test Qilish

1. Botga o'ting: `@my_poll_bot`
2. `/start` ni bosing
3. Telefon raqamni yuboring
4. Captcha ni yeching
5. Kanallarga obuna bo'ling

## 6️⃣ Admin Panel

1. Bot adminiga o'ting
2. `/start` bosing
3. "👑 Admin Panel" ni tanlang
4. So'rovnoma yarating

---

## 📋 Asosiy Buyruqlar

```bash
# Bot
docker-compose up -d        # Ishga tushirish
docker-compose down         # To'xtatish
docker-compose restart bot  # Qayta ishga tushirish
docker-compose logs -f bot  # Loglar

# Database
./manage_db.sh stats        # Statistika
./manage_db.sh users        # Foydalanuvchilar
./manage_db.sh polls        # So'rovnomalar

# Backup
./backup.sh                 # Zaxira yaratish
./restore.sh backup.sql.gz  # Tiklash
```

## 🆘 Xatolik Bo'lsa?

```bash
# 1. Loglarni ko'ring
docker-compose logs bot

# 2. Qayta ishga tushiring
docker-compose restart

# 3. Hammasini qayta yarating
docker-compose down -v
docker-compose up -d
```

## ✅ Minimal .env Fayl

```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_IDS=123456789
DATABASE_URL=postgresql://botuser:secure_password_change_me@postgres:5432/telegram_bot
```

---

**To'liq qo'llanma**: README.md fayl

**Muammolar**: TROUBLESHOOTING.md fayl
