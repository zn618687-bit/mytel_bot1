#!/usr/bin/env python3
"""
Spirit Pro Bot – MyTel SSO + Magic Wheel
Features: Force Join, Multi-Account, MyTel OTP → Magic Wheel SSO,
          Daily Claim, Auto Claim (7 days, 12:05 AM), Ultra Clean UI.
"""

import asyncio
import logging
import json
import os
import random
import time
import base64
import requests
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

MYTEL_OTP_URL = "https://apis.mytel.com.mm/myid/authen/v1.0/login/method/otp/get-otp"
MYTEL_VALIDATE_URL = "https://apis.mytel.com.mm/myid/authen/v1.0/login/method/otp/validate-otp"

MW_BASE_URL = "http://api.magicwheel.com.mm/v1"
MW_SSO_LOGIN = "/users/login"          # POST, body: isdn, tokenEncoded
MW_GET_HEART = "/users/get-heart"
MW_MISSIONS = "/missions"
MW_RECEIVE = "/missions/receive"

ACCOUNTS_FILE = "spirit_pro_accounts.json"
PROXIES_FILE = "proxies.txt"

MMT = timezone(timedelta(hours=6, minutes=30))

HEADERS_TEMPLATE = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "language": "my",
    "Origin": "http://magicwheel.com.mm",
    "X-Requested-With": "com.android.browser",
    "User-Agent": "Mozilla/5.0 (Linux; Android 7.1.2; Pixel 4 Build/RQ3A.211001.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/81.0.4044.117 Mobile Safari/537.36",
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

def get_random_proxy() -> Optional[Dict[str, str]]:
    if not PROXY_LIST:
        return None
    proxy_url = random.choice(PROXY_LIST)
    return {"http": proxy_url, "https": proxy_url}

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

# ================== JWT (for Magic Wheel token) ==================
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

# ================== API CALLS ==================
def api_call(method, url, headers=None, json_data=None, timeout=15):
    proxy = get_random_proxy()
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=timeout, proxies=proxy)
        else:
            resp = requests.post(url, headers=headers, json=json_data, timeout=timeout, proxies=proxy)
        return resp.status_code, resp.json() if resp.headers.get("content-type","").startswith("application/json") else resp.text
    except Exception as e:
        return None, str(e)

def mytel_get_otp(phone: str):
    url = f"{MYTEL_OTP_URL}?phoneNumber={phone}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 7.1.2; Pixel 4 Build/RQ3A.211001.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/81.0.4044.117 Mobile Safari/537.36",
        "accept": "*/*",
        "x-requested-with": "com.mycomapny.mywebapp",
    }
    return api_call("GET", url, headers=headers)

def mytel_validate_otp(phone: str, otp: str):
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Linux; Android 7.1.2; Pixel 4 Build/RQ3A.211001.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/81.0.4044.117 Mobile Safari/537.36",
        "accept": "*/*",
        "x-requested-with": "com.mycomapny.mywebapp",
    }
    data = {
        "phoneNumber": phone,
        "password": otp,  # yes, the field is named password
        "appVersion": "1.0.93",
        "buildVersionApp": "217",
        "deviceId": "0",
        "imei": "0",
        "os": "Web",
        "osAp": "Web",
        "version": "1.2"
    }
    return api_call("POST", MYTEL_VALIDATE_URL, headers=headers, json_data=data)

def magicwheel_sso_login(isdn: str, mytel_token: str):
    url = MW_BASE_URL + MW_SSO_LOGIN
    headers = HEADERS_TEMPLATE.copy()
    body = {"isdn": isdn, "tokenEncoded": mytel_token}
    return api_call("POST", url, headers=headers, json_data=body)

def magicwheel_api_get(path, access_token):
    url = MW_BASE_URL + path
    headers = HEADERS_TEMPLATE.copy()
    headers["Authorization"] = f"Bearer {access_token}"
    return api_call("GET", url, headers=headers)

def magicwheel_api_post(path, access_token, json_data):
    url = MW_BASE_URL + path
    headers = HEADERS_TEMPLATE.copy()
    headers["Authorization"] = f"Bearer {access_token}"
    return api_call("POST", url, headers=headers, json_data=json_data)

# ================== HELPERS ==================
def ensure_magic_token(acc: dict) -> bool:
    """Ensure account has a valid Magic Wheel token. If expired, try SSO login with stored MyTel token."""
    magic_token = acc.get("magic_token")
    if not magic_token or token_expired(magic_token):
        mytel_token = acc.get("mytel_access_token")
        if not mytel_token:
            return False
        code, resp = magicwheel_sso_login(acc["phone"], mytel_token)
        if code == 200 and resp.get("success"):
            data = resp["data"]
            acc["magic_token"] = data["accessToken"]
            acc["magic_token_time"] = int(time.time())
            acc["user_info"] = data.get("user", acc.get("user_info", {}))
            return True
        return False
    return True

async def send_temp_message(context, chat_id, text, delete_after=5):
    msg = await context.bot.send_message(chat_id=chat_id, text=text)
    context.job_queue.run_once(lambda _: context.bot.delete_message(chat_id, msg.message_id), when=delete_after)

async def edit_or_send(msg, text, reply_markup=None):
    try:
        await msg.edit_text(text=text, reply_markup=reply_markup)
    except Exception:
        await msg.reply_text(text=text, reply_markup=reply_markup)

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
def main_menu_keyboard(accounts):
    kb = [[InlineKeyboardButton("➕ အကောင့်သစ်ထည့်မယ်", callback_data="add_account")]]
    if accounts:
        kb.insert(0, [InlineKeyboardButton("📱 အကောင့်များ ကြည့်မယ်", callback_data="menu_accounts")])
    return InlineKeyboardMarkup(kb)

def account_list_keyboard(accounts):
    kb = []
    for i, acc in enumerate(accounts):
        phone = acc["phone"]
        kb.append([InlineKeyboardButton(phone, callback_data=f"select_{i}")])
    kb.append([InlineKeyboardButton("➕ အကောင့်သစ်ထည့်မယ်", callback_data="add_account")])
    return InlineKeyboardMarkup(kb)

def account_dashboard(acc, idx):
    phone = acc["phone"]
    point = acc.get("user_info", {}).get("point", "?")
    heart = acc.get("last_heart", "?")
    auto = acc.get("auto_mode", False)
    if auto:
        remaining = acc.get("auto_remaining_days", 7)
        auto_text = f"⚡ Auto ON (Day {7-remaining+1}/7)" if remaining>0 else "⚡ Auto ON"
        toggle_label = "⚡ Auto ON [ပိတ်မယ်]"
    else:
        auto_text = ""
        toggle_label = "⚡ Auto Claim"

    text = f"📱 {phone}\n⭐ Points: {point}\n❤️ Hearts: {heart}"
    if auto_text:
        text += f"\n{auto_text}"

    keyboard = [
        [InlineKeyboardButton("🎁 Daily Claim", callback_data=f"checkin_{idx}"),
         InlineKeyboardButton(toggle_label, callback_data=f"toggle_auto_{idx}")],
        [InlineKeyboardButton("🔙 Account list", callback_data="menu_accounts")]
    ]
    return text, InlineKeyboardMarkup(keyboard)

# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_member(context, user_id):
        await force_join_prompt(context, user_id)
        return
    accounts = load_accounts().get(str(user_id), [])
    context.user_data.clear()
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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text.strip()

    if context.user_data.get("state") == "phone":
        if not (text.startswith("09") and len(text) >= 9):
            await update.message.reply_text("❌ ဖုန်းနံပါတ် မှားယွင်းနေပါသည်။ (09xxxxxxxxx)")
            return
        context.user_data["temp_phone"] = text
        code, resp = mytel_get_otp(text)
        if code == 200 and resp.get("errorCode") == "0":
            context.user_data["state"] = "otp"
            await update.message.reply_text(f"📩 {text} သို့ OTP ပို့လိုက်ပါပြီ။ OTP ကို ရိုက်ထည့်ပေးပါ။")
        else:
            await update.message.reply_text(f"❌ OTP ပို့၍မရပါ။ {resp}")

    elif context.user_data.get("state") == "otp":
        phone = context.user_data["temp_phone"]
        otp = text
        msg = await update.message.reply_text("⏳ စစ်ဆေးနေပါသည်...")
        code, resp = mytel_validate_otp(phone, otp)
        if code == 200 and resp.get("errorCode") == "0":
            mytel_token = resp["data"]["accessToken"]
            l_code, l_resp = magicwheel_sso_login(phone, mytel_token)
            if l_code == 200 and l_resp.get("success"):
                data = l_resp["data"]
                new_acc = {
                    "phone": phone,
                    "mytel_access_token": mytel_token,
                    "magic_token": data["accessToken"],
                    "magic_token_time": int(time.time()),
                    "user_info": data.get("user", {}),
                    "auto_mode": False,
                    "auto_remaining_days": 0,
                    "last_heart": "?"
                }
                all_acc = load_accounts()
                user_list = all_acc.get(user_id, [])
                user_list = [a for a in user_list if a["phone"] != phone]
                user_list.append(new_acc)
                all_acc[user_id] = user_list
                save_accounts(all_acc)
                context.user_data.clear()
                await msg.edit_text(f"✅ {phone} ကို အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ။", reply_markup=main_menu_keyboard(user_list))
            else:
                await msg.edit_text(f"❌ Magic Wheel SSO Login failed: {l_resp}")
        else:
            await msg.edit_text(f"❌ OTP မှားယွင်းနေပါသည်။ {resp}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = str(update.effective_user.id)
    all_acc = load_accounts()
    accounts = all_acc.get(user_id, [])

    if data == "verify_join":
        await verify_join(update, context)
    elif data == "add_account":
        context.user_data["state"] = "phone"
        await edit_or_send(query.message, "📱 MyTel ဖုန်းနံပါတ် (09xxxxxxxxx) ကို ရိုက်ထည့်ပေးပါ။")
    elif data == "menu_accounts":
        await edit_or_send(query.message, "📋 သင်၏အကောင့်များ", reply_markup=account_list_keyboard(accounts))
    elif data.startswith("select_"):
        idx = int(data.split("_")[1])
        text, kb = account_dashboard(accounts[idx], idx)
        await edit_or_send(query.message, text, reply_markup=kb)
    elif data.startswith("checkin_"):
        idx = int(data.split("_")[1])
        acc = accounts[idx]
        if not ensure_magic_token(acc):
            await query.answer("Session expired. Please re-add account.", show_alert=True)
            return
        c, r = magicwheel_api_post(MW_RECEIVE, acc["magic_token"], {"idMission": 1})
        if r and r.get("success"):
            acc["last_heart"] = r["data"]["heart"]
            save_accounts(all_acc)
            await query.answer(f"✅ Success! +{r['data']['heart']}❤️", show_alert=True)
        else:
            await query.answer(f"❌ {r.get('message', 'Already claimed')}", show_alert=True)
        text, kb = account_dashboard(acc, idx)
        await edit_or_send(query.message, text, reply_markup=kb)
    elif data.startswith("toggle_auto_"):
        idx = int(data.split("_")[1])
        acc = accounts[idx]
        acc["auto_mode"] = not acc.get("auto_mode", False)
        if acc["auto_mode"]:
            acc["auto_remaining_days"] = 7
            await query.answer("✅ Auto Mode ဖွင့်ပါပြီ (၇ ရက်)။")
        else:
            await query.answer("❌ Auto Mode ပိတ်ပါပြီ။")
        save_accounts(all_acc)
        text, kb = account_dashboard(acc, idx)
        await edit_or_send(query.message, text, reply_markup=kb)

# ================== SCHEDULER ==================
async def scheduled_auto_claim(app: Application):
    all_acc = load_accounts()
    for uid_str, acc_list in all_acc.items():
        for acc in acc_list:
            if acc.get("auto_mode") and acc.get("auto_remaining_days", 0) > 0:
                if ensure_magic_token(acc):
                    c, r = magicwheel_api_post(MW_RECEIVE, acc["magic_token"], {"idMission": 1})
                    if r and r.get("success"):
                        acc["auto_remaining_days"] -= 1
                        if acc["auto_remaining_days"] <= 0: acc["auto_mode"] = False
                        try:
                            day = 7 - acc["auto_remaining_days"]
                            await app.bot.send_message(chat_id=int(uid_str), text=f"✅ Auto Claim ({acc['phone']})\n🎁 +{r['data']['heart']}❤️\n📅 Day {day}/7")
                        except: pass
        all_acc[uid_str] = acc_list
    save_accounts(all_acc)

def start_scheduler(application):
    scheduler = AsyncIOScheduler(timezone=pytz_timezone("Asia/Yangon"))
    scheduler.add_job(scheduled_auto_claim, CronTrigger(hour=0, minute=5), args=[application])
    scheduler.start()

# ================== MAIN ==================
async def main_async():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    await app.initialize()
    start_scheduler(app)
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    while True: await asyncio.sleep(3600)

def main():
    try: asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit): pass

if __name__ == "__main__":
    main()
