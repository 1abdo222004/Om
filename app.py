import asyncio
import aiohttp
import random
import json
import requests
import re
import time
import threading
import os
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
import telebot
from telebot import types

# ========== إعدادات البوت ==========
TELEGRAM_TOKEN = "8102359893:AAEZUgzUtWN4xyjpApOjQ_ZA3Tv9NGssnF0"  # ضع توكن البوت الخاص بك هنا
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ========== إعدادات MovieFlow ==========
EMAIL_API = "https://api.mail.tm"
MOVIEFLOW_REGISTER_URL = "https://api.movieflow.ai/api/user_fission/register_with_invite"
MOVIEFLOW_ACTIVATE_URL = "https://api.movieflow.ai/auth/activate"
MOVIEFLOW_LOGIN_URL = "https://auth.movieflow.ai/api/user/login"
MOVIEFLOW_CREATE_URL = "https://api.movieflow.ai/movie/create_movie_project_v4"
MOVIEFLOW_STATUS_URL = "https://api.movieflow.ai/movie/get_tasks_status"

# ========== قاموس مؤقت للجلسات (بدون حفظ في ملفات) ==========
active_sessions = {}  # {chat_id: {'token': str, 'project_id': str, 'created_at': datetime}}

# ========== دوال إنشاء حساب MovieFlow ==========

def get_movieflow_token() -> Optional[str]:
    """
    دالة متكاملة للتسجيل في MovieFlow والحصول على التوكن
    """
    
    class TempEmailClient:
        def __init__(self):
            self.base_url = EMAIL_API
        
        async def create_account(self) -> Tuple[str, str]:
            async with aiohttp.ClientSession() as session:
                # الحصول على النطاق المتاح
                async with session.get(f"{self.base_url}/domains") as resp:
                    domains = await resp.json()
                    domain = domains["hydra:member"][0]["domain"]
                
                # إنشاء اسم مستخدم عشوائي
                username = ''.join(random.choice("abcdefghijklmnopqrstuvwxyz123456789") for _ in range(8))
                email = f"{username}@{domain}"
                password = "Pass123!@#"
                
                # إنشاء حساب البريد
                async with session.post(
                    f"{self.base_url}/accounts", 
                    json={"address": email, "password": password}
                ) as resp:
                    if resp.status not in [200, 201]:
                        raise Exception("Failed to create email account")
                
                # الحصول على توكن البريد
                async with session.post(
                    f"{self.base_url}/token", 
                    json={"address": email, "password": password}
                ) as resp:
                    if resp.status not in [200, 201]:
                        raise Exception("Failed to get email token")
                    token_data = await resp.json()
                
                return email, token_data["token"]
        
        async def get_messages(self, token: str) -> List[Dict]:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {token}"}
                async with session.get(f"{self.base_url}/messages", headers=headers) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    return data.get("hydra:member", [])
        
        async def get_message(self, token: str, msg_id: str) -> Dict:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {token}"}
                async with session.get(f"{self.base_url}/messages/{msg_id}", headers=headers) as resp:
                    if resp.status != 200:
                        return {}
                    return await resp.json()
    
    def sync_run_async(coro):
        """تشغيل دالة async بشكل متزامن"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    
    def register_movieflow(email: str) -> bool:
        """التسجيل في MovieFlow"""
        payload = {"password": "abdo2004", "email": email}
        headers = {
            'User-Agent': "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
            'Content-Type': "application/json",
            'origin': "https://www.movieflow.ai",
            'referer': "https://www.movieflow.ai/"
        }
        try:
            response = requests.post(MOVIEFLOW_REGISTER_URL, json=payload, headers=headers, timeout=30)
            return response.status_code in [200, 201, 204]
        except:
            return False
    
    def extract_token_from_email(message_data: Dict) -> Optional[str]:
        """استخراج توكن التفعيل من البريد"""
        try:
            # البحث في html content
            html_content = message_data.get('html', [''])[0]
            if isinstance(html_content, list):
                html_content = html_content[0] if html_content else ''
            
            # محاولة استخراج التوكن بأنماط مختلفة
            patterns = [
                r'token=([a-f0-9]{32})',
                r't=([a-f0-9]{32})',
                r'activation_token=([a-f0-9]{32})',
                r'[?&]t=([a-zA-Z0-9]+)',
                r'activate/([a-f0-9]{32})'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, html_content)
                if match:
                    return match.group(1)
            
            # البحث في النص العادي
            text_content = message_data.get('text', [''])[0]
            if isinstance(text_content, list):
                text_content = text_content[0] if text_content else ''
            
            for pattern in patterns:
                match = re.search(pattern, text_content)
                if match:
                    return match.group(1)
                    
        except Exception as e:
            pass
        return None
    
    def activate_account(activation_token: str) -> bool:
        """تفعيل الحساب"""
        payload = {"t": activation_token}
        headers = {
            'Content-Type': "application/json",
            'User-Agent': "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"
        }
        try:
            response = requests.post(MOVIEFLOW_ACTIVATE_URL, json=payload, headers=headers, timeout=30)
            return response.status_code in [200, 201, 204]
        except:
            return False
    
    def login_movieflow(email: str) -> Optional[str]:
        """تسجيل الدخول والحصول على التوكن"""
        payload = {"username": email, "password": "abdo2004"}
        headers = {
            'Content-Type': "application/json",
            'User-Agent': "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"
        }
        try:
            response = requests.post(MOVIEFLOW_LOGIN_URL, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json()
                # محاولة استخراج التوكن من مسارات مختلفة
                if isinstance(data, dict):
                    if 'token' in data:
                        return data['token']
                    elif 'data' in data and isinstance(data['data'], dict):
                        return data['data'].get('token')
                    elif 'access_token' in data:
                        return data['access_token']
            return None
        except:
            return None
    
    def wait_for_email(mail_token: str, timeout: int = 60) -> Optional[str]:
        """انتظار وصول البريد"""
        client = TempEmailClient()
        start = time.time()
        last_count = 0
        
        while time.time() - start < timeout:
            try:
                messages = sync_run_async(client.get_messages(mail_token))
                
                if len(messages) > last_count and messages:
                    msg = sync_run_async(client.get_message(mail_token, messages[0]["id"]))
                    activation_token = extract_token_from_email(msg)
                    if activation_token:
                        return activation_token
                
                last_count = len(messages)
            except:
                pass
            
            time.sleep(3)
        
        return None
    
    try:
        # إنشاء حساب بريد مؤقت
        client = TempEmailClient()
        email, mail_token = sync_run_async(client.create_account())
        
        if not email or not mail_token:
            return None
        
        # التسجيل في MovieFlow
        if not register_movieflow(email):
            return None
        
        # انتظار بريد التفعيل
        activation_token = wait_for_email(mail_token)
        if not activation_token:
            return None
        
        # تفعيل الحساب
        if not activate_account(activation_token):
            return None
        
        # تسجيل الدخول للحصول على التوكن
        login_token = login_movieflow(email)
        return login_token
            
    except Exception as e:
        return None


# ========== دوال إنشاء مشروع فيلم ==========

def create_movieflow_project(script_text: str, auth_token: str) -> Optional[str]:
    """
    دالة لإنشاء مشروع فيلم جديد في MovieFlow
    """
    url = MOVIEFLOW_CREATE_URL
    
    # تنظيف النص من علامات الاقتباس الزائدة
    clean_script = script_text.strip().strip('"\'')
    
    payload = {
        "script": clean_script,
        "mode": "auto",
        "resolution": "720p",
        "pre_step": False,
        "language": "arabic",
        "aspect_ratio": "VIDEO_ASPECT_RATIO_PORTRAIT",
        "expansion_mode": False,
        "video_duration": "1min",
        "use_img2video": False,
        "generation_type": "",
        "pcode": "",
        "confirm_deduct": True,
        "user_data": {
            "user_agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
            "is_mobile": 1
        }
    }

    headers = {
        'User-Agent': "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
        'Accept': "application/json, text/plain, */*",
        'Content-Type': "application/json",
        'authorization': f"Bearer {auth_token}",
        'origin': "https://www.movieflow.ai",
        'referer': "https://www.movieflow.ai/"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        
        if response.status_code not in [200, 201]:
            return None
        
        response_data = response.json()
        
        # محاولة استخراج project_id من مسارات مختلفة
        if isinstance(response_data, dict):
            if 'data' in response_data and isinstance(response_data['data'], dict):
                if 'project_id' in response_data['data']:
                    return response_data['data']['project_id']
                elif 'id' in response_data['data']:
                    return response_data['data']['id']
            elif 'project_id' in response_data:
                return response_data['project_id']
            elif 'id' in response_data:
                return response_data['id']
        
        return None
            
    except Exception as e:
        return None


# ========== دوال جلب روابط الفيديوهات ==========

def get_movieflow_videos(project_id: str, auth_token: str) -> List[str]:
    """
    دالة لجلب روابط الفيديوهات من مشروع MovieFlow
    """
    def extract_videos_simple(text):
        """استخراج روابط الفيديو من النص"""
        # البحث عن روابط mp4
        pattern = r'https?://[^\s"\']+\.mp4[^\s"\']*'
        urls = re.findall(pattern, text)
        
        # البحث عن روابط الفيديو في JSON
        json_pattern = r'"video_url"\s*:\s*"([^"]+)"'
        json_urls = re.findall(json_pattern, text)
        
        # دمج وإزالة التكرار
        all_urls = urls + json_urls
        unique_urls = []
        for url in all_urls:
            # تنظيف الرابط
            clean_url = url.replace('\\/', '/').strip()
            if clean_url not in unique_urls and '.mp4' in clean_url:
                unique_urls.append(clean_url)
        
        return unique_urls
    
    params = {'project_id': project_id}
    
    headers = {
        'User-Agent': "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
        'Accept': "application/json",
        'authorization': f"Bearer {auth_token}",
        'origin': "https://www.movieflow.ai",
        'referer': "https://www.movieflow.ai/"
    }
    
    try:
        response = requests.get(MOVIEFLOW_STATUS_URL, params=params, headers=headers, timeout=30)
        
        if response.status_code != 200:
            return []
        
        urls = extract_videos_simple(response.text)
        
        # محاولة استخراج من JSON إذا كان الرد JSON
        try:
            data = response.json()
            if isinstance(data, dict):
                # محاولة استخراج من مسارات مختلفة
                if 'data' in data and isinstance(data['data'], dict):
                    if 'videos' in data['data'] and isinstance(data['data']['videos'], list):
                        for video in data['data']['videos']:
                            if isinstance(video, dict) and 'url' in video:
                                urls.append(video['url'])
                elif 'videos' in data and isinstance(data['videos'], list):
                    for video in data['videos']:
                        if isinstance(video, str) and '.mp4' in video:
                            urls.append(video)
                        elif isinstance(video, dict) and 'url' in video:
                            urls.append(video['url'])
        except:
            pass
        
        # إزالة التكرار
        unique_urls = []
        for url in urls:
            if url not in unique_urls:
                unique_urls.append(url)
        
        return unique_urls
        
    except Exception as e:
        return []


# ========== دوال معالجة الفيديو ==========

def process_video_creation(chat_id: int, script_text: str):
    """
    دالة معالجة إنشاء الفيديو (تعمل في thread منفصل)
    """
    try:
        # تحديث رسالة الحالة
        bot.send_message(chat_id, "🔄 جاري إنشاء حساب جديد...")
        
        # 1. إنشاء حساب جديد
        token = get_movieflow_token()
        if not token:
            bot.send_message(chat_id, "❌ فشل إنشاء حساب جديد")
            return
        
        # حفظ التوكن في الجلسة المؤقتة
        if chat_id not in active_sessions:
            active_sessions[chat_id] = {}
        active_sessions[chat_id]['token'] = token
        
        # 2. إنشاء المشروع
        bot.send_message(chat_id, "✅ تم إنشاء الحساب بنجاح!\n🔄 جاري إنشاء المشروع...")
        
        project_id = create_movieflow_project(script_text, token)
        if not project_id:
            bot.send_message(chat_id, "❌ فشل إنشاء المشروع")
            return
        
        # حفظ project_id في الجلسة
        active_sessions[chat_id]['project_id'] = project_id
        active_sessions[chat_id]['created_at'] = datetime.now()
        
        # 3. إرسال رسالة مع مؤقت 10 دقائق
        msg = bot.send_message(
            chat_id, 
            f"✅ تم إنشاء المشروع بنجاح!\n"
            f"📋 معرف المشروع: {project_id}\n\n"
            f"⏳ جاري معالجة الفيديو... سيتم إعلامك بعد 10 دقائق.\n"
            f"🕐 الوقت: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        # 4. انتظار 10 دقائق (600 ثانية)
        total_wait = 600  # 10 دقائق
        interval = 60  # تحديث كل دقيقة
        
        for remaining in range(total_wait, 0, -interval):
            time.sleep(interval)
            minutes_left = remaining // 60
            try:
                # تحديث الرسالة
                bot.edit_message_text(
                    f"✅ تم إنشاء المشروع بنجاح!\n"
                    f"📋 معرف المشروع: {project_id}\n\n"
                    f"⏳ جاري معالجة الفيديو... {minutes_left} دقيقة متبقية\n"
                    f"🕐 الوقت: {datetime.now().strftime('%H:%M:%S')}",
                    chat_id,
                    msg.message_id
                )
            except:
                pass  # تجاهل أخطاء التعديل
        
        # 5. بعد 10 دقائق، جلب الروابط
        try:
            bot.edit_message_text(
                f"✅ تم إنشاء المشروع بنجاح!\n"
                f"📋 معرف المشروع: {project_id}\n\n"
                f"🔍 جاري البحث عن روابط الفيديو...",
                chat_id,
                msg.message_id
            )
        except:
            pass
        
        # محاولة جلب الفيديوهات عدة مرات
        videos = []
        max_attempts = 5
        for attempt in range(max_attempts):
            videos = get_movieflow_videos(project_id, token)
            if videos:
                break
            if attempt < max_attempts - 1:
                time.sleep(5)  # انتظار 5 ثواني بين المحاولات
        
        # 6. إرسال النتائج
        if videos:
            # الحصول على الرابط رقم 9 (إذا وجد) أو آخر رابط
            target_url = None
            if len(videos) >= 9:
                target_url = videos[8]  # الرقم 9 (index 8)
                bot.send_message(chat_id, f"✅ تم العثور على الرابط رقم 9:\n{target_url}")
            else:
                # إذا لم يوجد رابط 9، نأخذ آخر رابط
                target_url = videos[-1]
                bot.send_message(chat_id, f"⚠️ لم يتم العثور على الرابط رقم 9، تم إرسال آخر رابط:\n{target_url}")
            
            # إرسال الفيديو
            if target_url:
                try:
                    bot.send_video(chat_id, target_url, caption="🎥 هذا هو الفيديو المطلوب")
                except Exception as e:
                    bot.send_message(chat_id, f"❌ فشل إرسال الفيديو، الرابط: {target_url}")
        else:
            bot.send_message(
                chat_id, 
                f"❌ لم يتم العثور على روابط فيديو بعد 10 دقائق.\n"
                f"قد تحتاج إلى الانتظار أكثر أو فشلت المعالجة.\n"
                f"معرف المشروع: {project_id}"
            )
        
        # تنظيف الجلسة بعد الانتهاء (اختياري - يمكنك إبقائها للاستخدام لاحقاً)
        # del active_sessions[chat_id]
            
    except Exception as e:
        bot.send_message(chat_id, f"❌ حدث خطأ: {str(e)}")


# ========== أوامر البوت ==========

@bot.message_handler(commands=['start'])
def start_command(message):
    """رسالة الترحيب"""
    username = message.from_user.first_name
    
    welcome_text = (
        f"🎬 مرحباً {username} في بوت MovieFlow!\n\n"
        "هذا البوت يساعدك في إنشاء فيديوهات باستخدام MovieFlow AI.\n\n"
        "📌 الأوامر المتاحة:\n"
        "/start - عرض هذه الرسالة\n"
        "/help - مساعدة\n"
        "/create <النص> - إنشاء فيديو جديد\n"
        "/status - عرض حالة الجلسة الحالية\n\n"
        "✨ طريقة الاستخدام:\n"
        "أرسل الأمر /create متبوعاً بنص السيناريو الذي تريده\n"
        "مثال: /create قصة عن مغامرة في الفضاء\n\n"
        "ملاحظة: كل جلسة تستخدم توكن جديد ولا يتم حفظ أي بيانات!"
    )
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_create = types.KeyboardButton("🎬 إنشاء فيديو")
    btn_status = types.KeyboardButton("📊 حالة الجلسة")
    btn_help = types.KeyboardButton("❓ مساعدة")
    markup.add(btn_create, btn_status, btn_help)
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)


@bot.message_handler(commands=['help'])
def help_command(message):
    """مساعدة"""
    help_text = (
        "❓ مساعدة البوت\n\n"
        "الأوامر:\n"
        "/start - بدء البوت\n"
        "/create [النص] - إنشاء فيديو جديد\n"
        "  مثال: /create قصة عن رحلة فضائية\n"
        "/status - عرض حالة الجلسة الحالية\n\n"
        "مميزات البوت:\n"
        "• كل جلسة تستخدم توكن جديد (لا يتم حفظ أي بيانات)\n"
        "• مدة الانتظار بعد إنشاء الفيديو: 10 دقائق\n"
        "• يتم إرسال الرابط رقم 9 فقط (أو آخر رابط إذا لم يوجد)\n"
        "• يتم إرسال الفيديو مباشرة\n\n"
        "الأزرار:\n"
        "🎬 إنشاء فيديو - لإنشاء فيديو جديد\n"
        "📊 حالة الجلسة - عرض معلومات الجلسة الحالية\n"
        "❓ مساعدة - عرض هذه المساعدة"
    )
    bot.send_message(message.chat.id, help_text)


@bot.message_handler(commands=['status'])
def status_command(message):
    """عرض حالة الجلسة الحالية"""
    chat_id = message.chat.id
    
    if chat_id in active_sessions:
        session = active_sessions[chat_id]
        status_text = "📊 حالة الجلسة الحالية:\n\n"
        
        if 'token' in session:
            status_text += f"🔑 التوكن: {session['token'][:20]}...\n"
        if 'project_id' in session:
            status_text += f"📋 معرف المشروع: {session['project_id']}\n"
        if 'created_at' in session:
            status_text += f"🕐 وقت الإنشاء: {session['created_at'].strftime('%Y-%m-%d %H:%M:%S')}\n"
    else:
        status_text = "📭 لا توجد جلسة نشطة حالياً.\nاستخدم /create لإنشاء فيديو جديد."
    
    bot.send_message(chat_id, status_text)


@bot.message_handler(commands=['create'])
def create_command(message):
    """إنشاء فيديو جديد"""
    # استخراج النص من الأمر
    text = message.text.replace('/create', '', 1).strip()
    
    if not text:
        bot.send_message(
            message.chat.id, 
            "❌ يرجى إرسال نص السيناريو.\n"
            "مثال: /create قصة عن مغامرة في الغابة"
        )
        return
    
    chat_id = message.chat.id
    
    # إرسال تأكيد
    bot.send_message(
        chat_id,
        f"✅ تم استلام طلبك!\n"
        f"📝 النص: {text[:100]}...\n\n"
        f"🔄 جاري تجهيز الفيديو..."
    )
    
    # تشغيل المعالجة في thread منفصل
    thread = threading.Thread(
        target=process_video_creation,
        args=(chat_id, text)
    )
    thread.daemon = True
    thread.start()


# ========== معالج الرسائل النصية ==========

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    """معالج الرسائل النصية"""
    text = message.text
    
    if text == "🎬 إنشاء فيديو":
        bot.send_message(
            message.chat.id,
            "📝 أرسل نص السيناريو الذي تريد تحويله إلى فيديو:"
        )
        bot.register_next_step_handler(message, handle_script_input)
    
    elif text == "📊 حالة الجلسة":
        status_command(message)
    
    elif text == "❓ مساعدة":
        help_command(message)
    
    else:
        bot.send_message(
            message.chat.id,
            "❓ أمر غير معروف. استخدم /help لعرض الأوامر المتاحة."
        )


def handle_script_input(message):
    """معالج إدخال نص السيناريو"""
    script_text = message.text.strip()
    
    if len(script_text) < 10:
        bot.send_message(
            message.chat.id,
            "❌ النص قصير جداً. يرجى إرسال نص أطول (على الأقل 10 أحرف)."
        )
        return
    
    # إنشاء الفيديو
    chat_id = message.chat.id
    
    bot.send_message(
        chat_id,
        f"✅ تم استلام النص!\n"
        f"🔄 جاري تجهيز الفيديو..."
    )
    
    thread = threading.Thread(
        target=process_video_creation,
        args=(chat_id, script_text)
    )
    thread.daemon = True
    thread.start()


# ========== تنظيف الجلسات القديمة (اختياري) ==========
def cleanup_old_sessions():
    """تنظيف الجلسات الأقدم من ساعتين"""
    while True:
        try:
            now = datetime.now()
            to_delete = []
            
            for chat_id, session in active_sessions.items():
                if 'created_at' in session:
                    age = now - session['created_at']
                    if age.total_seconds() > 7200:  # ساعتين
                        to_delete.append(chat_id)
            
            for chat_id in to_delete:
                del active_sessions[chat_id]
                
        except:
            pass
        
        time.sleep(3600)  # تنظيف كل ساعة


# ========== تشغيل البوت ==========

if __name__ == "__main__":
    print("🤖 بوت MovieFlow يعمل...")
    print("⏳ انتظر قليلاً...")
    print("✅ مميزات البوت:")
    print("   - كل جلسة بتوكن جديد (بدون حفظ)")
    print("   - إرسال الرابط رقم 9 فقط")
    print("   - إرسال الفيديو مباشرة")
    
    # تشغيل thread تنظيف الجلسات
    cleanup_thread = threading.Thread(target=cleanup_old_sessions, daemon=True)
    cleanup_thread.start()
    
    # تشغيل البوت
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"❌ خطأ في تشغيل البوت: {e}")
            time.sleep(5)
