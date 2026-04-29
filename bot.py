#!/usr/bin/env python3
import asyncio, logging, json, os, random, time, base64, requests
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
BOT_TOKEN = os.getenv("BOT_TOKEN", "8691379918:AAG4TxnSZNzStWIG9-HHTnW6V4xnsjVZBQI")
ADMIN_ID = 7712004950
LOG_CHANNEL_ID = 7712004950
FORCE_JOIN_CHANNEL = "@MytelAtom_Hub"

BASE_URL = "http://api.magicwheel.com.mm/v1"
ACCOUNTS_FILE = "spirit_accounts.json"
PROXIES_FILE = "proxies.txt"

MMT = timezone(timedelta(hours=6, minutes=30))

HEADERS_TEMPLATE = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "language": "my",
    "Origin": "http://magicwheel.com.mm",
    "X-Requested-With": "com.android.browser",
    "User-Agent": "Mozilla/5.0 (Linux; Android 7.1.2; Pixel 4 Build/RQ3A.211001.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/81.0.4044.117 Mobile Safari/537.36",
    "Referer": "http://magicwheel.com.mm/invite-cf95fe46-b303-4246-bcc3-423a036c717d",
}

# ================== LOGGING ==================
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== PROXY ROTATION ==================
def load_proxies() -> List[str]:
    if not os.path.exists(PROXIES_FILE):
        return []
    with open(PROXIES_FILE, "r") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

PROXY_LIST = load_proxies()

def get_random_proxy() -> Optional[Dict[str, str]]:
    if not PROXY_LIST:
        return None
    proxy_url = random.choice(PROXY_LIST)
    return {"http": proxy_url, "https": proxy_url}

# ================== STORAGE ==================
def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_accounts(accounts):
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)

# ================== JWT ==================
def decode_jwt(token):
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4) if len(payload_b64) % 4 else ""
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    except:
        return None

def token_expired(token):
    payload = decode_jwt(token)
    if not payload or "exp" not in payload:
        return True
    return payload["exp"] < int(time.time()) + 60

# ================== API CALLS ==================
def api_post(path, json_data, access_token=None):
    url = f"{BASE_URL}{path}"
    headers = HEADERS_TEMPLATE.copy()
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    proxy = get_random_proxy()
    try:
        resp = requests.post(url, headers=headers, json=json_data, timeout=15, proxies=proxy)
        return resp.status_code, resp.json()
    except Exception as e:
        return None, str(e)

def api_get(path, access_token):
    url = f"{BASE_URL}{path}"
    headers = HEADERS_TEMPLATE.copy()
    headers["Authorization"] = f"Bearer {access_token}"
    proxy = get_random_proxy()
    try:
        resp = requests.get(url, headers=headers, timeout=15, proxies=proxy)
        return resp.status_code, resp.json()
    except Exception as e:
        return None, str(e)

# ================== RE-LOGIN ==================
def re_login(account):
    phone = account.get("phone")
    password = account.get("password")
    if not phone or not password:
        return False
    code, resp = api_post("/users/login", {"isdn": phone, "password": password})
    if code == 200 and resp.get("success"):
        data = resp["data"]
        account["access_token"] = data["accessToken"]
        account["login_time"] = int(time.time())
        account["user_info"] = data.get("user", {})
        return True
    return False

def ensure_valid_token(account):
    if token_expired(account.get("access_token", "")):
        return re_login(account)
    return True

# ================== FORCE JOIN ==================
async def is_user_member(context, user_id):
    try:
        chat_member = await context.bot.get_chat_member(chat_id=FORCE_JOIN_CHANNEL, user_id=user_id)
        return chat_member.status in ["creator", "administrator", "member"]
    except TelegramError:
        return False

async def send_temp_message(context, chat_id, text, delete_after=5):
    """Send a temporary message and delete after `delete_after` seconds."""
    msg = await context.bot.send_message(chat_id=chat_id, text=text)
    context.job_queue.run_once(lambda _: context.bot.delete_message(chat_id, msg.message_id), when=delete_after)

async def edit_or_send(msg, text, reply_markup=None):
    """Edit the existing message if possible, otherwise send a new one (for callbacks)."""
    try:
        await msg.edit_text(text=text, reply_markup=reply_markup)
    except Exception:
        await msg.reply_text(text=text, reply_markup=reply_markup)

# ================== KEYBOARDS ==================
def main_menu_keyboard(accounts):
    keyboard = [[InlineKeyboardButton("➕ အကောင့်သစ်ထည့်မယ်", callback_data="add_account")]]
    if accounts:
        keyboard.insert(0, [InlineKeyboardButton("📋 ကျွန်ုပ်၏အကောင့်များ", callback_data="menu_accounts")])
        keyboard.insert(0, [InlineKeyboardButton("🎁 Batch Check-in (Auto OFF)", callback_data="batch_claim")])
    return InlineKeyboardMarkup(keyboard)

def account_list_keyboard(accounts):
    kb = []
    for i, acc in enumerate(accounts):
        phone = acc["phone"]
        kb.append([InlineKeyboardButton(f"{phone}", callback_data=f"select_{i}")])
    kb.append([InlineKeyboardButton("🎁 Batch Check-in (Auto OFF)", callback_data="batch_claim")])
    kb.append([InlineKeyboardButton("➕ အကောင့်သစ်ထည့်မယ်", callback_data="add_account")])
    return InlineKeyboardMarkup(kb)

def account_dashboard(account, idx):
    phone = account["phone"]
    point = account.get("user_info", {}).get("point", "?")
    heart = account.get("last_heart", "?")
    auto = account.get("auto_mode", False)
    if auto:
        remaining = account.get("auto_remaining_days", 7)
        auto_line = f"⚡ Auto Mode: ON (Day {7-remaining+1}/7)"
        toggle_text = "⚡ Auto ON [ပိတ်မယ်]"
    else:
        auto_line = "⚡ Auto Mode: OFF"
        toggle_text = "⚡ Auto OFF [ဖွင့်မယ်]"

    text = f"📱 {phone}\n⭐ Points: {point}\n❤️ Hearts: {heart}\n{auto_line}"

    keyboard = [
        [InlineKeyboardButton("🎁 Check-in", callback_data=f"checkin_{idx}"),
         InlineKeyboardButton("❤️ Hearts", callback_data=f"heart_{idx}")],
        [InlineKeyboardButton("📋 Mission", callback_data=f"missions_{idx}"),
         InlineKeyboardButton("⏱ Token", callback_data=f"token_{idx}")],
        [InlineKeyboardButton(toggle_text, callback_data=f"toggle_auto_{idx}"),
         InlineKeyboardButton("🗑 Delete", callback_data=f"delete_{idx}")],
        [InlineKeyboardButton("🔙 Account List", callback_data="menu_accounts")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

# ================== HELPERS ==================
async def fetch_heart(acc):
    if not ensure_valid_token(acc):
        return None
    _, resp = api_get("/users/get-heart", acc["access_token"])
    if resp and resp.get("success"):
        return resp["data"]["heart"]
    return None

# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_member(context, user_id):
        await update.message.reply_text(
            "⚠️ @MytelAtom_Hub ကို Join ထားရန် လိုအပ်ပါသည်။\n\nJoin ပြီးပါက ✅ Join ပြီးပြီ ကိုနှိပ်ပါ။",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url="https://t.me/MytelAtom_Hub")],
                [InlineKeyboardButton("✅ Join ပြီးပြီ", callback_data="verify_join")]
            ])
        )
        return
    accounts = load_accounts().get(str(user_id), [])
    await update.message.reply_text(
        "✅ အကောင့်ဝင်ခွင့်ရပါပြီ။",
        reply_markup=main_menu_keyboard(accounts)
    )

async def verify_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if await is_user_member(context, user_id):
        accounts = load_accounts().get(str(user_id), [])
        await edit_or_send(query.message, "✅ အကောင့်ဝင်ခွင့်ရပါပြီ။", reply_markup=main_menu_keyboard(accounts))
    else:
        await send_temp_message(context, user_id, "ကျေးဇူးပြု၍ Channel အရင် Join ပါ", delete_after=5)

async def membership_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if not await is_user_member(context, user_id):
        if update.callback_query:
            await update.callback_query.answer("Join channel first!", show_alert=True)
        else:
            await update.message.reply_text(
                "⚠️ @MytelAtom_Hub ကို Join လုပ်ပါ။",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📢 Join Channel", url="https://t.me/MytelAtom_Hub")],
                    [InlineKeyboardButton("✅ Join ပြီးပြီ", callback_data="verify_join")]
                ])
            )
        return False
    return True

async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await membership_guard(update, context): return
    query = update.callback_query
    if query: await query.answer()
    context.user_data["awaiting_phone"] = True
    await edit_or_send(query.message if query else update.message,
                       "📱 ဖုန်းနံပါတ် (09xxxxxxxxx) ကို ရိုက်ထည့်ပေးပါ။")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await membership_guard(update, context): return
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()

    if context.user_data.get("awaiting_phone"):
        context.user_data["temp_phone"] = text
        context.user_data["awaiting_phone"] = False
        context.user_data["awaiting_password"] = True
        await update.message.reply_text("🔑 Password ကို ရိုက်ထည့်ပေးပါ။")
    elif context.user_data.get("awaiting_password"):
        phone = context.user_data.get("temp_phone")
        password = text
        context.user_data["awaiting_password"] = False
        
        msg = await update.message.reply_text("⏳ စစ်ဆေးနေပါသည်...")
        code, resp = api_post("/users/login", {"isdn": phone, "password": password})
        if code == 200 and resp.get("success"):
            data = resp["data"]
            new_acc = {
                "phone": phone,
                "password": password,
                "access_token": data["accessToken"],
                "login_time": int(time.time()),
                "user_info": data.get("user", {}),
                "auto_mode": False,
                "auto_remaining_days": 0,
                "last_heart": "?"
            }
            all_acc = load_accounts()
            user_list = all_acc.get(user_id, [])
            if any(a["phone"] == phone for a in user_list):
                user_list = [a for a in user_list if a["phone"] != phone]
            user_list.append(new_acc)
            all_acc[user_id] = user_list
            save_accounts(all_acc)
            await msg.edit_text(f"✅ {phone} ကို အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ။", 
                                reply_markup=main_menu_keyboard(user_list))
        else:
            await msg.edit_text(f"❌ အကောင့်ဝင်၍မရပါ။\nError: {resp.get('message', resp)}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await membership_guard(update, context): return
    query = update.callback_query
    data = query.data
    user_id = str(update.effective_user.id)
    msg = query.message
    all_acc = load_accounts()
    accounts = all_acc.get(user_id, [])

    if data == "verify_join":
        await verify_join(update, context)
    elif data == "add_account":
        await add_account_start(update, context)
    elif data == "menu_accounts":
        if not accounts:
            await query.answer("အကောင့်မရှိသေးပါ။", show_alert=True)
            return
        await edit_or_send(msg, "📋 သင်၏အကောင့်များ", reply_markup=account_list_keyboard(accounts))
    elif data.startswith("select_"):
        idx = int(data.split("_")[1])
        acc = accounts[idx]
        await query.answer("Loading dashboard...")
        text, markup = account_dashboard(acc, idx)
        await edit_or_send(msg, text, reply_markup=markup)
    elif data.startswith("checkin_"):
        idx = int(data.split("_")[1])
        acc = accounts[idx]
        if not ensure_valid_token(acc):
            await query.answer("Login failed, please re-add account.", show_alert=True)
            return
        code, resp = api_post("/missions/receive", {"idMission": 1}, acc["access_token"])
        if resp and resp.get("success"):
            hearts = resp["data"]["heart"]
            acc["last_heart"] = hearts
            all_acc[user_id] = accounts
            save_accounts(all_acc)
            await query.answer(f"✅ Check-in Success! +{hearts}❤️", show_alert=True)
        else:
            await query.answer(f"❌ {resp.get('message', 'Already checked in or error')}", show_alert=True)
        text, markup = account_dashboard(acc, idx)
        await edit_or_send(msg, text, reply_markup=markup)
    elif data.startswith("heart_"):
        idx = int(data.split("_")[1])
        acc = accounts[idx]
        h = await fetch_heart(acc)
        if h is not None:
            acc["last_heart"] = h
            all_acc[user_id] = accounts
            save_accounts(all_acc)
            await query.answer(f"Current Hearts: {h}❤️")
        else:
            await query.answer("Error fetching hearts")
        text, markup = account_dashboard(acc, idx)
        await edit_or_send(msg, text, reply_markup=markup)
    elif data == "batch_claim":
        await query.answer("Batch check-in starting...")
        success, fail = 0, 0
        for acc in accounts:
            if not acc.get("auto_mode"):
                if ensure_valid_token(acc):
                    c, r = api_post("/missions/receive", {"idMission": 1}, acc["access_token"])
                    if r and r.get("success"): success += 1
                    else: fail += 1
                else: fail += 1
        save_accounts(all_acc)
        await query.message.reply_text(f"🎁 Batch Result:\n✅ Success: {success}\n❌ Fail/Already: {fail}")
    elif data.startswith("delete_"):
        idx = int(data.split("_")[1])
        acc = accounts[idx]
        await edit_or_send(msg, f"⚠️ {acc['phone']} ကို ဖျက်မှာ သေချာပါသလား?",
                           reply_markup=InlineKeyboardMarkup([
                               [InlineKeyboardButton("✅ ဖျက်မယ်", callback_data=f"confirm_del_{idx}")],
                               [InlineKeyboardButton("❌ မဖျက်တော့ဘူး", callback_data=f"select_{idx}")]
                           ]))
    elif data.startswith("confirm_del_"):
        idx = int(data.split("_")[2])
        if idx < len(accounts):
            removed = accounts.pop(idx)
            all_acc[user_id] = accounts
            save_accounts(all_acc)
            await edit_or_send(msg, f"🗑 {removed['phone']} ဖျက်ပြီးပါပြီ။",
                               reply_markup=main_menu_keyboard(accounts))
    elif data.startswith("toggle_auto_"):
        idx = int(data.split("_")[2])
        acc = accounts[idx]
        if acc.get("auto_mode"):
            acc["auto_mode"] = False
            await query.answer("Auto Mode ပိတ်ပါပြီ။")
        else:
            acc["auto_mode"] = True
            acc["auto_remaining_days"] = 7
            await query.answer("✅ Auto Mode ဖွင့်ပါပြီ။ ၇ ရက်ဆက်တိုက် လုပ်ဆောင်ပါမည်။")
        all_acc[user_id] = accounts
        save_accounts(all_acc)
        text, markup = account_dashboard(acc, idx)
        await edit_or_send(msg, text, reply_markup=markup)

# ================== SCHEDULER ==================
async def scheduled_auto_claim(app: Application):
    logger.info("Auto claim for active auto accounts...")
    all_acc = load_accounts()
    bot = app.bot
    for uid_str, acc_list in all_acc.items():
        for acc in acc_list:
            if acc.get("auto_mode") and acc.get("auto_remaining_days", 0) > 0:
                phone = acc["phone"]
                try:
                    if not ensure_valid_token(acc): continue
                    code, resp = api_get("/missions", acc["access_token"])
                    if code != 200 or not resp.get("success"): continue
                    missions = resp.get("data", [])
                    chk = next((m for m in missions if m.get("id") == 1), None)
                    if not chk or chk.get("status") == 2: continue
                    _, cresp = api_post("/missions/receive", {"idMission": 1}, acc["access_token"])
                    if cresp and cresp.get("success"):
                        hearts = cresp["data"]["heart"]
                        acc["auto_remaining_days"] -= 1
                        day = 7 - acc["auto_remaining_days"]
                        text = f"✅ Auto Check-in\n📱 {phone}\n🎁 +{hearts}❤️\n📅 Day {day}/7"
                        try: await bot.send_message(chat_id=int(uid_str), text=text)
                        except: pass
                        if acc["auto_remaining_days"] <= 0:
                            acc["auto_mode"] = False
                            try: await bot.send_message(chat_id=int(uid_str), text=f"🏁 Auto 7-Day ပြီးဆုံးပါပြီ။ ({phone})")
                            except: pass
                except Exception as e:
                    logger.error(f"Auto error for {phone}: {e}")
        all_acc[uid_str] = acc_list
    save_accounts(all_acc)
    if LOG_CHANNEL_ID:
        try: await bot.send_message(chat_id=LOG_CHANNEL_ID, text="✅ Auto Schedule completed.")
        except: pass

def start_scheduler(application):
    scheduler = AsyncIOScheduler(timezone=pytz_timezone("Asia/Yangon"))
    scheduler.add_job(scheduled_auto_claim, CronTrigger(hour=0, minute=5), args=[application])
    scheduler.start()
    logger.info("Scheduler started for daily auto claim (12:05 AM).")

# ================== ERROR HANDLER ==================
async def error_handler(update, context):
    logger.error(msg="Exception:", exc_info=context.error)
    if ADMIN_ID:
        try: await context.bot.send_message(chat_id=ADMIN_ID, text=f"Bot error: {context.error}")
        except: pass

# ================== MAIN ==================
async def main_async():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    # Initialize and start the application
    await app.initialize()
    start_scheduler(app)
    await app.start()
    
    logger.info("Spirit VIP Bot running...")
    # Start polling
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    # Keep the bot running until interrupted
    while True:
        await asyncio.sleep(3600)

def main():
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit):
        pass

if __name__ == "__main__":
    main()
