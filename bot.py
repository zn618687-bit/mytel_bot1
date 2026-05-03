#!/usr/bin/env python3
"""
Spirit Pro Bot – MyTel SSO + Magic Wheel (Error‑Free OTP Version)
Final Release – All features working.
"""

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

MYTEL_OTP_URL = "https://apis.mytel.com.mm/myid/authen/v1.0/login/method/otp/get-otp"
MYTEL_VALIDATE_URL = "https://apis.mytel.com.mm/myid/authen/v1.0/login/method/otp/validate-otp"

MW_BASE_URL = "http://api.magicwheel.com.mm/v1"
MW_SSO_LOGIN = "/users/login"
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

# ================== API CALLS ==================
def api_call(method, url, headers=None, json_data=None, timeout=15, use_proxy=True):
    proxy = get_random_proxy() if use_proxy else None
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=timeout, proxies=proxy, allow_redirects=True)
        else:
            resp = requests.post(url, headers=headers, json=json_data, timeout=timeout, proxies=proxy, allow_redirects=True)
        
        logger.info(f"API Call: {method} {url} | Status: {resp.status_code}")
        
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            return resp.status_code, resp.json()
        else:
            return resp.status_code, resp.text
    except Exception as e:
        logger.error(f"API Error: {method} {url} | {str(e)}")
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
        "password": otp,
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
    magic_token = acc.get("magic_token")
    if not magic_token or token_expired(magic_token):
        mytel_token = acc.get("mytel_access_token")
        if not mytel_token:
            return False
        code, resp = magicwheel_sso_login(acc["phone"], mytel_token)
        if 200 <= code < 300 and isinstance(resp, dict) and resp.get("success"):
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
        if remaining > 0:
            auto_text = f"⚡ Auto ON (Day {7-remaining+1}/7)"
        else:
            auto_text = "⚡ Auto ON"
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
        # Success check: any 2xx status code OR errorCode is 0 or 200
        is_success = False
        if code and 200 <= code < 300:
            if isinstance(resp, dict):
                err_code = str(resp.get("errorCode", ""))
                if err_code in ["0", "200"] or resp.get("message") == "Otp code was sent to your phone number":
                    is_success = True
            else:
                is_success = True # Assume success if 2xx and not JSON

        if is_success:
            context.user_data["state"] = "otp"
            await update.message.reply_text(f"📩 {text} သို့ OTP ပို့လိုက်ပါပြီ။ OTP ကို ရိုက်ထည့်ပေးပါ။")
        else:
            await update.message.reply_text(f"❌ OTP ပို့၍မရပါ။ (Status: {code}) {resp}")

    elif context.user_data.get("state") == "otp":
        otp = text
        phone = context.user_data.get("temp_phone")
        if not phone:
            await update.message.reply_text("Session expired. /start again.")
            context.user_data.clear()
            return

        # ၁။ User ရဲ့ OTP message ကို ၂ စက္ကန့်အတွင်း ဖျက်မယ်။
        context.job_queue.run_once(
            lambda _: context.bot.delete_message(update.effective_chat.id, update.message.message_id),
            when=2
        )

        # ၂။ "စစ်ဆေးနေသည်..." status message တစ်ခုပို့မယ်။
        status_msg = await update.message.reply_text("⏳ စစ်ဆေးနေပါသည်...")

        # ၃။ OTP Validation API ကိုခေါ်မယ်။
        try:
            code, resp = mytel_validate_otp(phone, otp)
        except Exception as e:
            await status_msg.edit_text(f"❌ ချိတ်ဆက်မရပါ (Network Error): {e}")
            return

        # ၄။ Response ကို စစ်ဆေးမယ်။
        # Note: Acceptance criteria modified to match previous fix for errorCode 0/200 and 2xx status
        is_otp_success = False
        if code and 200 <= code < 300 and isinstance(resp, dict):
            # Checking both result structure and common error codes
            if (resp.get("result") and resp["result"].get("access_token")) or \
               (str(resp.get("errorCode", "")) in ["0", "200"] and resp.get("data", {}).get("accessToken")):
                is_otp_success = True

        if is_otp_success:
            # OTP အောင်မြင် → MyTel token ရပြီ။
            # Handling both "result" (from snippet) and "data" (from previous API structure)
            if resp.get("result"):
                mytel_token = resp["result"]["access_token"]
                mytel_refresh = resp["result"].get("refresh_token")
            else:
                mytel_token = resp["data"]["accessToken"]
                mytel_refresh = None

            # Status ကို "Magic Wheel ဝင်နေသည်..." လို့ပြောင်းမယ်။
            await status_msg.edit_text("✅ MyTel အောင်မြင်ပါပြီ။ ⏳ Magic Wheel သို့ ဝင်ရောက်နေသည်...")

            # Magic Wheel SSO Login ခေါ်မယ်။
            sso_code, sso_resp = magicwheel_sso_login(phone, mytel_token)
            if (sso_code and 200 <= sso_code < 300 and
                    isinstance(sso_resp, dict) and
                    sso_resp.get("success")):
                data = sso_resp["data"]
                account = {
                    "phone": phone,
                    "mytel_access_token": mytel_token,
                    "mytel_refresh_token": mytel_refresh,
                    "magic_token": data["accessToken"],
                    "magic_token_time": int(time.time()),
                    "user_info": data.get("user", {}),
                    "auto_mode": False,
                    "auto_remaining_days": 7,
                    "last_heart": 0
                }
                all_acc = load_accounts()
                user_list = all_acc.get(user_id, [])
                user_list = [a for a in user_list if a["phone"] != phone]
                user_list.append(account)
                all_acc[user_id] = user_list
                save_accounts(all_acc)
                accounts = all_acc[user_id]

                # Status message ကို ဖျက်ပြီး အကောင့်စာရင်းကို သန့်သန့်လေးပြမယ်။
                await status_msg.delete()
                await update.message.reply_text(
                    "📱 ကျွန်ုပ်၏အကောင့်များ",
                    reply_markup=account_list_keyboard(accounts)
                )
                context.user_data.clear()
            else:
                # Magic Wheel SSO မအောင်မြင်
                err_detail = sso_resp if isinstance(sso_resp, dict) else "Unknown error"
                await status_msg.edit_text(f"❌ Magic Wheel SSO မအောင်မြင်ပါ။ {err_detail}")
        else:
            # OTP Validation မအောင်မြင် (သို့) error ပြန်
            err_detail = resp if isinstance(resp, dict) else "Unknown error"
            await status_msg.edit_text(f"❌ OTP အတည်မပြုနိုင်ပါ။ {err_detail}")

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
        if r and isinstance(r, dict) and r.get("success"):
            acc["last_heart"] = r["data"]["heart"]
            save_accounts(all_acc)
            await query.answer(f"✅ Success! +{r['data']['heart']}❤️", show_alert=True)
        else:
            msg = r.get('message', 'Already claimed') if isinstance(r, dict) else "Error"
            await query.answer(f"❌ {msg}", show_alert=True)
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
    """
    Scheduled job that runs daily at 12:05 AM Myanmar time (UTC+6:30).
    Processes all accounts with auto_mode enabled and claims daily hearts.
    """
    logger.info("[AUTO CLAIM] Starting scheduled auto-claim job...")
    try:
        all_acc = load_accounts()
        logger.info(f"[AUTO CLAIM] Loaded {len(all_acc)} users with accounts")
        
        total_processed = 0
        total_claimed = 0
        
        for uid_str, acc_list in all_acc.items():
            logger.info(f"[AUTO CLAIM] Processing user {uid_str} with {len(acc_list)} accounts")
            
            for idx, acc in enumerate(acc_list):
                phone = acc.get("phone", "unknown")
                auto_mode = acc.get("auto_mode", False)
                remaining_days = acc.get("auto_remaining_days", 0)
                
                logger.info(f"[AUTO CLAIM] Account {idx} ({phone}): auto_mode={auto_mode}, remaining_days={remaining_days}")
                
                if not auto_mode:
                    logger.debug(f"[AUTO CLAIM] Skipping {phone}: auto_mode is disabled")
                    continue
                
                if remaining_days <= 0:
                    logger.debug(f"[AUTO CLAIM] Skipping {phone}: no remaining days")
                    acc["auto_mode"] = False
                    continue
                
                try:
                    total_processed += 1
                    
                    # Ensure Magic Wheel token is valid
                    if not ensure_magic_token(acc):
                        logger.warning(f"[AUTO CLAIM] Failed to refresh token for {phone}")
                        try:
                            await app.bot.send_message(
                                chat_id=int(uid_str),
                                text=f"❌ Auto Claim ({phone})\n⚠️ Token refresh failed. Please re-login."
                            )
                        except Exception as e:
                            logger.error(f"[AUTO CLAIM] Failed to send error message to {uid_str}: {e}")
                        continue
                    
                    # Call Magic Wheel API to claim daily heart
                    logger.info(f"[AUTO CLAIM] Calling MW_RECEIVE for {phone}...")
                    code, resp = magicwheel_api_post(MW_RECEIVE, acc["magic_token"], {"idMission": 1})
                    logger.info(f"[AUTO CLAIM] MW_RECEIVE response: code={code}, resp={resp}")
                    
                    # Check if API call was successful (2xx status code)
                    if code and 200 <= code < 300 and isinstance(resp, dict) and resp.get("success"):
                        total_claimed += 1
                        acc["auto_remaining_days"] -= 1
                        
                        # Disable auto mode if all 7 days are complete
                        if acc["auto_remaining_days"] <= 0:
                            acc["auto_mode"] = False
                            logger.info(f"[AUTO CLAIM] Auto mode completed for {phone}")
                        
                        # Send success notification
                        day_num = 7 - acc["auto_remaining_days"]
                        heart_gained = resp.get("data", {}).get("heart", "?")
                        notification_text = f"✅ Auto Claim ({phone})\n🎁 +{heart_gained}❤️\n📅 Day {day_num}/7"
                        
                        try:
                            await app.bot.send_message(chat_id=int(uid_str), text=notification_text)
                            logger.info(f"[AUTO CLAIM] Sent success notification to {uid_str}")
                        except Exception as e:
                            logger.error(f"[AUTO CLAIM] Failed to send notification to {uid_str}: {e}")
                    else:
                        logger.warning(f"[AUTO CLAIM] API call failed for {phone}: code={code}, resp={resp}")
                        try:
                            await app.bot.send_message(
                                chat_id=int(uid_str),
                                text=f"❌ Auto Claim ({phone})\n⚠️ API error. Please try manual claim."
                            )
                        except Exception as e:
                            logger.error(f"[AUTO CLAIM] Failed to send error message to {uid_str}: {e}")
                
                except Exception as e:
                    logger.error(f"[AUTO CLAIM] Exception processing account {phone}: {str(e)}", exc_info=True)
                    try:
                        await app.bot.send_message(
                            chat_id=int(uid_str),
                            text=f"❌ Auto Claim ({phone})\n⚠️ An error occurred. Please check logs."
                        )
                    except Exception as send_err:
                        logger.error(f"[AUTO CLAIM] Failed to send error message: {send_err}")
            
            all_acc[uid_str] = acc_list
        
        # Save updated accounts
        save_accounts(all_acc)
        logger.info(f"[AUTO CLAIM] Job completed: processed={total_processed}, claimed={total_claimed}")
        
    except Exception as e:
        logger.error(f"[AUTO CLAIM] Critical error in scheduled_auto_claim: {str(e)}", exc_info=True)


def start_scheduler(application):
    """
    Initialize and start the APScheduler for auto-claim jobs.
    Runs daily at 12:05 AM Myanmar time (UTC+6:30).
    """
    logger.info("[SCHEDULER] Initializing scheduler...")
    
    try:
        # Try to use Asia/Yangon timezone
        try:
            tz = pytz_timezone("Asia/Yangon")
            logger.info("[SCHEDULER] Using timezone: Asia/Yangon")
        except Exception as tz_err:
            logger.warning(f"[SCHEDULER] Failed to load Asia/Yangon: {tz_err}. Using UTC+6:30 offset.")
            # Fallback: use UTC with manual offset
            from datetime import timezone as dt_timezone
            tz = dt_timezone(timedelta(hours=6, minutes=30))
        
        scheduler = AsyncIOScheduler(timezone=tz)
        
        # Add the auto-claim job
        job = scheduler.add_job(
            scheduled_auto_claim,
            CronTrigger(hour=0, minute=5, timezone=tz),
            args=[application],
            id="auto_claim_job",
            name="Auto Claim Daily Job",
            replace_existing=True
        )
        
        logger.info(f"[SCHEDULER] Job added: {job.name} (ID: {job.id})")
        logger.info(f"[SCHEDULER] Next run time: {job.next_run_time}")
        
        # Start the scheduler
        scheduler.start()
        logger.info("[SCHEDULER] Scheduler started successfully")
        
        # Log all registered jobs
        jobs = scheduler.get_jobs()
        logger.info(f"[SCHEDULER] Total jobs registered: {len(jobs)}")
        for j in jobs:
            logger.info(f"[SCHEDULER]   - {j.name} (ID: {j.id}, Next run: {j.next_run_time})")
        
        return scheduler
    
    except Exception as e:
        logger.error(f"[SCHEDULER] Failed to start scheduler: {str(e)}", exc_info=True)
        raise



# ================== MANUAL TEST COMMAND (/auto) ==================

async def auto_claim_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Manual command to trigger auto-claim immediately for the current user's accounts.
    Usage: /auto
    """
    user_id = update.effective_user.id
    logger.info(f"[MANUAL AUTO] User {user_id} triggered /auto command")
    
    # Check force join
    if not await is_user_member(context, user_id):
        await force_join_prompt(context, user_id)
        return
    
    try:
        all_acc = load_accounts()
        user_accounts = all_acc.get(str(user_id), [])
        
        if not user_accounts:
            await update.message.reply_text("❌ No accounts found. Please add an account first.")
            return
        
        # Filter accounts with auto_mode enabled
        auto_accounts = [acc for acc in user_accounts if acc.get("auto_mode", False)]
        
        if not auto_accounts:
            await update.message.reply_text("❌ No accounts with auto-claim enabled.")
            return
        
        await update.message.reply_text(f"⏳ Processing {len(auto_accounts)} account(s)...")
        
        total_claimed = 0
        
        for acc in auto_accounts:
            phone = acc.get("phone", "unknown")
            remaining_days = acc.get("auto_remaining_days", 0)
            
            logger.info(f"[MANUAL AUTO] Processing {phone} (remaining_days={remaining_days})")
            
            if remaining_days <= 0:
                logger.info(f"[MANUAL AUTO] Skipping {phone}: no remaining days")
                continue
            
            try:
                # Ensure Magic Wheel token is valid
                if not ensure_magic_token(acc):
                    logger.warning(f"[MANUAL AUTO] Failed to refresh token for {phone}")
                    await update.message.reply_text(f"❌ {phone}: Token refresh failed")
                    continue
                
                # Call Magic Wheel API to claim daily heart
                logger.info(f"[MANUAL AUTO] Calling MW_RECEIVE for {phone}...")
                code, resp = magicwheel_api_post(MW_RECEIVE, acc["magic_token"], {"idMission": 1})
                logger.info(f"[MANUAL AUTO] MW_RECEIVE response: code={code}, resp={resp}")
                
                # Check if API call was successful (2xx status code)
                if code and 200 <= code < 300 and isinstance(resp, dict) and resp.get("success"):
                    total_claimed += 1
                    acc["auto_remaining_days"] -= 1
                    
                    # Disable auto mode if all 7 days are complete
                    if acc["auto_remaining_days"] <= 0:
                        acc["auto_mode"] = False
                        logger.info(f"[MANUAL AUTO] Auto mode completed for {phone}")
                    
                    # Send success notification
                    day_num = 7 - acc["auto_remaining_days"]
                    heart_gained = resp.get("data", {}).get("heart", "?")
                    await update.message.reply_text(f"✅ {phone}\n🎁 +{heart_gained}❤️\n📅 Day {day_num}/7")
                else:
                    logger.warning(f"[MANUAL AUTO] API call failed for {phone}: code={code}, resp={resp}")
                    await update.message.reply_text(f"❌ {phone}: API error")
            
            except Exception as e:
                logger.error(f"[MANUAL AUTO] Exception processing {phone}: {str(e)}", exc_info=True)
                await update.message.reply_text(f"❌ {phone}: Error - {str(e)}")
        
        # Save updated accounts
        all_acc[str(user_id)] = user_accounts
        save_accounts(all_acc)
        
        await update.message.reply_text(f"✅ Manual auto-claim completed: {total_claimed} account(s) claimed")
        logger.info(f"[MANUAL AUTO] User {user_id} completed manual auto-claim: {total_claimed} claimed")
    
    except Exception as e:
        logger.error(f"[MANUAL AUTO] Error in auto_claim_manual: {str(e)}", exc_info=True)
        await update.message.reply_text(f"❌ An error occurred: {str(e)}")

# ================== MAIN ==================
async def main_async():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("auto", auto_claim_manual))
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
