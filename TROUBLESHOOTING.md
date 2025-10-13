# 🔧 Muammolarni Hal Qilish

## ❌ Umumiy Xatoliklar va Yechimlar

### 1. Bot ishga tushmayapti

**Simptom**: `docker-compose up` dan keyin bot ishlamaydi

**Yechim**:
```bash
# Loglarni tekshiring
docker-compose logs bot

# Agar "BOT_TOKEN" xatosi bo'lsa:
# 1. .env faylini tekshiring
cat .env

# 2. Token to'g'ri ekanligini tasdiqlang
# 3. Containerlarni qayta ishga tushiring
docker-compose restart bot
```

### 2. Database connection xatosi

**Simptom**: `could not connect to server`

**Yechim**:
```bash
# PostgreSQL ishlab turganini tekshiring
docker-compose ps

# Agar postgres "unhealthy" bo'lsa:
docker-compose down
docker-compose up -d

# 10 soniya kuting va qayta urinib ko'ring
```

### 3. Telegram API xatolari

**Simptom**: `Unauthorized` yoki `Invalid token`

**Yechim**:
- BotFather dan yangi token oling
- .env fayldagi tokenni yangilang
- Botni qayta ishga tushiring

### 4. Kanal obunasini tekshirishda xato

**Simptom**: Bot kanal a'zoligini tekshira olmayapti

**Yechim**:
- Botni kanalga **admin** qilib qo'shing
- Bot kanal xabarlarini o'qiy olishi kerak
- Kanal ID to'g'ri kiritilganligini tekshiring

### 5. Captcha xatoligi

**Simptom**: Captcha javob bermayapti

**Yechim**:
```bash
# Captcha sessiyalarini tozalash
./manage_db.sh cleanup

# Yoki qo'lda:
docker-compose exec postgres psql -U botuser telegram_bot -c "
    DELETE FROM captcha_sessions WHERE created_at < NOW() - INTERVAL '1 hour';
"
```

### 6. Pie chart yaratilmayapti

**Simptom**: Grafik ko'rsatilmayapti

**Yechim**:
```bash
# matplotlib kutubxonasini tekshiring
docker-compose exec bot python -c "import matplotlib; print('OK')"

# Agar xato bo'lsa, qayta build qiling:
docker-compose build --no-cache bot
docker-compose up -d
```

### 7. Telefon raqam xatosi

**Simptom**: `duplicate key value violates unique constraint`

**Yechim**:
- Har bir telefon raqam faqat 1 marta ishlatiladi
- Boshqa telefon raqam bilan urinib ko'ring
- Yoki ma'lumotlar bazasidan eski yozuvni o'chiring:

```bash
docker-compose exec postgres psql -U botuser telegram_bot -c "
    DELETE FROM users WHERE phone_number = '+998901234567';
"
```

### 8. Docker disk joy yetishmayapti

**Simptom**: `no space left on device`

**Yechim**:
```bash
# Foydalanilmayotgan containerlarni o'chirish
docker system prune -a

# Eski imagelarni o'chirish
docker image prune -a

# Volumelarni tekshirish
docker volume ls
docker volume prune
```

## 🔍 Debug Mode

### Loglarni ko'rish

```bash
# Barcha loglar
docker-compose logs -f

# Faqat bot loglari
docker-compose logs -f bot

# Faqat postgres loglari
docker-compose logs -f postgres

# Oxirgi 100 qator
docker-compose logs --tail=100 bot
```

### Database ichiga kirish

```bash
# PostgreSQL shell
docker-compose exec postgres psql -U botuser telegram_bot

# Ma'lumotlarni ko'rish
telegram_bot=# SELECT * FROM users LIMIT 5;
telegram_bot=# SELECT * FROM polls;
telegram_bot=# \dt  -- Barcha jadvallar
telegram_bot=# \q   -- Chiqish
```

### Container ichiga kirish

```bash
# Bot container
docker-compose exec bot bash

# Postgres container
docker-compose exec postgres bash
```

## ⚠️ Xavfsizlik

### Bot tokenini himoyalash

1. **.env faylini .gitignore ga qo'shing**
2. **Token ni hech qachon commit qilmang**
3. **Token ni boshqalar bilan bo'lishmang**

### Ma'lumotlar bazasi paroli

```bash
# Parolni o'zgartirish:
# 1. docker-compose.yml da POSTGRES_PASSWORD ni o'zgartiring
# 2. .env da DATABASE_URL ni yangilang
# 3. Containerlarni qayta yarating:
docker-compose down -v
docker-compose up -d
```

## 🔄 Yangilash va Backup

### Backup olish

```bash
# Avtomatik backup
./backup.sh

# Qo'lda backup
docker-compose exec postgres pg_dump -U botuser telegram_bot > backup.sql
```

### Backupni tiklash

```bash
# Script orqali
./restore.sh backup_20240101_120000.sql.gz

# Qo'lda
cat backup.sql | docker-compose exec -T postgres psql -U botuser telegram_bot
```

## 📊 Performance

### Database optimization

```bash
# Index larni qayta yaratish
docker-compose exec postgres psql -U botuser telegram_bot -c "
    REINDEX DATABASE telegram_bot;
"

# Vacuum
docker-compose exec postgres psql -U botuser telegram_bot -c "
    VACUUM ANALYZE;
"
```

### Memory usage

```bash
# Container memory
docker stats

# Bot memory
docker-compose exec bot python -c "
import psutil
print(f'Memory: {psutil.Process().memory_info().rss / 1024 / 1024:.2f} MB')
"
```

## 🆘 Qo'shimcha Yordam

Agar muammo hal bo'lmasa:

1. **Loglarni yig'ing**:
```bash
docker-compose logs > logs.txt
```

2. **Konfiguratsiyani tekshiring**:
```bash
cat .env
cat docker-compose.yml
```

3. **Yordam so'rang**:
- GitHub Issues
- Telegram guruh
- Email support

## 📝 Ma'lumot To'plash

Muammoni hal qilish uchun quyidagi ma'lumotlarni yuboring:

```bash
# Tizim ma'lumotlari
uname -a
docker --version
docker-compose --version

# Container holati
docker-compose ps

# Loglar (oxirgi 50 qator)
docker-compose logs --tail=50 bot

# .env (tokenni o'chirgan holda!)
cat .env | grep -v TOKEN
```

---

**Eslatma**: Har doim avval backup oling! 💾
