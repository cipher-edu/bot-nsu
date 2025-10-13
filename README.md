# 🤖 Telegram So'rovnoma Boti

Professional Telegram bot so'rovnomalar o'tkazish va natijalarni real vaqtda kuzatish uchun.

## ✨ Asosiy Imkoniyatlar

### 👥 Foydalanuvchilar uchun:
- 📱 **Telefon raqam bilan ro'yxatdan o'tish** - xavfsiz va oson
- 🤖 **Captcha testi** - botlar va spam dan himoya
- 📢 **Kanal obunalarini tekshirish** - faqat a'zolar ishtirok etadi
- 🗳️ **Ovoz berish** - har bir foydalanuvchi 1 marta ovoz beradi
- 📊 **Real vaqt statistika** - natijalarni Pie Chart ko'rinishida ko'rish
- 📈 **Ovozlar tarixi** - siz qaysi so'rovnomalarda qatnashganingizni ko'ring

### 👑 Admin uchun:
- ➕ **So'rovnoma yaratish** - sarlavha, tavsif, rasm va nomzodlar
- 📋 **So'rovnomalarni boshqarish** - ko'rish, tahrirlash, o'chirish
- 📢 **Kanallar boshqaruvi** - majburiy obuna kanallarini qo'shish/o'chirish
- 👥 **To'liq statistika** - foydalanuvchilar, ovozlar, faollik
- 🔒 **Anti-fraud tizim** - nakrutka va botlarni aniqlash

## 🛡️ Xavfsizlik Xususiyatlari

1. **Captcha testi** - har bir yangi foydalanuvchi matematik masalani yechadi
2. **Telefon raqam verifikatsiyasi** - har bir raqam faqat 1 marta ishlatiladi
3. **Kanal obunalari tekshiruvi** - faqat a'zolar ovoz beradi
4. **Takroriy ovoz berish oldini olish** - 1 foydalanuvchi = 1 ovoz
5. **Fraud detection** - shubhali harakatlarni kuzatish va saqlash

## 📋 Talablar

- Docker va Docker Compose
- Telegram Bot Token ([@BotFather](https://t.me/BotFather) dan)
- Admin Telegram ID

## 🚀 O'rnatish

### 1. Loyihani klonlash yoki yuklab olish

```bash
# GitHub dan klonlash (agar mavjud bo'lsa)
git clone https://github.com/username/telegram-poll-bot.git
cd telegram-poll-bot

# Yoki fayllarni qo'lda ko'chirish
```

### 2. Environment faylini sozlash

```bash
# .env.example faylidan nusxa oling
cp .env.example .env

# .env faylini tahrirlang
nano .env
```

`.env` faylida quyidagilarni o'zgartiring:

```env
BOT_TOKEN=sizning_bot_tokeningiz
ADMIN_IDS=sizning_telegram_id,boshqa_admin_id
```

### 3. Bot tokenini olish

1. Telegram da [@BotFather](https://t.me/BotFather) ga o'ting
2. `/newbot` buyrug'ini yuboring
3. Bot nomini kiriting (masalan: "Mening So'rovnoma Botim")
4. Bot username kiriting (masalan: "my_poll_bot")
5. BotFather sizga token beradi: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

### 4. Admin ID ni aniqlash

1. [@userinfobot](https://t.me/userinfobot) ga o'ting
2. Bot sizga ID ingizni ko'rsatadi
3. Bu ID ni `.env` faylidagi `ADMIN_IDS` ga qo'shing

### 5. Docker bilan ishga tushirish

```bash
# Containerlarni build qilish va ishga tushirish
docker-compose up -d

# Loglarni ko'rish
docker-compose logs -f bot

# To'xtatish
docker-compose down

# Ma'lumotlar bilan birga to'xtatish
docker-compose down -v
```

## 📱 Botdan Foydalanish

### Foydalanuvchi uchun:

1. **Ro'yxatdan o'tish**:
   - Botga `/start` yuboring
   - "Telefon raqamni yuborish" tugmasini bosing
   - Matematik masalani yeching (Captcha)
   - Kerakli kanallarga obuna bo'ling

2. **Ovoz berish**:
   - "Faol so'rovnomalar" ni tanlang
   - So'rovnomani tanlang
   - Nomzodni tanlang va ovoz bering

3. **Natijalarni ko'rish**:
   - "Natijalarni ko'rish" tugmasini bosing
   - Pie chart va statistikani ko'ring

### Admin uchun:

1. **So'rovnoma yaratish**:
   - "Admin Panel" → "So'rovnoma yaratish"
   - Sarlavha kiriting (masalan: "Eng faol xodim")
   - Tavsif kiriting
   - Rasm yuklang (ixtiyoriy)
   - Nomzodlar ro'yxatini kiriting (har qatorga 1 ta)
   - Tasdiqlang

2. **Kanal qo'shish**:
   - "Admin Panel" → "Kanallar boshqaruvi"
   - "Kanal qo'shish" tugmasini bosing
   - Botni kanalga admin qilib qo'shing
   - Kanal username yoki ID sini yuboring

3. **Statistika**:
   - "Admin Panel" → "Statistika"
   - Barcha ma'lumotlarni ko'ring

## 🗃️ Ma'lumotlar Bazasi Tuzilishi

### Tables:

1. **users** - Foydalanuvchilar ma'lumotlari
   - user_id, username, phone_number
   - is_verified, is_banned
   - registered_at, last_activity

2. **channels** - Majburiy obuna kanallari
   - channel_id, channel_username, channel_title

3. **polls** - So'rovnomalar
   - title, description, image_file_id
   - created_by, is_active, total_votes

4. **poll_candidates** - So'rovnoma nomzodlari
   - poll_id, candidate_name, votes

5. **votes** - Ovozlar (takroriy oldini olish)
   - poll_id, user_id, candidate_id

6. **captcha_sessions** - Captcha sessiyalari

7. **fraud_detection** - Shubhali harakatlar

## 🔧 Sozlamalar

### Docker Compose:

```yaml
# docker-compose.yml da portlarni o'zgartirish
ports:
  - "5433:5432"  # Host:Container

# Parolni o'zgartirish
POSTGRES_PASSWORD: yangi_xavfsiz_parol
```

### Bot sozlamalari:

```python
# main.py da sozlamalar
BOT_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',')]
```

## 📊 Xususiyatlar

### So'rovnoma yaratishda:

- **Sarlavha**: Maksimal 500 belgi
- **Tavsif**: Cheksiz matn
- **Rasm**: PNG, JPG, GIF (ixtiyoriy)
- **Nomzodlar**: Minimum 2 ta, maksimum cheksiz

### Ovoz berish:

- Har bir foydalanuvchi 1 marta ovoz beradi
- Ovozni o'zgartirish mumkin emas
- Real vaqt statistika
- Pie chart ko'rinishida natijalar

### Anti-fraud:

- Telefon raqam verifikatsiyasi
- Captcha testi
- Database constraints (UNIQUE)
- Fraud detection loglari

## 🐛 Xatoliklarni Bartaraf Etish

### Bot ishlamayapti:

```bash
# Loglarni tekshiring
docker-compose logs bot

# Containerlarni qayta ishga tushiring
docker-compose restart

# Ma'lumotlar bazasini tekshiring
docker-compose exec postgres psql -U botuser -d telegram_bot
```

### Ma'lumotlar bazasi xatoligi:

```bash
# Postgres containerga kirish
docker-compose exec postgres bash

# Ma'lumotlar bazasini tekshirish
psql -U botuser -d telegram_bot

# Jadvallarni ko'rish
\dt

# Ma'lumotlarni tekshirish
SELECT * FROM users;
SELECT * FROM polls;
```

### Token xatoligi:

- Bot token to'g'ri kiritilganini tekshiring
- BotFather da bot faol ekanligini tekshiring
- `.env` fayl to'g'ri formatda ekanligini tekshiring

## 🔄 Yangilash

```bash
# Yangi versiyani tortib olish
git pull

# Containerlarni qayta build qilish
docker-compose build

# Qayta ishga tushirish
docker-compose up -d
```

## 🗑️ O'chirish

```bash
# Containerlarni to'xtatish va o'chirish
docker-compose down

# Ma'lumotlar bilan birga o'chirish
docker-compose down -v

# Image larni o'chirish
docker rmi telegram_bot_bot
```

## 📝 Qo'shimcha Imkoniyatlar

### 1. So'rovnoma muddati:

So'rovnomaga tugash sanasini qo'shish mumkin:

```python
# main.py da
ends_at TIMESTAMP
```

### 2. Ko'p tillilik:

Uzbek, Rus, Ingliz tillarini qo'shish:

```python
# Tillar lug'ati
TEXTS = {
    'uz': {'welcome': 'Xush kelibsiz!'},
    'ru': {'welcome': 'Добро пожаловать!'},
    'en': {'welcome': 'Welcome!'}
}
```

### 3. Export funksiyasi:

Natijalarni Excel yoki CSV ga export qilish:

```python
import pandas as pd
# Excel yaratish
df.to_excel('results.xlsx')
```

### 4. Notification tizimi:

Yangi so'rovnoma yaratilganda xabar yuborish:

```python
# Barcha foydalanuvchilarga xabar
for user in users:
    await bot.send_message(user.id, "Yangi so'rovnoma!")
```

## 🤝 Hissa Qo'shish

Agar siz bu loyihaga hissa qo'shmoqchi bo'lsangiz:

1. Fork qiling
2. Feature branch yarating
3. Commit qiling
4. Push qiling
5. Pull Request yuboring

## 📄 Litsenziya

MIT License

## 👨‍💻 Muallif

Created with ❤️ for Uzbekistan

## 📞 Yordam

Savollaringiz bo'lsa:
- GitHub Issues: [link]
- Telegram: @support
- Email: support@example.com

## 🎯 Keyingi Rejalar

- [ ] Ko'p tillilik (UZ, RU, EN)
- [ ] So'rovnoma muddati
- [ ] Natijalarni export qilish
- [ ] Batch notification
- [ ] Advanced analytics
- [ ] Mobile responsive web interface
- [ ] API endpoints
- [ ] Webhook support

---

**Eslatma**: Bu bot professional maqsadlar uchun ishlatilishi mumkin. Xavfsizlik va privacy ni birinchi o'ringa qo'ying! 🔒
