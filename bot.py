import os
import json
import logging
import requests
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackContext, 
    CallbackQueryHandler, MessageHandler, Filters
)
from flask import Flask

# تهيئة التطبيق
app = Flask(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# متغيرات البيئة
BOT_TOKEN = os.getenv('BOT_TOKEN')
DEVELOPER_USERNAME = os.getenv('DEVELOPER_USERNAME')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')
API_URL = "https://api.quran.com/api/v4"

# ملف المفضلة
FAVORITES_FILE = 'favorites.json'

# تحميل المفضلة
def load_favorites():
    try:
        with open(FAVORITES_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# حفظ المفضلة
def save_favorites(data):
    with open(FAVORITES_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ديكورات التحقق من الاشتراك
def check_subscription(func):
    @wraps(func)
    def wrapper(update: Update, context: CallbackContext):
        user_id = update.effective_user.id
        chat_member = context.bot.get_chat_member(CHANNEL_ID, user_id)
        
        if chat_member.status in ['left', 'kicked']:
            keyboard = [
                [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME}")],
                [InlineKeyboardButton("✅ تحقق", callback_data="check_subscription")]
            ]
            update.message.reply_text(
                "⛔️ يجب الاشتراك في القناة أولاً لاستخدام البوت",
                reply_markup=InlineKeyboardMarkup(keyboard)
            return
        return func(update, context)
    return wrapper

# --- معالجات البوت ---
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🕋 مرحباً {user.first_name} في بوت \"سُطورٌ من السَّماء ☁️\"\n"
             "رحلة روحانية تبدأ من هنا... استعرض، اقرأ، استمع، واحفظ آيات الله 💖",
        reply_markup=main_menu_keyboard()
    )

@check_subscription
def main_menu(update: Update, context: CallbackContext):
    update.message.reply_text(
        "اختر من القائمة:",
        reply_markup=main_menu_keyboard()
    )

def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 تصفّح السور", callback_data="browse_surahs")],
        [InlineKeyboardButton("🔍 البحث عن آية", callback_data="search_verse")],
        [InlineKeyboardButton("⭐ مفضلتي", callback_data="show_favorites")],
        [InlineKeyboardButton("🧑‍💻 المطور", url=f"https://t.me/{DEVELOPER_USERNAME}")]
    ])

# تصفح السور
def browse_surahs(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    response = requests.get(f"{API_URL}/chapters?language=ar")
    surahs = response.json()['chapters']
    
    keyboard = []
    for surah in surahs:
        keyboard.append([InlineKeyboardButton(
            f"{surah['id']}. {surah['name_arabic']} ({surah['name_simple']})",
            callback_data=f"surah_{surah['id']}"
        )])
    
    query.edit_message_text(
        text="📚 اختر سورة من القرآن الكريم:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# عرض سورة محددة
def show_surah(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    surah_id = query.data.split('_')[1]
    
    response = requests.get(f"{API_URL}/verses/by_chapter/{surah_id}?language=ar&text_type=uthmani_tajweed")
    verses = response.json()['verses']
    
    text = ""
    for i, verse in enumerate(verses):
        verse_text = f"{verse['verse_number']}. {verse['text_uthmani_tajweed']}\n"
        if len(text + verse_text) > 4000:
            send_verse_group(update, context, text, surah_id, verses[i-1]['verse_number'])
            text = ""
        text += verse_text
    
    if text:
        send_verse_group(update, context, text, surah_id, verses[-1]['verse_number'])

def send_verse_group(update: Update, context: CallbackContext, text: str, surah_id: int, last_verse: int):
    keyboard = [
        [
            InlineKeyboardButton("▶️ استمع", url=f"https://quran.com/{surah_id}"),
            InlineKeyboardButton("📌 أضف للمفضلة", callback_data=f"fav_surah_{surah_id}_{last_verse}")
        ]
    ]
    context.bot.send_message(
        chat_id=update.callback_query.message.chat_id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

# البحث عن آية
def search_verse(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    context.user_data['search_mode'] = True
    query.edit_message_text("🔍 أرسل الكلمة أو الجملة التي تريد البحث عنها:")

def handle_search(update: Update, context: CallbackContext):
    if not context.user_data.get('search_mode'):
        return
    
    search_term = update.message.text
    response = requests.get(f"{API_URL}/search?q={search_term}&size=5&language=ar")
    results = response.json()['search']['results']
    
    if not results:
        update.message.reply_text("⚠️ لم يتم العثور على نتائج")
        return
    
    for result in results:
        keyboard = [
            [
                InlineKeyboardButton("📘 تفسير", callback_data=f"tafsir_{result['verse_id']}"),
                InlineKeyboardButton("📌 أضف للمفضلة", callback_data=f"fav_{result['verse_id']}")
            ]
        ]
        update.message.reply_text(
            f"سورة {result['surah_name']} الآية {result['verse_number']}:\n\n{result['text']}",
            reply_markup=InlineKeyboardMarkup(keyboard)
    
    context.user_data['search_mode'] = False

# إدارة المفضلة
def add_favorite(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = str(query.from_user.id)
    
    if query.data.startswith('fav_'):
        verse_id = query.data.split('_')[1]
        response = requests.get(f"{API_URL}/verses/by_id/{verse_id}")
        verse = response.json()['verse']
        
        favorites = load_favorites()
        if user_id not in favorites:
            favorites[user_id] = []
        
        favorites[user_id].append({
            'verse_id': verse['id'],
            'surah_id': verse['chapter_id'],
            'verse_number': verse['verse_number'],
            'text': verse['text_uthmani']
        })
        
        save_favorites(favorites)
        query.edit_message_reply_markup(reply_markup=None)
        query.message.reply_text("💖 تمت إضافة الآية إلى المفضلة")

def show_favorites(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = str(query.from_user.id)
    favorites = load_favorites().get(user_id, [])
    
    if not favorites:
        query.edit_message_text("⭐ لم تقم بحفظ أي آيات بعد")
        return
    
    text = "⭐ آياتك المفضلة:\n\n"
    for fav in favorites:
        text += f"{fav['surah_id']}:{fav['verse_number']} - {fav['text']}\n\n"
    
    query.edit_message_text(text, reply_markup=favorites_keyboard(favorites))

def favorites_keyboard(favorites):
    keyboard = []
    for fav in favorites:
        keyboard.append([
            InlineKeyboardButton(
                f"❌ حذف {fav['surah_id']}:{fav['verse_number']}",
                callback_data=f"remove_{fav['verse_id']}"
            ),
            InlineKeyboardButton(
                "▶️ استمع",
                url=f"https://quran.com/{fav['surah_id']}/{fav['verse_number']}"
            )
        ])
    return InlineKeyboardMarkup(keyboard)

def remove_favorite(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user_id = str(query.from_user.id)
    verse_id = query.data.split('_')[1]
    
    favorites = load_favorites()
    if user_id in favorites:
        favorites[user_id] = [fav for fav in favorites[user_id] if fav['verse_id'] != int(verse_id)]
        save_favorites(favorites)
    
    query.edit_message_text("🗑 تم حذف الآية من المفضلة")

# التحقق من الاشتراك
def check_subscription_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    chat_member = context.bot.get_chat_member(CHANNEL_ID, user_id)
    
    if chat_member.status in ['member', 'administrator', 'creator']:
        start(update, context)
    else:
        query.answer("⛔️ لم تشترك بعد، يرجى الاشتراك أولاً")

# صفحة Ping
@app.route('/')
def ping():
    return "🕌 بوت \"سُطورٌ من السَّماء ☁️\" يعمل بنجاح 💫"

def main():
    # تهيئة البوت
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # معالجات الأوامر
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(browse_surahs, pattern="^browse_surahs$"))
    dp.add_handler(CallbackQueryHandler(search_verse, pattern="^search_verse$"))
    dp.add_handler(CallbackQueryHandler(show_favorites, pattern="^show_favorites$"))
    dp.add_handler(CallbackQueryHandler(show_surah, pattern="^surah_"))
    dp.add_handler(CallbackQueryHandler(add_favorite, pattern="^fav_"))
    dp.add_handler(CallbackQueryHandler(remove_favorite, pattern="^remove_"))
    dp.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_search))

    # تشغيل البوت
    if os.getenv('RENDER'):
        PORT = int(os.environ.get('PORT', 8080))
        updater.start_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"https://your-render-app.onrender.com/{BOT_TOKEN}"
        )
        app.run(host='0.0.0.0', port=PORT)
    else:
        updater.start_polling()
        updater.idle()

if __name__ == '__main__':
    main()
