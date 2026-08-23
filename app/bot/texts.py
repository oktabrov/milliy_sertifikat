"""Every user-facing string, in Uzbek (Latin).

Kept in one file so the wording can be reviewed without reading handler code.
"""

from __future__ import annotations

ASK_NAME = (
    "📝Ism va familyangizni kiriting. Iltimos to'g'ri va to'liq yozing. "
    "Lotin harflaridan foydalaning"
)

NAME_TOO_SHORT = "❗️Ism va familyangizni to'liq yozing. Kamida 5 ta harf bo'lishi kerak."

NAME_NOT_LATIN = (
    "❗️Iltimos lotin harflaridan foydalaning. Masalan: <b>Torayev Sardor</b>"
)

GREETING = (
    "👤Hurmatli {name}\n\n"
    "‼️Botning barcha imkoniyatlari bilan tanishish uchun pastdagi "
    "<b>botda test ishlash va yaratish(+video)</b> tugmasini bosing"
)

NAME_UPDATED = "✅ Ismingiz o'zgartirildi: <b>{name}</b>"

MS_SECTION = "Milliy sertifikat bo'limi\n\nKerakli tugmani bosing"

# Shown right after the process (re)started: the site had been stopped and this
# message arrived during or just after the wake-up, so the student's keyboard
# may predate a WEBHOOK_BASE change or a stale Mini App page.
WAKE_NOTICE = (
    "\n\n⚠️ <i>Bot hozir qayta ishga tushdi — u vaqtincha to'xtatib turilgandi. "
    'Agar tugmalar ishlamasa, testni havola orqali oching: '
    '<a href="{url}">Mini ilova</a></i>'
)

HOW_TO_ANSWER = (
    "📗 <b>Testga qanday javob beriladi?</b>\n\n"
    "1️⃣ <b>Test tekshirish</b> tugmasini bosing.\n"
    "2️⃣ Ochilgan oynaga <b>test kodini</b> kiriting va <b>Davom etish</b> tugmasini bosing.\n"
    "3️⃣ Yuqoridan <b>fanni tanlang</b>.\n"
    "4️⃣ Yopiq testlarda <b>A, B, C, D</b> variantlaridan birini bosing.\n"
    "   33, 34 va 35-savollarda esa <b>A, B, C, D, E, F</b> variantlari bo'ladi.\n"
    "5️⃣ Ochiq testlarda (36-45) javobni <b>a)</b> va <b>b)</b> katakchalariga yozing.\n"
    "   Formulalar uchun maxsus matematik klaviaturadan foydalaning.\n"
    "6️⃣ Oxirida <b>Javoblarni yuborish</b> tugmasini bosing.\n\n"
    "⚠️ Ochiq testlarda iloji boricha qisqa javob yozing. "
    "\"ta, nafar, m, litr, so'm, a=, h=, jami, gradus\" kabi so'zlarni ishlatmang."
)

HOW_TO_CREATE = (
    "📘 <b>Yangi test qanday yaratiladi?</b>\n\n"
    "1️⃣ <b>Test yaratish</b> tugmasini bosing.\n"
    "2️⃣ Test nomi, savollar soni va fanlarni kiriting.\n"
    "3️⃣ Har bir savol uchun to'g'ri javobni belgilang.\n"
    "4️⃣ Ochiq savollar uchun <b>a)</b> va <b>b)</b> javoblarini yozing.\n"
    "   Bir javobning bir necha ko'rinishini qo'shish uchun "
    "<b>+ Yana javob qo'shish</b> tugmasini bosing (masalan 3/4 va 0.75).\n"
    "5️⃣ <b>Testni saqlash</b> tugmasini bosing.\n\n"
    "✅ Bot sizga <b>test kodini</b> beradi. Shu kodni o'quvchilarga yuboring."
)

HELP_VIDEO_MISSING = "📹 Video hozircha qo'shilmagan."

INFO = (
    "ℹ️ <b>Bot haqida</b>\n\n"
    "Bu bot Milliy sertifikat formatidagi testlarni ishlash va yaratish uchun.\n\n"
    "<b>Buyruqlar:</b>\n"
    "/start — botni qayta ishga tushirish\n"
    "/edit — ism va familyani o'zgartirish\n"
    "/ms — Milliy sertifikat bo'limi\n"
    "/testlarim — siz yaratgan testlar\n"
    "/natijalarim — sizning natijalaringiz\n"
    "/info — shu ma'lumot\n\n"
    "<b>Adminlar uchun:</b>\n"
    "/special — admin buyruqlari ro'yxati\n"
    "/kanallar — majburiy kanallar ro'yxati\n"
    "/adminlar — adminlar ro'yxati\n"
    "/stats — statistika\n\n"
    "Har kim <code>/id</code> orqali o'z ID raqamini bilib olishi mumkin.\n\n"
    "<b>Natijalar qanday hisoblanadi?</b>\n"
    "Natijangiz RASH (Rasch) modeli asosida 3 xil stsenariyda beriladi:\n"
    "• <b>Zaif guruh</b> — qatnashchilarning ko'pchiligi past natija ko'rsatganda\n"
    "• <b>O'rtacha guruh</b> — o'rtacha natija ko'rsatganda\n"
    "• <b>Kuchli guruh</b> — yuqori natija ko'rsatganda\n\n"
    "Shu 3 ta natija sizning haqiqiy ballingiz qaysi oraliqda bo'lishini ko'rsatadi."
)

MUST_JOIN = (
    "📢 Botdan foydalanish uchun quyidagi kanal(lar)ga a'zo bo'ling, "
    "so'ng <b>Tekshirish</b> tugmasini bosing."
)

STILL_NOT_JOINED = "❗️Siz hali barcha kanallarga a'zo bo'lmadingiz."

JOIN_CONFIRMED = "✅ Rahmat! Endi botdan to'liq foydalanishingiz mumkin."

SUBMITTED = (
    "Siz <b>{code}</b> raqamli testga javob berdingiz.\n"
    "Natijangizni ko'rish uchun 📊 <b>Natijani ko'rish</b> tugmasini bosing."
)

RESULT_PENDING = "Natija hisoblanmoqda. Bir necha daqiqadan so'ng urinib ko'ring."

RESULT_HEADER = (
    "📊 <b>{title}</b>\n"
    "👤 {name}\n"
    "✅ To'g'ri javoblar: <b>{correct}/{total}</b>\n\n"
    "<b>Stsenariy bo'yicha natijalar:</b>"
)

RESULT_ROW = "{label} — <b>{ball}</b> ball · {percentile}% · <b>{grade}</b>"

RESULT_FOOTER = (
    "\n<i>Uch stsenariy qatnashchilar kuchiga qarab ballingiz qanday "
    "o'zgarishini ko'rsatadi.</i>"
)

NO_RESULTS = "Sizda hali natijalar yo'q. <b>Test tekshirish</b> tugmasi orqali test ishlang."

NO_TESTS = "Siz hali test yaratmagansiz. <b>Test yaratish</b> tugmasini bosing."

MY_TESTS_HEADER = "📚 <b>Siz yaratgan testlar:</b>"

TEST_ROW = (
    "\n\n🔹 <b>{title}</b>\n"
    "Kod: <code>{code}</code>\n"
    "Savollar: {questions} ta · Qatnashchilar: {participants} ta · Holat: {status}"
)

TEST_CREATED = (
    "✅ Test yaratildi!\n\n"
    "🔹 <b>{title}</b>\n"
    "Test kodi: <code>{code}</code>\n"
    "Savollar soni: {questions} ta\n\n"
    "Shu kodni o'quvchilarga yuboring. Ular <b>Test tekshirish</b> tugmasi "
    "orqali javob berishadi."
)

TEST_CLOSED_OK = "🔒 <b>{title}</b> testi yopildi. Endi yangi javoblar qabul qilinmaydi."

TEST_REOPENED = "🔓 <b>{title}</b> testi qayta ochildi."

UNKNOWN = (
    "Tushunmadim 🤔\n\n"
    "Quyidagi tugmalardan birini tanlang yoki /info buyrug'i orqali "
    "ko'rsatmalarni ko'ring."
)

ADMIN_ONLY = "❗️Bu buyruq faqat adminlar uchun."

ADMIN_STATS = (
    "📈 <b>Statistika</b>\n\n"
    "👥 Foydalanuvchilar: <b>{users}</b>\n"
    "📚 Testlar: <b>{tests}</b>\n"
    "✍️ Javoblar: <b>{attempts}</b>"
)

BROADCAST_USAGE = "Foydalanish: <code>/broadcast xabar matni</code>"

BROADCAST_DONE = "✅ Yuborildi: {sent} ta. Xatolik: {failed} ta."

# --- Buttons -----------------------------------------------------------------

BTN_HOW_TO_ANSWER = "📗Testga qanday javob beriladi?"
BTN_HOW_TO_CREATE = "📘Yangi test qanday yaratiladi?"
BTN_HELP_VIDEO = "Botda test ishlash va yaratish(+video)"

BTN_CHECK_TEST = "Test tekshirish"
BTN_CREATE_TEST = "Test yaratish"
BTN_MY_RESULTS = "Mening natijalarim"
BTN_MY_TESTS = "Mening testlarim"

BTN_SEE_RESULT = "📊 Natijani ko'rish"
BTN_JOIN = "Qo'shilish"
BTN_CHECK_JOIN = "✅ Tekshirish"
BTN_CLOSE_TEST = "🔒 Yopish"
BTN_REOPEN_TEST = "🔓 Ochish"

STATUS_LABELS = {"open": "ochiq", "closed": "yopiq"}

# --- Required channels (admin) ------------------------------------------------

CHANNELS_HEADER = "📢 <b>Majburiy kanallar</b>\n\nHozircha {count} ta kanal:"

CHANNELS_EMPTY = (
    "📢 <b>Majburiy kanallar</b>\n\n"
    "Hozircha majburiy kanal yo'q — botdan hamma bemalol foydalana oladi."
)

CHANNELS_USAGE = (
    "\n\n<b>Buyruqlar:</b>\n"
    "<code>/kanal_qoshish @kanal</code> — kanal qo'shish\n"
    "<code>/kanal_ochirish @kanal</code> — kanalni o'chirish\n"
    "<code>/kanal_tozalash</code> — barcha kanallarni o'chirish"
)

CHANNEL_ADD_USAGE = (
    "Foydalanish: <code>/kanal_qoshish @kanal</code>\n\n"
    "Kanal manzilini @nom, t.me/nom yoki -100... ko'rinishida yuboring."
)

CHANNEL_REMOVE_USAGE = "Foydalanish: <code>/kanal_ochirish @kanal</code>"

CHANNEL_BAD_FORMAT = (
    "❗️<code>{value}</code> — kanal manzili noto'g'ri.\n"
    "@nom, t.me/nom yoki -100... ko'rinishida yuboring."
)

CHANNEL_NOT_FOUND = (
    "❗️<b>{channel}</b> topilmadi.\n"
    "Kanal nomi to'g'ri ekanini va kanal ochiq ekanini tekshiring."
)

CHANNEL_BOT_NOT_ADMIN = (
    "❗️Bot <b>{channel}</b> kanalida administrator emas.\n\n"
    "Botni kanalga administrator qilib qo'shing, so'ng qayta urinib ko'ring. "
    "Aks holda bot kimning a'zo ekanini tekshira olmaydi."
)

CHANNEL_ADDED = "✅ <b>{channel}</b> qo'shildi. Endi {count} ta majburiy kanal bor."

CHANNEL_ALREADY = "ℹ️ <b>{channel}</b> allaqachon ro'yxatda."

CHANNEL_REMOVED = "🗑 <b>{channel}</b> o'chirildi. Qolgan kanallar: {count} ta."

CHANNEL_NOT_IN_LIST = "❗️<b>{channel}</b> ro'yxatda yo'q."

CHANNELS_CLEARED = "🗑 Barcha majburiy kanallar o'chirildi. Endi cheklov yo'q."

BTN_REMOVE_CHANNEL = "🗑 {channel}"

# --- Admin management ---------------------------------------------------------

MY_ID = (
    "🆔 Sizning Telegram ID raqamingiz:\n\n<code>{user_id}</code>\n\n"
    "Admin bo'lish uchun shu raqamni administratorga yuboring."
)

ADMINS_HEADER = "👮 <b>Adminlar</b> ({count} ta)\n"

ADMIN_ROW = "{index}. <code>{user_id}</code>{name} — {origin}"

ADMIN_ORIGINS = {
    "owner": "asosiy admin (o'chirib bo'lmaydi)",
    "env": "sozlamalardan (.env)",
    "runtime": "qo'shilgan",
}

ADMINS_USAGE = (
    "\n\n<b>Buyruqlar:</b>\n"
    "<code>/admin_qoshish 123456789</code> — admin qo'shish\n"
    "<code>/admin_ochirish 123456789</code> — adminni o'chirish\n\n"
    "ID raqamni bilish uchun o'sha odam botga <code>/id</code> buyrug'ini "
    "yuborsin. Yoki uning xabarini shu yerga forward qilib, javob sifatida "
    "<code>/admin_qoshish</code> yozing."
)

ADMIN_ADD_USAGE = (
    "Foydalanish: <code>/admin_qoshish 123456789</code>\n\n"
    "Yoki foydalanuvchining xabarini forward qiling va unga javob berib "
    "<code>/admin_qoshish</code> yozing."
)

ADMIN_REMOVE_USAGE = "Foydalanish: <code>/admin_ochirish 123456789</code>"

ADMIN_BAD_ID = (
    "❗️<code>{value}</code> — ID raqam noto'g'ri. Faqat raqam yuboring, "
    "masalan <code>123456789</code>."
)

ADMIN_FORWARD_HIDDEN = (
    "❗️Bu foydalanuvchi maxfiylik sozlamalari tufayli forward qilingan "
    "xabarda ko'rinmaydi. Undan <code>/id</code> buyrug'i orqali ID so'rang."
)

ADMIN_ADDED = "✅ <code>{user_id}</code> admin qilib qo'shildi. Jami {count} ta admin."

ADMIN_ALREADY = "ℹ️ <code>{user_id}</code> allaqachon admin."

ADMIN_REMOVED = "🗑 <code>{user_id}</code> adminlikdan olindi. Qolgan adminlar: {count} ta."

ADMIN_NOT_FOUND = "❗️<code>{user_id}</code> adminlar ro'yxatida yo'q."

ADMIN_CANNOT_REMOVE_OWNER = "❗️Asosiy adminni o'chirib bo'lmaydi."

ADMIN_CANNOT_REMOVE_ENV = (
    "❗️<code>{user_id}</code> <b>.env</b> faylidagi <code>ADMIN_IDS</code> "
    "orqali qo'shilgan. Uni o'chirish uchun serverdagi faylni tahrirlang."
)

ADMIN_NOTIFIED = (
    "🎉 Sizga admin huquqi berildi!\n\n"
    "/kanallar — majburiy kanallar\n"
    "/adminlar — adminlar ro'yxati\n"
    "/stats — statistika"
)

# --- Admin command list (/special) ---------------------------------------------

SPECIAL_HEADER = "🛡 <b>Admin buyruqlari</b>\n\n"

SPECIAL_ROW = "<code>{command}</code> — {description}"
