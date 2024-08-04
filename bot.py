import os
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters, CallbackQueryHandler
import random
import asyncio
import logging
import sqlite3  # مكتبة sqlite3 مضمنة في بايثون، لذا لا حاجة لتثبيتها عبر pip
import matplotlib.pyplot as plt
import smtplib
from email.mime.text import MIMEText
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import subprocess
import io
from contextlib import redirect_stdout, redirect_stderr
import sys  # استيراد مكتبة sys

# Define the token directly in the code
TOKEN = "7345776779:AAF82j-huMOakzVp2LG2TBK9_CrYkIlgVmM"
OWNER_ID = 7342561936  # Replace with your own Telegram ID

# Tokens for report and feedback bots
REPORT_BOT_TOKEN = "7261277394:AAEALpqckRG2McndiD8dhuVaqn-veZ_9nbo"
FEEDBACK_BOT_TOKEN = "7426243703:AAG91JEHkvMV417YanjSWhsAmTKTkwCDaag"

# Create bot instance
bot = Bot(token=TOKEN)

# Directory to hold account files
ACCOUNTS_DIR = 'accounts'

# Essential account files
ESSENTIAL_FILES = ['Valorant.txt', 'league of legends.txt']

# Rate limiting parameters
REQUEST_LIMIT = 10
REQUEST_WINDOW = 60  # Number of seconds per window

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,  # أو المستوى الذي تحتاجه مثل logging.INFO
    format='%(asctime)s - %(name)s - %(levellevel)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Dictionary to hold all data
data = {
    "shortcuts": {},
    "account_types": ["Valorant", "league of legends"],
    "blocked_users": set(),
    "allowed_channels": set(),
    "allow_all_channels": True,
    "enabled": True,
    "user_daily_limits": {},
    "daily_limit": 5,
    "unlimited_access": False,
    "user_data": {},
    "maintenance_mode": False,
    "premium_users": set(),
    "user_requests": defaultdict(list),
    "premium_daily_limit": 50,
    "unlimited_access_premium_plus": False,
    "premium_plus_users": set(),
    "admins": set(),
    "user_last_button_press": {},  # Field for tracking last button press time
}

# Function to install missing libraries
def install_missing_libraries():
    required_libraries = [
        "python-telegram-bot",
        "aiohttp",
        "apscheduler",
        "matplotlib"
    ]

    installed_libraries = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze']).decode().split('\n')
    installed_libraries = [pkg.split('==')[0] for pkg in installed_libraries]

    missing_libraries = [lib for lib in required_libraries if lib not in installed_libraries]

    if missing_libraries:
        f = io.StringIO()  # Create a StringIO object to capture stdout and stderr
        with redirect_stdout(f), redirect_stderr(f):
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', *missing_libraries])
        with open('requirements.txt', 'w') as file:
            file.write('\n'.join(required_libraries))

# Ensure libraries are installed
install_missing_libraries()

# Clear the screen to hide previous messages
if os.name == 'nt':  # For Windows
    os.system('cls')
else:  # For macOS and Linux
    os.system('clear')

print("The bot is running successfully.")

# Ensure necessary directories and files are present
def ensure_directories_and_files():
    if not os.path.exists(ACCOUNTS_DIR):
        os.makedirs(ACCOUNTS_DIR)

    # Create essential txt files if they don't exist
    for filename in ESSENTIAL_FILES:
        file_path = os.path.join(ACCOUNTS_DIR, filename)
        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                pass

    # Create JSON file if it doesn't exist
    if not os.path.exists('data.json'):
        with open('data.json', 'w') as f:
            json.dump(data, f)

    # Create SQLite database if it doesn't exist
    conn = sqlite3.connect('activity_log.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS activity_log
                      (timestamp TEXT, user_id INTEGER, activity_type TEXT, details TEXT)''')
    conn.commit()
    conn.close()

ensure_directories_and_files()

# Load data from file
def load_data():
    global data
    try:
        if os.path.exists('data.json'):
            with open('data.json', 'r', encoding='utf-8') as file:
                loaded_data = json.load(file)
                # Update the global data dictionary with loaded data
                data.update(loaded_data)
                # Convert lists back to sets
                data['blocked_users'] = set(data.get('blocked_users', []))
                data['allowed_channels'] = set(data.get('allowed_channels', []))
                data['premium_users'] = set(data.get('premium_users', []))
                data['premium_plus_users'] = set(data.get('premium_plus_users', []))
                data['user_requests'] = defaultdict(list, {int(k): v for k, v in data.get('user_requests', {}).items()})
                data['user_daily_limits'] = {int(k): (datetime.fromisoformat(v[0]), v[1]) for k, v in data.get('user_daily_limits', {}).items()}
                data['admins'] = set(data.get('admins', []))
        else:
            save_data()
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(f"Error loading data: {e}")
        save_data()

# Save data to file
def save_data():
    with open('data.json', 'w', encoding='utf-8') as file:
        # Convert sets and defaultdicts to lists and dicts for JSON serialization
        data_to_save = data.copy()
        data_to_save['blocked_users'] = list(data_to_save['blocked_users'])
        data_to_save['allowed_channels'] = list(data_to_save['allowed_channels'])
        data_to_save['premium_users'] = list(data_to_save['premium_users'])
        data_to_save['premium_plus_users'] = list(data_to_save['premium_plus_users'])
        data_to_save['user_requests'] = dict(data_to_save['user_requests'])
        data_to_save['user_daily_limits'] = {k: (v[0].isoformat(), v[1]) for k, v in data_to_save['user_daily_limits'].items()}
        data_to_save['admins'] = list(data_to_save['admins'])
        json.dump(data_to_save, file, ensure_ascii=False, indent=4)

# Load data when the bot starts
load_data()

def is_owner(user_id):
    return user_id == OWNER_ID

def is_admin(user_id):
    return user_id == OWNER_ID or user_id in data['admins']

def is_blocked(user_id):
    if user_id in data['blocked_users']:
        if 'timeout_end' in data['user_data'].get(user_id, {}):
            timeout_end = datetime.fromisoformat(data['user_data'][user_id]['timeout_end'])
            if datetime.now() < timeout_end:
                return timeout_end
            else:
                del data['user_data'][user_id]['timeout_end']
                data['blocked_users'].discard(user_id)
                save_data()
                return False
        return True
    return False

def is_allowed_channel(chat_id):
    return data['allow_all_channels'] or chat_id in data['allowed_channels']

def is_rate_limited(user_id):
    current_time = time.time()
    if user_id in data['user_requests']:
        requests = data['user_requests'][user_id]
        data['user_requests'][user_id] = [req for req in requests if req > current_time - REQUEST_WINDOW]
    else:
        data['user_requests'][user_id] = []

    if len(data['user_requests'][user_id]) >= REQUEST_LIMIT:
        return True

    data['user_requests'][user_id].append(current_time)
    return False

def get_next_accounts(account_type="accounts", quantity=1):
    filename = os.path.join(ACCOUNTS_DIR, f'{account_type}.txt')
    if not os.path.exists(filename):
        return []

    with open(filename, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    if not lines:
        return []

    accounts = [lines.pop(0).strip() for _ in range(min(quantity, len(lines)))]

    with open(filename, 'w', encoding='utf-8') as file:
        file.writelines(lines)
    return accounts

def get_random_account():
    account_files = [f for f in os.listdir(ACCOUNTS_DIR) if f.endswith('.txt')]
    if not account_files:
        return None, None

    random_file = random.choice(account_files)
    account_type = os.path.splitext(random_file)[0]
    account = get_next_account(account_type)
    return account, account_type

def get_next_account(account_type="accounts"):
    accounts = get_next_accounts(account_type, 1)
    return accounts[0] if accounts else None

def parse_account_info(account_info, account_type):
    if account_type.lower() == "league of legends":
        parts = account_info.split('\n')
        if len(parts) == 4:
            user_pass, region, level, nickname = parts
            return (f"Username: {user_pass.split(':')[0]}\n"
                    f"Password: {user_pass.split(':')[1]}\n"
                    f"Region: {region.split('=')[1].strip()}\n"
                    f"Level: {level.split('=')[1].strip()}\n"
                    f"Nickname: {nickname.split('=')[1].strip()}")
        else:
            return account_info  # Return the raw info if it doesn't match the expected format
    else:
        user_pass = account_info.split(' | ')[0]
        return f"Username: {user_pass.split(':')[0]}\nPassword: {user_pass.split(':')[1]}"

def check_daily_limit(user_id):
    if is_owner(user_id):
        return 0

    current_time = datetime.now()

    if user_id in data['premium_plus_users']:
        if data['unlimited_access_premium_plus']:
            return 0
        limit = data['premium_plus_daily_limit']
    elif user_id in data['premium_users']:
        limit = data['premium_daily_limit']
    else:
        limit = data['daily_limit']

    if user_id in data['user_daily_limits']:
        last_access_time, count = data['user_daily_limits'][user_id]
        if last_access_time.date() == current_time.date():
            return count
        else:
            data['user_daily_limits'][user_id] = (current_time, 0)
            save_data()
            return 0
    else:
        data['user_daily_limits'][user_id] = (current_time, 0)
        save_data()
        return 0

def increment_daily_limit(user_id):
    if is_owner(user_id):
        return

    current_time = datetime.now()
    if user_id in data['user_daily_limits']:
        last_access_time, count = data['user_daily_limits'][user_id]
        if last_access_time.date() == current_time.date():
            data['user_daily_limits'][user_id] = (last_access_time, count + 1)
        else:
            data['user_daily_limits'][user_id] = (current_time, 1)
    else:
        data['user_daily_limits'][user_id] = (current_time, 1)
    save_data()

def reset_user_limit(user_id):
    if user_id in data['user_daily_limits']:
        del data['user_daily_limits'][user_id]
        save_data()

def reset_all_free_limits():
    global data
    data['user_daily_limits'] = {k: v for k, v in data['user_daily_limits'].items() if k in data['premium_users'] or k in data['premium_plus_users']}
    save_data()

def reset_all_premium_limits():
    global data
    for user_id in data['premium_users']:
        if user_id in data['user_daily_limits']:
            del data['user_daily_limits'][user_id]
    save_data()

def reset_all_premium_plus_limits():
    global data
    for user_id in data['premium_plus_users']:
        if user_id in data['user_daily_limits']:
            del data['user_daily_limits'][user_id]
    save_data()

def update_user_data(user_id, username):
    current_time = datetime.now().isoformat()
    if user_id not in data['user_data']:
        data['user_data'][user_id] = {
            "username": username,
            "first_use": current_time,
            "last_use": current_time,
            "use_count": 1,
            "last_activity": current_time  # Add last_activity field
        }
    else:
        data['user_data'][user_id]["username"] = username  # Ensure the username is updated
        data['user_data'][user_id]["last_use"] = current_time
        data['user_data'][user_id]["use_count"] += 1
        data['user_data'][user_id]["last_activity"] = current_time  # Update last_activity
    save_data()

def update_last_activity(user_id):
    current_time = datetime.now().isoformat()
    if user_id in data['user_data']:
        data['user_data'][user_id]['last_activity'] = current_time
    else:
        data['user_data'][user_id] = {"last_activity": current_time}
    save_data()

def log_activity(user_id, activity_type, details):
    conn = sqlite3.connect('activity_log.db')
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat()
    cursor.execute('''INSERT INTO activity_log (timestamp, user_id, activity_type, details)
                      VALUES (?, ?, ?, ?)''', (timestamp, user_id, activity_type, details))
    conn.commit()
    conn.close()

def detect_unusual_activity(user_id):
    # Add logic to detect unusual activity
    return False

def get_statistics():
    conn = sqlite3.connect('activity_log.db')
    cursor = conn.cursor()
    cursor.execute('''SELECT COUNT(DISTINCT user_id) FROM activity_log''')
    total_users = cursor.fetchone()[0]
    cursor.execute('''SELECT COUNT(DISTINCT user_id) FROM activity_log WHERE timestamp > datetime('now', '-10 minutes')''')
    active_users = cursor.fetchone()[0]
    conn.close()
    return total_users, active_users

def generate_report():
    conn = sqlite3.connect('activity_log.db')
    cursor = conn.cursor()
    cursor.execute('''SELECT DATE(timestamp), COUNT(*) FROM activity_log GROUP BY DATE(timestamp)''')
    data = cursor.fetchall()
    conn.close()

    dates = [row[0] for row in data]
    counts = [row[1] for row in data]

    plt.figure(figsize=(10, 6))
    plt.plot(dates, counts, marker='o')
    plt.title('Daily Activity Report')
    plt.xlabel('Date')
    plt.ylabel('Number of Activities')
    plt.grid(True)
    plt.savefig('activity_report.png')

def send_alert(subject, message):
    msg = MIMEText(message)
    msg['Subject'] = subject
    msg['From'] = 'your-email@example.com'
    msg['To'] = 'admin@example.com'
    with smtplib.SMTP('smtp.example.com') as server:
        server.login('your-email@example.com', 'your-password')
        server.sendmail('your-email@example.com', ['admin@example.com'], msg.as_string())

def check_for_alerts():
    total_users, active_users = get_statistics()
    if active_users > 100:  # Example threshold
        send_alert('High Activity Alert', f'There are currently {active_users} active users.')

async def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    timeout_end = is_blocked(user_id)
    if timeout_end:
        if timeout_end is True:
            await update.message.reply_text("You have been permanently banned from using the bot.")
        else:
            await update.message.reply_text(f"You are currently in timeout until {timeout_end}. Please try again later.")
        return

    if data['maintenance_mode'] and not is_owner(user_id):
        await update.message.reply_text("The bot is currently under maintenance. Please try again later.")
        return

    update_user_data(user_id, username)
    log_activity(user_id, "start", "Started bot interaction")

    await update.message.reply_text("Hello! Use /free to get an account or /feedbackmenu to report an issue or give feedback.")

async def premium(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if is_admin(user_id):
        await update.message.reply_text("Welcome Admin! This is the premium section.")
        await show_premium_menu(update, context)
    elif user_id in data['premium_users']:
        await update.message.reply_text(f"Welcome {update.message.from_user.username}! This is the premium section. Here are your available account types.")
        await show_premium_menu(update, context)
    else:
        await update.message.reply_text("You are not a premium user. Please upgrade to access this section.")

async def premium_plus(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if is_admin(user_id) or user_id in data['premium_plus_users']:
        await show_premium_plus_menu(update, context)
    else:
        await update.message.reply_text("You are not a premium plus user. Please upgrade to access this section.")

async def block_user(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("This command is for admins only.")
        return

    target_user = int(context.args[0])
    data['blocked_users'].add(target_user)
    save_data()
    await update.message.reply_text(f"User with ID {target_user} has been blocked.")
    try:
        await context.bot.send_message(chat_id=target_user, text="You have been blocked by the bot.")
    except Exception as e:
        logger.error(f"Failed to send block message to user {target_user}: {e}")

async def unblock_user(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("This command is for admins only.")
        return

    target_user = int(context.args[0])
    data['blocked_users'].discard(target_user)
    save_data()
    await update.message.reply_text(f"User with ID {target_user} has been unblocked.")
    try:
        await context.bot.send_message(chat_id=target_user, text="Your block has been removed. You can use the bot again.")
    except Exception as e:
        logger.error(f"Failed to send unblock message to user {target_user}: {e}")

async def timeout_user(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("This command is for admins only.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Please provide user ID and duration (e.g., 12345 1h for 1 hour timeout).")
        return

    try:
        target_user_id, duration_str = args
        target_user_id = int(target_user_id)
        if duration_str.endswith('m'):
            timeout_duration = timedelta(minutes=int(duration_str[:-1]))
        elif duration_str.endswith('h'):
            timeout_duration = timedelta(hours=int(duration_str[:-1]))
        elif duration_str.endswith('d'):
            timeout_duration = timedelta(days=int(duration_str[:-1]))
        else:
            await update.message.reply_text("Invalid duration format. Use 'm' for minutes, 'h' for hours, or 'd' for days (e.g., 1h for 1 hour).")
            return

        end_time = datetime.now() + timeout_duration
        data['blocked_users'].add(target_user_id)
        if target_user_id not in data['user_data']:
            data['user_data'][target_user_id] = {}
        data['user_data'][target_user_id]['timeout_end'] = end_time.isoformat()
        save_data()
        await update.message.reply_text(f"User with ID {target_user_id} has been timed out until {end_time}.")
        try:
            await context.bot.send_message(chat_id=target_user_id, text=f"You are timed out until {end_time}.")
        except Exception as e:
            logger.error(f"Failed to send timeout message to user {target_user_id}: {e}")
    except ValueError:
        await update.message.reply_text("Invalid user ID or duration format.")

async def remove_timeout(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("This command is for admins only.")
        return

    target_user_id = int(context.args[0])
    if 'timeout_end' in data['user_data'].get(target_user_id, {}):
        del data['user_data'][target_user_id]['timeout_end']
    data['blocked_users'].discard(target_user_id)
    save_data()
    await update.message.reply_text(f"Timeout removed for user with ID {target_user_id}.")
    try:
        await context.bot.send_message(chat_id=target_user_id, text="Your timeout has been removed. You can use the bot again.")
    except Exception as e:
        logger.error(f"Failed to send timeout removal message to user {target_user_id}: {e}")

async def list_blocked(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("This command is for admins only.")
        return

    if data['blocked_users']:
        blocked_list = "\n".join(str(user_id) for user_id in data['blocked_users'])
        await update.message.reply_text(f"Blocked Users:\n{blocked_list}")
    else:
        await update.message.reply_text("There are no users currently blocked from using the bot.")

async def add_section(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("This command is for admins only.")
        return

    section_name = ' '.join(context.args)
    if not section_name:
        await update.message.reply_text("Please specify a section name.")
        return

    section_file = os.path.join(ACCOUNTS_DIR, f'{section_name}.txt')
    if not os.path.exists(section_file):
        open(section_file, 'w').close()
        data['account_types'].append(section_name)
        save_data()
        await update.message.reply_text(f"Section '{section_name}' has been added.")
    else:
        await update.message.reply_text(f"Section '{section_name}' already exists.")

async def delete_section(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("This command is for admins only.")
        return

    section_name = ' '.join(context.args)
    if not section_name:
        await update.message.reply_text("Please specify a section name.")
        return

    section_file = os.path.join(ACCOUNTS_DIR, f'{section_name}.txt')
    if os.path.exists(section_file):
        os.remove(section_file)
        if section_name in data['account_types']:
            data['account_types'].remove(section_name)
            save_data()
        await update.message.reply_text(f"Section '{section_name}' has been deleted.")
    else:
        await update.message.reply_text(f"Section '{section_name}' does not exist.")

async def handle_upload_section(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("This command is for admins only.")
        return

    await update.message.reply_text("Please specify the section name to add the accounts to:")
    context.user_data['awaiting_section_name'] = True

async def handle_owner_commands(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("This menu is for admins only.")
        return

    if context.user_data.get('awaiting_section_name'):
        section_name = update.message.text.strip()
        section_file = os.path.join(ACCOUNTS_DIR, f'{section_name}.txt')

        if not section_file:
            await update.message.reply_text(f"Section '{section_name}' does not exist. Please create the section first.")
            return

        context.user_data['section_name'] = section_name
        await update.message.reply_text(f"Section '{section_name}' selected. Now, please upload the txt file with accounts:")
        context.user_data['awaiting_upload'] = True
        context.user_data['awaiting_section_name'] = False
    elif context.user_data.get('awaiting_upload'):
        await update.message.reply_text("Please upload the txt file with accounts.")
    else:
        total_users, active_users = get_statistics()
        keyboard = [
            [InlineKeyboardButton("Block User", callback_data='block_user')],
            [InlineKeyboardButton("Unblock User", callback_data='unblock_user')],
            [InlineKeyboardButton("Timeout User", callback_data='timeout_user')],
            [InlineKeyboardButton("Remove Timeout", callback_data='remove_timeout')],
            [InlineKeyboardButton("List Blocked Users", callback_data='list_blocked')],
            [InlineKeyboardButton("Add Section", callback_data='add_section')],
            [InlineKeyboardButton("Delete Section", callback_data='delete_section')],
            [InlineKeyboardButton("Upload Accounts", callback_data='upload_accounts')],
            [InlineKeyboardButton("Free User Management", callback_data='free_user_management')],
            [InlineKeyboardButton("Premium User Management", callback_data='premium_user_management')],
            [InlineKeyboardButton("Premium Plus User Management", callback_data='premium_plus_user_management')],
            [InlineKeyboardButton("Enable Maintenance Mode", callback_data='enable_maintenance')],
            [InlineKeyboardButton("Disable Maintenance Mode", callback_data='disable_maintenance')],
            [InlineKeyboardButton("Add Admin", callback_data='add_admin')],
            [InlineKeyboardButton("Remove Admin", callback_data='remove_admin')],
            [InlineKeyboardButton("Monitoring", callback_data='monitoring')],
            [InlineKeyboardButton("Show Account Statistics", callback_data='show_account_statistics')],
            [InlineKeyboardButton("Announcement", callback_data='announcement')]  # New Announcement button
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f'Owner Commands:\nTotal Users: {total_users}\nActive Users: {active_users}', reply_markup=reply_markup)

async def handle_free_user_management(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Set Daily Limit", callback_data='set_daily_limit')],
        [InlineKeyboardButton("Set Unlimited Access", callback_data='set_unlimited_access')],
        [InlineKeyboardButton("Reset Free User Limits", callback_data='reset_all_free_limits')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text('Free User Management:', reply_markup=reply_markup)

async def handle_premium_user_management(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Add Premium User", callback_data='add_premium_user')],
        [InlineKeyboardButton("Remove Premium User", callback_data='remove_premium_user')],
        [InlineKeyboardButton("Set Premium Daily Limit", callback_data='set_premium_daily_limit')],
        [InlineKeyboardButton("Reset Premium User Limits", callback_data='reset_all_premium_limits')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text('Premium User Management:', reply_markup=reply_markup)

async def handle_premium_plus_user_management(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Add Premium Plus User", callback_data='add_premium_plus_user')],
        [InlineKeyboardButton("Remove Premium Plus User", callback_data='remove_premium_plus_user')],
        [InlineKeyboardButton("Set Premium Plus Daily Limit", callback_data='set_premium_plus_daily_limit')],
        [InlineKeyboardButton("Reset Premium Plus User Limits", callback_data='reset_all_premium_plus_limits')],
        [InlineKeyboardButton("Unlimited Access", callback_data='set_unlimited_access_premium_plus')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.reply_text('Premium Plus User Management:', reply_markup=reply_markup)

async def upload_accounts(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("This command is for admins only.")
        return

    await update.message.reply_text("Please specify the section name to add the accounts to:")
    context.user_data['awaiting_section_name'] = True

async def handle_document(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if not is_admin(user_id):
        await update.message.reply_text("This command is for admins only.")
        return

    if context.user_data.get('awaiting_upload'):
        document = update.message.document
        section_name = context.user_data.get('section_name')

        if not section_name:
            await update.message.reply_text("No section specified. Please specify the section name first.")
            return

        section_file = os.path.join(ACCOUNTS_DIR, f'{section_name}.txt')
        if not os.path.exists(section_file):
            await update.message.reply_text(f"Section '{section_name}' does not exist.")
            return

        file_path = os.path.join(ACCOUNTS_DIR, f'temp_{user_id}.txt')
        new_file = await context.bot.get_file(document.file_id)
        await new_file.download_to_drive(file_path)

        with open(file_path, 'r', encoding='utf-8') as temp_file:
            accounts = temp_file.readlines()

        with open(section_file, 'a', encoding='utf-8') as section_file:
            section_file.writelines(accounts)

        os.remove(file_path)
        del context.user_data['section_name']
        context.user_data['awaiting_upload'] = False

        await update.message.reply_text(f"Accounts have been added to section '{section_name}'.")

async def handle_announcement(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id

    if not is_owner(user_id):
        await query.message.reply_text("This command is for the owner only.")
        return

    await query.message.reply_text("Please enter the announcement message:")
    context.user_data['awaiting_announcement'] = True

async def broadcast_announcement(context: CallbackContext, announcement: str):
    sent_users = set()
    blocked_users = []  # List to store users who blocked the bot
    for user_id in data['user_data'].keys():
        if user_id != OWNER_ID and user_id not in sent_users:  # Ensure the announcement is not sent to the owner or to the same user again
            try:
                await context.bot.send_message(chat_id=user_id, text=f"Announcement\n\n{announcement}")
                sent_users.add(user_id)
            except Exception as e:
                logger.error(f"Failed to send announcement to user {user_id}: {e}")
                if "bot was blocked by the user" in str(e):
                    blocked_users.append(user_id)
                    data['blocked_users'].add(user_id)
                    save_data()  # Save data to ensure the blocked user is recorded

    # Notify owner about users who blocked the bot
    if blocked_users:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"The following users have blocked the bot and were subsequently blocked:\n{', '.join(map(str, blocked_users))}")

    # Send a confirmation message to the owner
    owner_message = f"The announcement has been sent to all users."
    await context.bot.send_message(chat_id=OWNER_ID, text=owner_message)

async def handle_faq(update: Update, context: CallbackContext):
    # Define your FAQ messages here
    faq_message = (
        "FAQs:\n\n"
        "1. How to use the bot?\n"
        " - Use /start to begin.\n"
        " - Use /free to get a free account.\n"
        " - Use /feedbackmenu to report an issue or give feedback.\n"
        " - Use /premium to access premium features.\n"
        " - Use /premium_plus to access premium plus features.\n\n"
        "2. How to become a premium user?\n"
        " - Contact support to upgrade your account.\n\n"
        "3. What to do if I encounter an issue?\n"
        " - Use /feedbackmenu to report any issues or provide feedback.\n\n"
        "Q: What is the source of the accounts?\n"
        "A: The accounts are cracked randomly via the bot's API from various external sources. The details of these sources are not disclosed.\n\n"
        "Q: Why is the account not working?\n"
        "A: It has likely been changed by the owner. Please try another account.\n\n"
        "Q: Why is the account used by multiple people?\n"
        "A: The accounts are cracked and obtained from various sources, including the main source and other sources, which means they might be used by other people.\n\n"
        "Q: Are the accounts safe to use?\n"
        "A: The accounts provided are cracked accounts, which come with risks. We recommend using them with caution.\n\n"
        "Note: We are not responsible for any issues related to the accounts as they are obtained from external sources via a custom API. The details of these sources are not disclosed. If you encounter any technical issues with the bot itself, please use /feedbackmenu to report them."
    )

    await update.message.reply_text(faq_message)

# Function to show the custom menu
async def show_menu(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if data['maintenance_mode'] and not is_owner(user_id):
        await update.message.reply_text("The bot is currently under maintenance. Please try again later.")
        return
    if is_rate_limited(user_id):
        await update.message.reply_text("You are being rate limited. Please try again later.")
        return

    if user_id in data['premium_users']:
        await update.message.reply_text("You are a premium user. Please use the /premium command to access premium accounts.")
        return

    if user_id in data['premium_plus_users']:
        await update.message.reply_text("You are a premium plus user. Please use the /premium_plus command to access premium plus accounts.")
        return

    keyboard = [[InlineKeyboardButton(account_type, callback_data=f'get_account_{account_type}')] for account_type in data['account_types']]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Please choose an option:', reply_markup=reply_markup)

# Function to show the premium menu
async def show_premium_menu(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if data['maintenance_mode'] and not is_owner(user_id):
        await update.message.reply_text("The bot is currently under maintenance. Please try again later.")
        return
    if is_rate_limited(user_id):
        await update.message.reply_text("You are being rate limited. Please try again later.")
        return

    keyboard = [[InlineKeyboardButton(account_type, callback_data=f'get_premium_account_{account_type}')] for account_type in data['account_types']]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Please choose a premium account type:', reply_markup=reply_markup)

# Function to show the premium plus menu
async def show_premium_plus_menu(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if data['maintenance_mode'] and not is_owner(user_id):
        await update.message.reply_text("The bot is currently under maintenance. Please try again later.")
        return
    if is_rate_limited(user_id):
        await update.message.reply_text("You are being rate limited. Please try again later.")
        return

    keyboard = [[InlineKeyboardButton(account_type, callback_data=f'get_premium_plus_account_{account_type}')] for account_type in data['account_types']]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=user_id, text=f'Welcome {update.message.from_user.mention_html()}! This is the premium plus section. Please choose a premium plus account type:', reply_markup=reply_markup, parse_mode=ParseMode.HTML)

# Function to show the feedback menu
async def show_feedback_menu(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if data['maintenance_mode'] and not is_owner(user_id):
        await update.message.reply_text("The bot is currently under maintenance. Please try again later.")
        return
    if is_rate_limited(user_id):
        await update.message.reply_text("You are being rate limited. Please try again later.")
        return

    keyboard = [
        [InlineKeyboardButton("Report Issue", callback_data='report_issue')],
        [InlineKeyboardButton("Give Feedback", callback_data='give_feedback')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Please choose an option:', reply_markup=reply_markup)

async def handle_menu_choice(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    choice = query.data

    user_id = query.from_user.id
    current_time = time.time()

    # Check the last button press time for the user
    last_press_time = data['user_last_button_press'].get(user_id, 0)
    if not is_owner(user_id) and current_time - last_press_time < 3:
        await query.message.reply_text("Please wait 3 seconds before trying again.")
        return

    # Update the last button press time for the user
    data['user_last_button_press'][user_id] = current_time

    timeout_end = is_blocked(user_id)
    if timeout_end:
        if timeout_end is True:
            await query.edit_message_text("You have been permanently banned from using the bot.")
        else:
            await query.edit_message_text(f"You are currently in timeout until {timeout_end}. Please try again later.")
        return

    if data['maintenance_mode'] and not is_owner(user_id):
        await query.message.reply_text("The bot is currently under maintenance. Please try again later.")
        return

    if not is_admin(user_id) and choice in ['block_user', 'unblock_user', 'timeout_user', 'remove_timeout', 'list_blocked', 'add_section', 'delete_section', 'upload_accounts', 'set_daily_limit', 'set_unlimited_access', 'reset_all_free_limits', 'reset_all_premium_limits', 'reset_all_premium_plus_limits', 'enable_maintenance', 'disable_maintenance', 'free_user_management', 'premium_user_management', 'premium_plus_user_management', 'add_premium_user', 'remove_premium_user', 'set_premium_daily_limit', 'add_premium_plus_user', 'remove_premium_plus_user', 'set_premium_plus_daily_limit', 'set_unlimited_access_premium_plus', 'add_admin', 'remove_admin', 'show_account_statistics', 'announcement']:  # Added 'announcement' here
        await query.message.reply_text("You do not have the necessary permissions to access this command.")
        return

    if choice == 'monitoring':
        total_users, active_users = get_statistics()
        await query.message.reply_text(f'Monitoring:\nTotal Users: {total_users}\nActive Users: {active_users}')
    elif choice.startswith('get_account_'):
        account_type = choice.split('get_account_')[1]
        username = query.from_user.username

        daily_limit_count = check_daily_limit(user_id)
        if user_id not in data['premium_users'] and user_id not in data['premium_plus_users'] and daily_limit_count >= data['daily_limit'] and not data['unlimited_access']:
            last_access_time, _ = data['user_daily_limits'][user_id]
            next_access_time = last_access_time + timedelta(days=1)
            await query.message.reply_text(f"You have reached your daily limit. You can use the bot again at {next_access_time.strftime('%Y-%m-%d %H:%M:%S')}.")
            return
        elif user_id in data['premium_users'] and daily_limit_count >= data['premium_daily_limit']:
            await query.message.reply_text("You have reached your daily limit for premium requests. Please try again tomorrow.")
            return
        elif user_id in data['premium_plus_users'] and daily_limit_count >= data['premium_plus_daily_limit']:
            await query.message.reply_text("You have reached your daily limit for premium plus requests. Please try again tomorrow.")
            return

        account = get_next_account(account_type)
        if account:
            parsed_info = parse_account_info(account, account_type)
            await query.message.reply_text(f"Account Info:\n{parsed_info}\nAccount Type: {account_type}")
            await query.message.reply_text(
                f"Thank you for using the bot. Here is your account information:\n{query.from_user.first_name}!\n"
                
            )
            increment_daily_limit(user_id)
            update_user_data(user_id, username)
        else:
            await query.edit_message_text(f"No accounts available for {account_type}.")
    elif choice.startswith('get_premium_account_'):
        if user_id not in data['premium_users'] and not is_owner(user_id):
            await query.message.reply_text("You do not have access to this section.")
            return

        account_type = choice.split('get_premium_account_')[1]
        username = query.from_user.username

        daily_limit_count = check_daily_limit(user_id)
        if daily_limit_count >= data['premium_daily_limit']:
            await query.message.reply_text("You have reached your daily limit for premium requests. Please try again tomorrow.")
            return

        account = get_next_account(account_type)
        if account:
            parsed_info = parse_account_info(account, account_type)
            await query.message.reply_text(f"Premium Account Info:\n{parsed_info}\nAccount Type: {account_type}")
            await query.message.reply_text(
                f"Thank you for using the premium section. Here is your account information:\n{query.from_user.first_name}!\n"
                
            )
            increment_daily_limit(user_id)
            update_user_data(user_id, username)
        else:
            await query.edit_message_text(f"No premium accounts available for {account_type}.")
    elif choice.startswith('get_premium_plus_account_'):
        if user_id not in data['premium_plus_users'] and not is_owner(user_id):
            await query.message.reply_text("You do not have access to this section.")
            return

        account_type = choice.split('get_premium_plus_account_')[1]
        username = query.from_user.username

        daily_limit_count = check_daily_limit(user_id)
        if daily_limit_count >= data['premium_plus_daily_limit']:
            await query.message.reply_text("You have reached your daily limit for premium plus requests. Please try again tomorrow.")
            return

        account = get_next_account(account_type)
        if account:
            parsed_info = parse_account_info(account, account_type)
            await query.message.reply_text(f"Premium Plus Account Info:\n{parsed_info}\nAccount Type: {account_type}")
            await query.message.reply_text(
                f"Thank you for using the premium plus section. Here is your account information:\n{query.from_user.first_name}!\n"
                
            )
            increment_daily_limit(user_id)
            update_user_data(user_id, username)
        else:
            await query.edit_message_text(f"No premium plus accounts available for {account_type}.")
    elif choice == 'premium_plus':
        await premium_plus(update, context)
    elif choice == 'premium':
        await premium(update, context)
    elif choice == 'report_issue':
        await query.message.reply_text("Please describe the issue you are facing:")
        context.user_data['awaiting_issue'] = True
    elif choice == 'give_feedback':
        await query.message.reply_text("Please provide your feedback:")
        context.user_data['awaiting_feedback'] = True
    elif choice == 'block_user':
        await query.message.reply_text("Please enter the user ID to block:")
        context.user_data['awaiting_block_user_id'] = True
    elif choice == 'unblock_user':
        await query.message.reply_text("Please enter the user ID to unblock:")
        context.user_data['awaiting_unblock_user_id'] = True
    elif choice == 'timeout_user':
        await query.message.reply_text("Please enter the user ID and duration (e.g., 12345 1h for 1 hour timeout):")
        context.user_data['awaiting_timeout_user'] = True
    elif choice == 'remove_timeout':
        await query.message.reply_text("Please enter the user ID to remove the timeout:")
        context.user_data['awaiting_remove_timeout_user'] = True
    elif choice == 'list_blocked':
        if data['blocked_users']:
            blocked_list = "\n".join(str(user_id) for user_id in data['blocked_users'])
            await query.message.reply_text(f"Blocked Users:\n{blocked_list}")
        else:
            await query.message.reply_text("There are no users currently blocked from using the bot.")
    elif choice == 'add_section':
        await query.message.reply_text("Please enter the name of the new section:")
        context.user_data['awaiting_add_section'] = True
    elif choice == 'delete_section':
        await query.message.reply_text("Please enter the name of the section to delete:")
        context.user_data['awaiting_delete_section'] = True
    elif choice == 'upload_accounts':
        await query.message.reply_text("Please specify the section name to add the accounts to:")
        context.user_data['awaiting_section_name'] = True
    elif choice == 'set_daily_limit':
        await query.message.reply_text("Please enter the new daily limit for free users:")
        context.user_data['awaiting_daily_limit'] = True
    elif choice == 'set_unlimited_access':
        await query.message.reply_text("Please enter 'on' to enable unlimited access or 'off' to disable unlimited access:")
        context.user_data['awaiting_unlimited_access'] = True
    elif choice == 'reset_all_free_limits':
        reset_all_free_limits()
        await query.message.reply_text("All free user daily limits have been reset.")
    elif choice == 'reset_all_premium_limits':
        reset_all_premium_limits()
        await query.message.reply_text("All premium user daily limits have been reset.")
    elif choice == 'reset_all_premium_plus_limits':
        reset_all_premium_plus_limits()
        await query.message.reply_text("All premium plus user daily limits have been reset.")
    elif choice == 'enable_maintenance':
        data['maintenance_mode'] = True
        save_data()
        await query.message.reply_text("The bot is now in maintenance mode.")
        # Notify all users about maintenance mode
        for user_id in data['user_data'].keys():
            if user_id != OWNER_ID:
                try:
                    await bot.send_message(chat_id=user_id, text="The bot is currently under maintenance. Please try again later.")
                except Exception as e:
                    logger.error(f"Failed to send maintenance message to user {user_id}: {e}")
    elif choice == 'disable_maintenance':
        data['maintenance_mode'] = False
        save_data()
        await query.message.reply_text("The bot is now out of maintenance mode.")
        # Notify all users about end of maintenance mode
        for user_id in data['user_data'].keys():
            if user_id != OWNER_ID:
                try:
                    await bot.send_message(chat_id=user_id, text="The bot is now available. You can use it again.")
                except Exception as e:
                    logger.error(f"Failed to send availability message to user {user_id}: {e}")
    elif choice == 'free_user_management':
        await handle_free_user_management(update, context)
    elif choice == 'premium_user_management':
        await handle_premium_user_management(update, context)
    elif choice == 'premium_plus_user_management':
        await handle_premium_plus_user_management(update, context)
    elif choice == 'add_premium_user':
        await query.message.reply_text("Please enter the user ID to add as premium:")
        context.user_data['awaiting_add_premium_user'] = True
    elif choice == 'remove_premium_user':
        await query.message.reply_text("Please enter the user ID to remove from premium:")
        context.user_data['awaiting_remove_premium_user'] = True
    elif choice == 'set_premium_daily_limit':
        await query.message.reply_text("Please enter the new daily limit for premium users:")
        context.user_data['awaiting_set_premium_daily_limit'] = True
    elif choice == 'add_premium_plus_user':
        await query.message.reply_text("Please enter the user ID to add as premium plus:")
        context.user_data['awaiting_add_premium_plus_user'] = True
    elif choice == 'remove_premium_plus_user':
        await query.message.reply_text("Please enter the user ID to remove from premium plus:")
        context.user_data['awaiting_remove_premium_plus_user'] = True
    elif choice == 'set_premium_plus_daily_limit':
        await query.message.reply_text("Please enter the new daily limit for premium plus users:")
        context.user_data['awaiting_set_premium_plus_daily_limit'] = True
    elif choice == 'set_unlimited_access_premium_plus':
        await query.message.reply_text("Please enter 'on' to enable unlimited access for premium plus users or 'off' to disable unlimited access:")
        context.user_data['awaiting_unlimited_access_premium_plus'] = True
    elif choice == 'add_admin':
        await query.message.reply_text("Please enter the user ID to add as admin:")
        context.user_data['awaiting_add_admin'] = True
    elif choice == 'remove_admin':
        await query.message.reply_text("Please enter the user ID to remove from admin:")
        context.user_data['awaiting_remove_admin'] = True
    elif choice == 'show_account_statistics':
        account_stats = ""
        for account_type in data['account_types']:
            filename = os.path.join(ACCOUNTS_DIR, f'{account_type}.txt')
            with open(filename, 'r', encoding='utf-8') as file:
                count = len(file.readlines())
            account_stats += f"{account_type}: {count} accounts\n"
        await query.message.reply_text(f"Account Statistics:\n{account_stats}")
    elif choice == 'announcement':  # Handle announcement choice
        await handle_announcement(update, context)

async def handle_user_input(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    text = update.message.text

    update_last_activity(user_id)
    log_activity(user_id, "user_input", text)
    if detect_unusual_activity(user_id):
        await update.message.reply_text("Suspicious activity detected. Action will be taken.")
        return

    timeout_end = is_blocked(user_id)
    if timeout_end:
        if timeout_end is True:
            await update.message.reply_text("You have been permanently banned from using the bot.")
        else:
            await update.message.reply_text(f"You are currently in timeout until {timeout_end}. Please try again later.")
        return

    if data['maintenance_mode'] and not is_admin(user_id):
        await update.message.reply_text("The bot is currently under maintenance. Please try again later.")
        return

    if context.user_data.get('awaiting_block_user_id'):
        target_user_id = int(text)
        data['blocked_users'].add(target_user_id)
        save_data()
        context.user_data['awaiting_block_user_id'] = False
        await update.message.reply_text(f"User with ID {target_user_id} has been blocked.")
        try:
            await context.bot.send_message(chat_id=target_user_id, text="You have been blocked by the bot.")
        except Exception as e:
            logger.error(f"Failed to send block message to user {target_user_id}: {e}")
    elif context.user_data.get('awaiting_unblock_user_id'):
        target_user_id = int(text)
        data['blocked_users'].discard(target_user_id)
        save_data()
        context.user_data['awaiting_unblock_user_id'] = False
        await update.message.reply_text(f"User with ID {target_user_id} has been unblocked.")
        try:
            await context.bot.send_message(chat_id=target_user_id, text="Your block has been removed. You can use the bot again.")
        except Exception as e:
            logger.error(f"Failed to send unblock message to user {target_user_id}: {e}")
    elif context.user_data.get('awaiting_timeout_user'):
        try:
            target_user_id, duration_str = text.split()
            target_user_id = int(target_user_id)
            if duration_str.endswith('m'):
                timeout_duration = timedelta(minutes=int(duration_str[:-1]))
            elif duration_str.endswith('h'):
                timeout_duration = timedelta(hours=int(duration_str[:-1]))
            elif duration_str.endswith('d'):
                timeout_duration = timedelta(days=int(duration_str[:-1]))
            else:
                await update.message.reply_text("Invalid duration format. Use 'm' for minutes, 'h' for hours, or 'd' for days (e.g., 1h for 1 hour).")
                return

            end_time = datetime.now() + timeout_duration
            data['blocked_users'].add(target_user_id)
            if target_user_id not in data['user_data']:
                data['user_data'][target_user_id] = {}
            data['user_data'][target_user_id]['timeout_end'] = end_time.isoformat()
            save_data()
            await update.message.reply_text(f"User with ID {target_user_id} has been timed out until {end_time}.")
            try:
                await context.bot.send_message(chat_id=target_user_id, text=f"You are timed out until {end_time}.")
            except Exception as e:
                logger.error(f"Failed to send timeout message to user {target_user_id}: {e}")
        except ValueError:
            await update.message.reply_text("Invalid input. Please provide user ID and duration (e.g., 12345 1h).")
        context.user_data['awaiting_timeout_user'] = False
    elif context.user_data.get('awaiting_remove_timeout_user'):
        target_user_id = int(text)
        if 'timeout_end' in data['user_data'].get(target_user_id, {}):
            del data['user_data'][target_user_id]['timeout_end']
        data['blocked_users'].discard(target_user_id)
        save_data()
        context.user_data['awaiting_remove_timeout_user'] = False
        await update.message.reply_text(f"Timeout removed for user with ID {target_user_id}.")
        try:
            await context.bot.send_message(chat_id=target_user_id, text="Your timeout has been removed. You can use the bot again.")
        except Exception as e:
            logger.error(f"Failed to send timeout removal message to user {target_user_id}: {e}")
    elif context.user_data.get('awaiting_add_section'):
        section_name = text.strip()
        section_file = os.path.join(ACCOUNTS_DIR, f'{section_name}.txt')
        if not os.path.exists(section_file):
            open(section_file, 'w').close()
            data['account_types'].append(section_name)
            save_data()
            await update.message.reply_text(f"Section '{section_name}' has been added.")
        else:
            await update.message.reply_text(f"Section '{section_name}' already exists.")
        context.user_data['awaiting_add_section'] = False
    elif context.user_data.get('awaiting_delete_section'):
        section_name = text.strip()
        section_file = os.path.join(ACCOUNTS_DIR, f'{section_name}.txt')
        if os.path.exists(section_file):
            os.remove(section_file)
            if section_name in data['account_types']:
                data['account_types'].remove(section_name)
                save_data()
            await update.message.reply_text(f"Section '{section_name}' has been deleted.")
        else:
            await update.message.reply_text(f"Section '{section_name}' does not exist.")
        context.user_data['awaiting_delete_section'] = False
    elif context.user_data.get('awaiting_section_name'):
        section_name = text.strip()
        context.user_data['section_name'] = section_name
        await update.message.reply_text(f"Section '{section_name}' selected. Now, please upload the txt file with accounts:")
        context.user_data['awaiting_upload'] = True
    elif context.user_data.get('awaiting_daily_limit'):
        data['daily_limit'] = int(text)
        save_data()
        await update.message.reply_text(f"Daily limit for free users set to {data['daily_limit']} accounts per day.")
        context.user_data['awaiting_daily_limit'] = False
    elif context.user_data.get('awaiting_unlimited_access'):
        if text.lower() == 'on':
            data['unlimited_access'] = True
            await update.message.reply_text("Unlimited access enabled.")
        elif text.lower() == 'off':
            data['unlimited_access'] = False
            await update.message.reply_text("Unlimited access disabled.")
        else:
            await update.message.reply_text("Invalid input. Please enter 'on' or 'off'.")
        save_data()
        context.user_data['awaiting_unlimited_access'] = False
    elif context.user_data.get('awaiting_reset_user_limit'):
        target_user_id = int(text)
        reset_user_limit(target_user_id)
        context.user_data['awaiting_reset_user_limit'] = False
        await update.message.reply_text(f"Daily limit for user with ID {target_user_id} has been reset.")
    elif context.user_data.get('awaiting_issue'):
        issue = text.strip()
        report_bot = Bot(token=REPORT_BOT_TOKEN)
        await report_bot.send_message(chat_id=OWNER_ID, text=f"Issue Report from User ID {user_id}:\n{issue}")
        context.user_data['awaiting_issue'] = False
        await update.message.reply_text("Thank you for reporting the issue. It has been forwarded to the support team.")
    elif context.user_data.get('awaiting_feedback'):
        feedback = text.strip()
        feedback_bot = Bot(token=FEEDBACK_BOT_TOKEN)
        await feedback_bot.send_message(chat_id=OWNER_ID, text=f"Feedback from User ID {user_id}:\n{feedback}")
        context.user_data['awaiting_feedback'] = False
        await update.message.reply_text("Thank you for your feedback. It has been forwarded to the team.")
    elif context.user_data.get('awaiting_add_premium_user'):
        target_user_id = int(text)
        data['premium_users'].add(target_user_id)
        reset_user_limit(target_user_id)  # Reset limit when user is added to premium
        save_data()
        context.user_data['awaiting_add_premium_user'] = False
        await update.message.reply_text(f"User with ID {target_user_id} has been added as premium.")
    elif context.user_data.get('awaiting_remove_premium_user'):
        target_user_id = int(text)
        data['premium_users'].discard(target_user_id)
        reset_user_limit(target_user_id)  # Reset limit when user is removed from premium
        save_data()
        context.user_data['awaiting_remove_premium_user'] = False
        await update.message.reply_text(f"User with ID {target_user_id} has been removed from premium.")
    elif context.user_data.get('awaiting_set_premium_daily_limit'):
        data['premium_daily_limit'] = int(text)
        save_data()
        context.user_data['awaiting_set_premium_daily_limit'] = False
        await update.message.reply_text(f"Premium daily limit set to {data['premium_daily_limit']} accounts per day.")
    elif context.user_data.get('awaiting_add_premium_plus_user'):
        target_user_id = int(text)
        data['premium_plus_users'].add(target_user_id)
        reset_user_limit(target_user_id)  # Reset limit when user is added to premium plus
        save_data()
        context.user_data['awaiting_add_premium_plus_user'] = False
        await update.message.reply_text(f"User with ID {target_user_id} has been added as premium plus.")
    elif context.user_data.get('awaiting_remove_premium_plus_user'):
        target_user_id = int(text)
        data['premium_plus_users'].discard(target_user_id)
        reset_user_limit(target_user_id)  # Reset limit when user is removed from premium plus
        save_data()
        context.user_data['awaiting_remove_premium_plus_user'] = False
        await update.message.reply_text(f"User with ID {target_user_id} has been removed from premium plus.")
    elif context.user_data.get('awaiting_set_premium_plus_daily_limit'):
        data['premium_plus_daily_limit'] = int(text)
        save_data()
        context.user_data['awaiting_set_premium_plus_daily_limit'] = False
        await update.message.reply_text(f"Premium plus daily limit set to {data['premium_plus_daily_limit']} accounts per day.")
    elif context.user_data.get('awaiting_unlimited_access_premium_plus'):
        if text.lower() == 'on':
            data['unlimited_access_premium_plus'] = True
            await update.message.reply_text("Unlimited access for premium plus users enabled.")
        elif text.lower() == 'off':
            data['unlimited_access_premium_plus'] = False
            await update.message.reply_text("Unlimited access for premium plus users disabled.")
        else:
            await update.message.reply_text("Invalid input. Please enter 'on' or 'off'.")
        save_data()
        context.user_data['awaiting_unlimited_access_premium_plus'] = False
    elif context.user_data.get('awaiting_add_admin'):
        target_user_id = int(text)
        if target_user_id == OWNER_ID:
            await update.message.reply_text("Cannot add the owner as admin.")
        else:
            data['admins'].add(target_user_id)
            save_data()
            context.user_data['awaiting_add_admin'] = False
            await update.message.reply_text(f"User with ID {target_user_id} has been added as admin.")
    elif context.user_data.get('awaiting_remove_admin'):
        target_user_id = int(text)
        if target_user_id == OWNER_ID:
            await update.message.reply_text("Cannot remove the owner as admin.")
        else:
            data['admins'].discard(target_user_id)
            save_data()
            context.user_data['awaiting_remove_admin'] = False
            await update.message.reply_text(f"User with ID {target_user_id} has been removed from admin.")
    elif context.user_data.get('awaiting_announcement'):
        announcement = text.strip()
        await broadcast_announcement(context, announcement)
        context.user_data['awaiting_announcement'] = False
        await update.message.reply_text("The announcement has been sent to all users.")

async def set_commands(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "Start the bot"),
        BotCommand("free", "Show account types menu"),
        BotCommand("feedbackmenu", "Show feedback and report menu"),
        BotCommand("ownermenu", "Show owner commands menu (owner only)"),
        BotCommand("premium", "Access premium features"),
        BotCommand("premium_plus", "Access premium plus features"),
        BotCommand("faq", "Show frequently asked questions")  # New FAQ command
    ])

async def update_active_users(application: Application):
    while True:
        total_users, active_users = get_statistics()
        print(f"Total Users: {total_users}, Active Users: {active_users}")
        await asyncio.sleep(60)  # تحقق كل 60 ثانية

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("premium", premium))
    application.add_handler(CommandHandler("premium_plus", premium_plus))
    application.add_handler(CommandHandler("blockuser", block_user))
    application.add_handler(CommandHandler("unblock_user", unblock_user))
    application.add_handler(CommandHandler("timeout_user", timeout_user))
    application.add_handler(CommandHandler("remove_timeout", remove_timeout))
    application.add_handler(CommandHandler("listblocked", list_blocked))
    application.add_handler(CommandHandler("free", show_menu))
    application.add_handler(CommandHandler("feedbackmenu", show_feedback_menu))
    application.add_handler(CommandHandler("ownermenu", handle_owner_commands))
    application.add_handler(CommandHandler("deletesection", delete_section))
    application.add_handler(CommandHandler("faq", handle_faq))  # New FAQ command handler
    application.add_handler(CallbackQueryHandler(handle_menu_choice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_input))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    application.job_queue.run_once(lambda context: asyncio.create_task(set_commands(application)), 0)
    application.job_queue.run_once(lambda context: asyncio.create_task(update_active_users(application)), 0)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(generate_report, 'interval', hours=24)
    scheduler.add_job(check_for_alerts, 'interval', minutes=10)
    scheduler.start()

    application.run_polling()

if __name__ == "__main__":
    main()
