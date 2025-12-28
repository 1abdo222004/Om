import os
import telebot
from nsfw_detector import predict
from nsfw_detector import model as nsfw_model
from PIL import Image

# ================== الإعدادات ==================
BOT_TOKEN = "7157763965:AAG4Dv2nOc5USx4qsX3n4L6pQteVXojFYeg"
MODEL_PATH = "nsfw_mobilenet2.224x224.h5"
NSFW_THRESHOLD = 0.7
TMP_DIR = "tmp"
# ==============================================

bot = telebot.TeleBot(BOT_TOKEN)

# إنشاء مجلد مؤقت للصور
os.makedirs(TMP_DIR, exist_ok=True)

# تحميل الموديل إذا لم يكن موجود
if not os.path.exists(MODEL_PATH):
    print("❗ موديل NSFW غير موجود. جاري التحميل...")
    nsfw_model.download(MODEL_PATH)
    print("✅ تم تنزيل الموديل بنجاح.")

# تحميل الموديل
print("🔹 جاري تحميل الموديل...")
nsfw_model_loaded = predict.load_model(MODEL_PATH)
print("✅ الموديل جاهز للعمل.")

# ==============================================
def is_nsfw(image_path):
    result = predict.classify(nsfw_model_loaded, image_path)
    scores = result[image_path]

    nsfw_score = scores.get("porn", 0) + scores.get("sexy", 0)
    return nsfw_score >= NSFW_THRESHOLD

# التعامل مع الصور
@bot.message_handler(content_types=["photo"])
def check_photo(message):
    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)

    img_path = f"{TMP_DIR}/{file_id}.jpg"
    downloaded = bot.download_file(file_info.file_path)
    with open(img_path, "wb") as f:
        f.write(downloaded)

    if is_nsfw(img_path):
        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.send_message(message.chat.id, "🚫 تم حذف صورة غير لائقة")
        except Exception as e:
            print(f"خطأ عند الحذف: {e}")

    os.remove(img_path)

# أمر البداية
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(message.chat.id, "🤖 بوت حماية NSFW يعمل تلقائيًا على الصور.")

# تشغيل البوت
print("🟢 البوت يعمل الآن...")
bot.infinity_polling()
