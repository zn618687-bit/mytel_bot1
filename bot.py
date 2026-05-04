#!/usr/bin/env python3
"""
Spirit Bot – Optimized (Async HTTP + Cleaner UI)
"""

import asyncio, logging, json, os, random, time, base64, httpx
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone as pytz_timezone

# ================== CONFIGURATION ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8665830485:AAEAmqvi8c43axiaAgKJ0D9W2QchPg24Y9Q")
ADMIN_ID = 7712004950
LOG_CHANNEL_ID = 7712004950
FORCE_JOIN_CHANNEL = "@MytelAtom_Hub"

MYTEL_OTP_URL = "https://apis.mytel.com.mm/myid/authen/v1.0/login/method/otp/get-otp"
MYTEL_VALIDATE_URL = "https://apis.mytel.com.mm/myid/authen/v1.0/login/method/otp/validate-otp"

MW_BASE_URL = "http://api.magicwheel.com.mm/v1"
MW_SSO_LOGIN = "/users/login"
MW_GET_HEART = "/users/get-heart"
MW_GET_INFO  = "/users/info"
MW_MISSIONS  = "/missions"
MW_RECEIVE   = "/missions/receive"

ACCOUNTS_FILE = "spirit_bot_accounts.json"
PROXIES_FILE  = "proxies.txt"

MMT = timezone(timedelta(hours=6, minutes=30))

HEADERS_TEMPLATE = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "language": "my",
    "Origin": "http://magicwheel.com.mm",
    "X-Requested-With": "com.android.browser",
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36",
}

# ================== LOGGING ==================
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== PROXY ==================
def load_proxies() -> List[str]:
    if not os.path.exists(PROXIES_FILE):
        return []
    with open(PROXIES_FILE, "r") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

PROXY_LIST = load_proxies()

def get_random_proxy() -> Optional[str]:
    if not PROXY_LIST:
        return None
    return random.choice(PROXY_LIST)

# ================== STORAGE ==================
def load_accounts() -> Dict[str, List[Dict[str, Any]]]:
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_accounts(accounts: Dict[str, List[Dict[str, Any]]]):
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)

# ================== JWT (Magic Wheel token) ==================
def decode_jwt(token: str) -> Optional[Dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4 if len(payload_b64) % 4 else 0
        payload_b64 += "=" * padding
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return None

def token_expired(token: str) -> bool:
    payload = decode_jwt(token)
    if not payload or "exp" not in payload:
        return True
    return payload["exp"] < (int(time.time()) + 60)

# ================== ASYNC API CALLS ==================
async def api_call(method, url, headers=None, json_data=None, timeout=20):
    proxy = get_random_proxy()
    proxies = {"http://": proxy, "https://": proxy} if proxy else None
    
    async with httpx.AsyncClient(proxies=proxies, timeout=timeout, follow_redirects=True) as client:
        try:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            else:
                resp = await client.post(url, headers=headers, json=json_data)
            
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                return resp.status_code, resp.json()
            else:
                return resp.status_code, resp.text
        except Exception as e:
            logger.error(f"API Error ({url}): {e}")
            return None, str(e)

async def mytel_get_otp(phone: str):
    url = f"{MYTEL_OTP_URL}?phoneNumber={phone}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36",
        "accept": "*/*",
        "x-requested-with": "com.mycomapny.mywebapp",
    }
    return await api_call("GET", url, headers=headers)

async def mytel_validate_otp(phone: str, otp: str):
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36",
        "accept": "*/*",
        "x-requested-with": "com.mycomapny.mywebapp",
    }
    data = {
        "phoneNumber": phone,
        "password": otp,
        "appVersion": "1.0.93",
        "buildVersionApp": "217",
        "deviceId": "0",
        "imei": "0",
        "os": "Web",
        "osAp": "Web",
        "version": "1.2"
    }
    return await api_call("POST", MYTEL_VALIDATE_URL, headers=headers, json_data=data)

async def magicwheel_sso_login(isdn: str, mytel_token: str):
    url = MW_BASE_URL + MW_SSO_LOGIN
    headers = HEADERS_TEMPLATE.copy()
    body = {"isdn": isdn, "tokenEncoded": mytel_token}
    return await api_call("POST", url, headers=headers, json_data=body)

async def magicwheel_api_get(path, access_token):
    url = MW_BASE_URL + path
    headers = HEADERS_TEMPLATE.copy()
    headers["Authorization"] = f"Bearer {access_token}"
    return await api_call("GET", url, headers=headers)

async def magicwheel_api_post(path, access_token, json_data):
    url = MW_BASE_URL + path
    headers = HEADERS_TEMPLATE.copy()
    headers["Authorization"] = f"Bearer {access_token}"
    return await api_call("POST", url, headers=headers, json_data=json_data)

# ================== HELPERS ==================
async def ensure_magic_token(acc: dict) -> bool:
    magic_token = acc.get("magic_token")
    if not magic_token or token_expired(magic_token):
        mytel_token = acc.get("mytel_access_token")
        if not mytel_token:
            return False
        code, resp = await magicwheel_sso_login(acc["phone"], mytel_token)
        if code and 200 <= code < 300 and isinstance(resp, dict) and resp.get("success"):
            data = resp["data"]
            acc["magic_token"] = data["accessToken"]
            acc["magic_token_time"] = int(time.time())
            acc["user_info"] = data.get("user", acc.get("user_info", {}))
            return True
        return False
    return True

async def edit_or_send(msg, text, reply_markup=None):
    try:
        if msg.text == text and msg.reply_markup == reply_markup:
            return msg
        return await msg.edit_text(text=text, reply_markup=reply_markup)
    except Exception:
        return await msg.reply_text(text=text, reply_markup=reply_markup)

async def delete_msg_safe(context, chat_id, msg_id):
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except:
        pass

# ================== FORCE JOIN ==================
async def is_user_member(context, user_id) -> bool:
    try:
        chat_member = await context.bot.get_chat_member(chat_id=FORCE_JOIN_CHANNEL, user_id=user_id)
        return chat_member.status in ["creator", "administrator", "member"]
    except TelegramError:
        return False

async def force_join_prompt(context, chat_id):
    await context.bot.send_message(
        chat_id=chat_id,
        text="⚠️ @MytelAtom_Hub ကို Join ထားရန် လိုအပ်ပါသည်।\n\nJoin ပြီးပါက ✅ Join ပြီးပြီ ကိုနှိပ်ပါ။",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url="https://t.me/MytelAtom_Hub")],
            [InlineKeyboardButton("✅ Join ပြီးပြီ", callback_data="verify_join")]
        ])
    )

# ================== KEYBOARDS ==================
def main_menu_keyboard():
    kb = [
        [InlineKeyboardButton("➕ Add Account", callback_data="add_account"),
         InlineKeyboardButton("📱 Profile", callback_data="menu_accounts")]
    ]
    return InlineKeyboardMarkup(kb)

def account_list_keyboard(accounts):
    kb = []
    for i, acc in enumerate(accounts):
        phone = acc["phone"]
        kb.append([InlineKeyboardButton(phone, callback_data=f"select_{i}")])
    kb.append([InlineKeyboardButton("➕ Add Account", callback_data="add_account")])
    kb.append([InlineKeyboardButton("🔙 Main Menu", callback_data="back_main")])
    return InlineKeyboardMarkup(kb)

# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_member(context, user_id):
        await force_join_prompt(context, user_id)
        return
    
    context.user_data.clear()
    await update.message.reply_text(
        "⚡ Spirit Wheel\n\nအောက်ပါတစ်ခုခုကို ရွေးပါ။",
        reply_markup=main_menu_keyboard()
    )

async def verify_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if await is_user_member(context, user_id):
        await edit_or_send(query.message, "⚡ Spirit Wheel\n\nအောက်ပါတစ်ခုခုကို ရွေးပါ။", reply_markup=main_menu_keyboard())
    else:
        try:
            msg = await context.bot.send_message(chat_id=user_id, text="ကျေးဇူးပြု၍ Channel အရင် Join ပါ")
            context.job_queue.run_once(lambda _: asyncio.create_task(delete_msg_safe(context, user_id, msg.message_id)), when=3)
        except: pass

async def membership_guard(update, context) -> bool:
    user_id = update.effective_user.id
    if not await is_user_member(context, user_id):
        if update.callback_query:
            await update.callback_query.answer("Join @MytelAtom_Hub first!", show_alert=True)
        else:
            await force_join_prompt(context, user_id)
        return False
    return True

# ============== ADD ACCOUNT ==============
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await membership_guard(update, context): return
    query = update.callback_query
    if query: await query.answer()
    
    context.user_data["state"] = "phone"
    context.user_data["menu_msg_id"] = query.message.message_id
    
    await edit_or_send(query.message, "📱 ဖုန်းနံပါတ် (09xxxxxxxxx) ပို့ပါ။",
                       reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ပယ်ဖျက်", callback_data="cancel_add")]]))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    if not await membership_guard(update, context): return
    
    state = context.user_data.get("state")
    if not state: return
    
    text = update.message.text.strip()
    # Always delete user's input message immediately
    await delete_msg_safe(context, chat_id, update.message.message_id)
    
    menu_msg_id = context.user_data.get("menu_msg_id")
    
    if state == "phone":
        if not (text.startswith("09") and text.isdigit() and len(text) == 11):
            temp = await update.message.reply_text("❌ ဖုန်းနံပါတ် မှားယွင်းနေပါသည်။")
            context.job_queue.run_once(lambda _: asyncio.create_task(delete_msg_safe(context, chat_id, temp.message_id)), when=3)
            return
        
        phone = text
        context.user_data["phone"] = phone
        
        # Update menu message to show loading or progress
        if menu_msg_id:
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=menu_msg_id, text="⏳ OTP တောင်းဆိုနေပါသည်...")
            except: pass
            
        code, resp = await mytel_get_otp(phone)
        if code and (isinstance(resp, dict) and int(resp.get("errorCode", 0)) == 200):
            context.user_data["state"] = "otp"
            if menu_msg_id:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=menu_msg_id,
                    text="🔑 OTP ပို့ပြီးပါပြီ။ OTP ကုဒ် (၆ လုံး) ပို့ပါ။",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ပယ်ဖျက်", callback_data="cancel_add")]])
                )
        else:
            error_msg = f"❌ OTP တောင်း၍မရပါ။ {resp}"
            if menu_msg_id:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=menu_msg_id, text=error_msg)
                context.job_queue.run_once(lambda _: asyncio.create_task(back_to_main_from_error(context, chat_id, menu_msg_id, user_id)), when=5)
            context.user_data.clear()

    elif state == "otp":
        otp = text
        phone = context.user_data.get("phone")
        if not phone:
            context.user_data.clear()
            return
            
        if menu_msg_id:
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=menu_msg_id, text="⏳ OTP စစ်ဆေးနေပါသည်...")
            except: pass
            
        code, resp = await mytel_validate_otp(phone, otp)
        if (code and isinstance(resp, dict) and
            int(resp.get("errorCode", 0)) == 200 and resp.get("result") and resp["result"].get("access_token")):
            
            result = resp["result"]
            mytel_token = result["access_token"]
            mytel_refresh = result.get("refresh_token")
            
            sso_code, sso_resp = await magicwheel_sso_login(phone, mytel_token)
            if (sso_code and 200 <= sso_code < 300 and isinstance(sso_resp, dict) and sso_resp.get("success")):
                data = sso_resp["data"]
                account = {
                    "phone": phone,
                    "mytel_access_token": mytel_token,
                    "mytel_refresh_token": mytel_refresh,
                    "magic_token": data["accessToken"],
                    "magic_token_time": int(time.time()),
                    "user_info": data.get("user", {}),
                }
                all_acc = load_accounts()
                user_accs = all_acc.get(user_id, [])
                # Avoid duplicates
                user_accs = [a for a in user_accs if a["phone"] != phone]
                user_accs.append(account)
                all_acc[user_id] = user_accs
                save_accounts(all_acc)
                
                success_text = (
                    f"✅ အကောင့် ချိတ်ဆက်ပြီးပါပြီ။\n"
                    f"📱 {phone}\n"
                    f"⚡Auto claim active\n"
                    f"🕐 12:05 AM auto\n\n"
                    f"3 စက္ကန့်အကြာ ပင်မ Menu ပြန်ပြောင်းပါမည်..."
                )
                
                if menu_msg_id:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=menu_msg_id, text=success_text)
                    context.job_queue.run_once(lambda _: asyncio.create_task(back_to_main_from_success(context, chat_id, menu_msg_id, user_id)), when=3)
                context.user_data.clear()
            else:
                if menu_msg_id:
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=menu_msg_id, text="❌ Magic Wheel SSO ဝင်မရပါ။")
                    context.job_queue.run_once(lambda _: asyncio.create_task(back_to_main_from_error(context, chat_id, menu_msg_id, user_id)), when=5)
        else:
            if menu_msg_id:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=menu_msg_id, text=f"❌ OTP အတည်မပြုနိုင်ပါ။ {resp}")
                context.job_queue.run_once(lambda _: asyncio.create_task(back_to_main_from_error(context, chat_id, menu_msg_id, user_id)), when=5)

async def back_to_main_from_success(context, chat_id, msg_id, user_id):
    await context.bot.edit_message_text(
        chat_id=chat_id, message_id=msg_id,
        text="⚡ Spirit Wheel\n\nအောက်ပါတစ်ခုခုကို ရွေးပါ။",
        reply_markup=main_menu_keyboard()
    )

async def back_to_main_from_error(context, chat_id, msg_id, user_id):
    await context.bot.edit_message_text(
        chat_id=chat_id, message_id=msg_id,
        text="⚡ Spirit Wheel\n\nအောက်ပါတစ်ခုခုကို ရွေးပါ။",
        reply_markup=main_menu_keyboard()
    )

async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await edit_or_send(query.message, "⚡ Spirit Wheel\n\nအောက်ပါတစ်ခုခုကို ရွေးပါ။", reply_markup=main_menu_keyboard())

# ================== PROFILE HANDLERS ==================
async def menu_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    if not await membership_guard(update, context): return
    accounts = load_accounts().get(user_id, [])
    if not accounts:
        await edit_or_send(query.message, "အကောင့်မရှိသေးပါ။", reply_markup=main_menu_keyboard())
        return
    await edit_or_send(query.message, "📱 ကျွန်ုပ်၏အကောင့်များ", reply_markup=account_list_keyboard(accounts))

async def select_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(update.effective_user.id)
    if not await membership_guard(update, context): return
    data = query.data
    idx = int(data.split("_")[1])
    all_acc = load_accounts()
    accounts = all_acc.get(user_id, [])
    if idx < 0 or idx >= len(accounts):
        return
    acc = accounts[idx]
    phone = acc["phone"]
    
    await edit_or_send(query.message, f"⏳ {phone} ၏ အချက်အလက်များကို ရယူနေပါသည်...")
    
    if not await ensure_magic_token(acc):
        await query.answer("Token expired. Please re-add account.", show_alert=True)
        return
        
    _, info_resp = await magicwheel_api_get(MW_GET_INFO, acc["magic_token"])
    point = info_resp["data"]["point"] if (isinstance(info_resp, dict) and info_resp.get("success")) else acc.get("user_info", {}).get("point", "?")
    _, heart_resp = await magicwheel_api_get(MW_GET_HEART, acc["magic_token"])
    heart = heart_resp["data"]["heart"] if (isinstance(heart_resp, dict) and heart_resp.get("success")) else "?"
    
    acc["user_info"]["point"] = point
    save_accounts(all_acc)

    text = f"⚡ My Profile\n━━━━━━━━━━━━━━\n📱 {phone}\n⭐ Points: {point}\n❤️ Hearts: {heart}\n━━━━━━━━━━━━━━"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Account List", callback_data="menu_accounts")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="back_main")]
    ])
    await edit_or_send(query.message, text, reply_markup=keyboard)

# ================== BUTTON HANDLER ==================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = str(update.effective_user.id)
    
    if data == "verify_join":
        await verify_join(update, context)
        return
    if not await membership_guard(update, context): 
        await query.answer()
        return

    if data == "add_account":
        await add_account_start(update, context)
    elif data == "menu_accounts":
        await menu_accounts(update, context)
    elif data.startswith("select_"):
        await select_account(update, context)
    elif data == "cancel_add":
        await cancel_add(update, context)
    elif data == "back_main":
        await edit_or_send(query.message, "⚡ Spirit Wheel\n\nအောက်ပါတစ်ခုခုကို ရွေးပါ။", reply_markup=main_menu_keyboard())
    else:
        await query.answer()

# ================== AUTO CLAIM SCHEDULER ==================
async def auto_claim_all_accounts(app: Application):
    logger.info("Auto claim for all accounts starting...")
    all_acc = load_accounts()
    for uid_str, acc_list in all_acc.items():
        chat_id = int(uid_str)
        for acc in acc_list:
            phone = acc["phone"]
            try:
                if not await ensure_magic_token(acc):
                    continue
                _, missions_resp = await magicwheel_api_get(MW_MISSIONS, acc["magic_token"])
                if not (isinstance(missions_resp, dict) and missions_resp.get("success")):
                    continue
                missions = missions_resp["data"]
                checkin = next((m for m in missions if m.get("id") == 1), None)
                if not checkin or checkin.get("status") == 2:
                    continue
                
                _, claim_resp = await magicwheel_api_post(MW_RECEIVE, acc["magic_token"], {"idMission": 1})
                if isinstance(claim_resp, dict) and claim_resp.get("success"):
                    hearts_earned = claim_resp["data"]["heart"]
                    _, heart_resp = await magicwheel_api_get(MW_GET_HEART, acc["magic_token"])
                    total_heart = heart_resp["data"]["heart"] if (isinstance(heart_resp, dict) and heart_resp.get("success")) else hearts_earned
                    text = (
                        f"✅ Auto Check-in\n\n"
                        f"📱 {phone} အတွက် နေ့စဥ် Heart ယူပြီးပါပြီ।\n\n"
                        f"🎁 ယနေ့ရရှိသည့်အသဲ: +{hearts_earned}❤️\n"
                        f"💰 စုစုပေါင်းအသဲ: {total_heart}"
                    )
                    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Delete this message", callback_data="delete_auto_msg")]])
                    await app.bot.send_message(chat_id, text, reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Auto claim error for {phone}: {e}")
    save_accounts(all_acc)
    if LOG_CHANNEL_ID:
        try: await app.bot.send_message(LOG_CHANNEL_ID, "✅ Auto claim completed.")
        except: pass

async def delete_auto_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try: await query.message.delete()
    except: pass

def start_scheduler(application):
    scheduler = AsyncIOScheduler(timezone=pytz_timezone("Asia/Yangon"))
    scheduler.add_job(auto_claim_all_accounts, CronTrigger(hour=0, minute=5), args=[application])
    scheduler.start()
    logger.info("Scheduler started for 12:05 AM auto claim.")

# ================== ERROR HANDLER ==================
async def error_handler(update, context):
    logger.error(msg="Exception:", exc_info=context.error)
    if ADMIN_ID:
        try: await context.bot.send_message(ADMIN_ID, f"Bot error: {context.error}")
        except: pass

# ================== MAIN ==================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(?!delete_auto_msg).*"))
    app.add_handler(CallbackQueryHandler(delete_auto_msg, pattern="^delete_auto_msg$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    async def post_init(application):
        start_scheduler(application)

    app.post_init = post_init
    logger.info("Spirit Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
