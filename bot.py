import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from database import Database
import os
import time
import threading
from flask import Flask

TOKEN = '8700846869:AAG0z7VXoImnG4aCF0yH6IVfhDbXqY0pzzE'
ADMIN_ID = 8766583877

bot = telebot.TeleBot(TOKEN)
db = Database('bot.db')

def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton('👤 Profile'),
        KeyboardButton('💰 Balance'),
        KeyboardButton('🔗 Referral'),
        KeyboardButton('🛒 Get ChatGPT Plus'),
        KeyboardButton('📥 Deposit'),
        KeyboardButton('📺 Tutorial')
    )
    return markup

def check_and_prompt_membership(chat_id, user_id):
    channels = db.get_all_channels()
    if not channels or user_id == ADMIN_ID:
        return True
        
    unjoined_channels = []
    for channel in channels:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                unjoined_channels.append(channel)
        except Exception:
            unjoined_channels.append(channel)
            
    if unjoined_channels:
        text = "⚠️ **You must join our channels to use this bot!**\n\nPlease join the following channels:"
        markup = InlineKeyboardMarkup()
        for ch in unjoined_channels:
            markup.row(InlineKeyboardButton(f"Join {ch}", url=f"https://t.me/{ch.replace('@', '')}"))
        markup.row(InlineKeyboardButton("✅ I have joined", callback_data="check_joined"))
        
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
        return False
    return True

@bot.callback_query_handler(func=lambda call: call.data == 'check_joined')
def handle_check_joined(call):
    if check_and_prompt_membership(call.message.chat.id, call.from_user.id):
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.send_message(call.message.chat.id, "✅ Thank you for joining! You can now use the bot. Type /start to begin.")

@bot.message_handler(commands=['start'])
def start_command(message):
    if not check_and_prompt_membership(message.chat.id, message.from_user.id): return
    user_id = message.from_user.id
    first_name = message.from_user.first_name

    # Check if referral link was used: /start <referrer_id>
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id and db.user_exists(referrer_id):
            referred_by = referrer_id

    # Add user
    if not db.user_exists(user_id):
        db.add_user(user_id, first_name, referred_by)
        bot.send_message(user_id, f"Welcome to the Bot, {first_name}!", reply_markup=get_main_menu())
        
        # Credit referrer
        if referred_by:
            reward = float(db.get_setting('referral_reward') or 1.0)
            db.add_balance(referred_by, reward)
            db.increment_referral_count(referred_by)
            try:
                bot.send_message(referred_by, f"🎉 You have a new referral! You earned ${reward}.")
            except Exception as e:
                print(f"Failed to send message to referrer {referred_by}: {e}")
    else:
        bot.send_message(user_id, f"Welcome back, {first_name}!", reply_markup=get_main_menu())

@bot.message_handler(func=lambda message: message.text == '👤 Profile')
def profile_handler(message):
    if not check_and_prompt_membership(message.chat.id, message.from_user.id): return
    user = db.get_user(message.from_user.id)
    if user:
        profile_text = (
            f"👤 **Your Profile**\n"
            f"ID: `{user['id']}`\n"
            f"Name: {user['first_name']}\n"
            f"Balance: ${user['balance']:.2f}\n"
            f"Total Referrals: {user['referral_count']}"
        )
        bot.send_message(message.chat.id, profile_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == '💰 Balance')
def balance_handler(message):
    if not check_and_prompt_membership(message.chat.id, message.from_user.id): return
    user = db.get_user(message.from_user.id)
    if user:
        bot.send_message(message.chat.id, f"💰 Your current balance is: **${user['balance']:.2f}**", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == '🔗 Referral')
def referral_handler(message):
    if not check_and_prompt_membership(message.chat.id, message.from_user.id): return
    user_id = message.from_user.id
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    reward = db.get_setting('referral_reward')
    
    text = (
        f"🔗 **Your Referral Link**\n\n"
        f"Share this link with your friends to earn ${reward} per referral:\n"
        f"`{ref_link}`"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == '🛒 Get ChatGPT Plus')
def get_chatgpt_plus_handler(message):
    if not check_and_prompt_membership(message.chat.id, message.from_user.id): return
    msg = bot.send_message(message.chat.id, "Please send the link to your gopay payment page:")
    bot.register_next_step_handler(msg, process_payment_link)

def process_payment_link(message):
    if not message.text:
        bot.send_message(message.chat.id, "❌ Invalid input. Please click '🛒 Get ChatGPT Plus' and send a valid text link.")
        return
        
    payment_link = message.text
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    chatgpt_price = float(db.get_setting('chatgpt_price') or 1.0)
    user = db.get_user(user_id)
    if not user or user['balance'] < chatgpt_price:
        bot.send_message(message.chat.id, f"❌ Insufficient balance! You need at least ${chatgpt_price:.2f} to request ChatGPT Plus.")
        return
        
    db.add_balance(user_id, -chatgpt_price)
    
    bot.send_message(message.chat.id, f"⏳ Your request is being processed. ${chatgpt_price:.2f} has been deducted from your balance. Please wait...")
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Confirm", callback_data=f"chatgpt_confirm_{user_id}"),
        InlineKeyboardButton("❌ Cancel Order", callback_data=f"chatgpt_cancel_{user_id}")
    )
    
    admin_text = (
        f"🚨 **New ChatGPT Plus Request**\n"
        f"From User: {user_name} (ID: `{user_id}`)\n"
        f"Payment Link: {payment_link}"
    )
    bot.send_message(ADMIN_ID, admin_text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('chatgpt_'))
def handle_chatgpt_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "You are not an admin!")
        return
        
    data_parts = call.data.split('_')
    action = data_parts[1]
    user_id = int(data_parts[2])
    
    if action == "confirm":
        bot.edit_message_text(f"{call.message.text}\n\n**Status:** ✅ Confirmed", chat_id=call.message.chat.id, message_id=call.message.message_id)
        try:
            bot.send_message(user_id, "🎉 Congratulations! Your ChatGPT Plus account has been successful.")
        except Exception as e:
            print(f"Failed to notify user: {e}")
            
    elif action == "cancel":
        chatgpt_price = float(db.get_setting('chatgpt_price') or 1.0)
        db.add_balance(user_id, chatgpt_price)
        bot.edit_message_text(f"{call.message.text}\n\n**Status:** ❌ Cancelled", chat_id=call.message.chat.id, message_id=call.message.message_id)
        try:
            bot.send_message(user_id, f"❌ Sorry, your ChatGPT Plus order has been cancelled. ${chatgpt_price:.2f} has been refunded to your balance.")
        except Exception as e:
            print(f"Failed to notify user: {e}")
            
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.text == '📥 Deposit')
def deposit_handler(message):
    if not check_and_prompt_membership(message.chat.id, message.from_user.id): return
    text = (
        "💳 **Deposit Funds**\n\n"
        "Please send your payment to the following Binance UID:\n"
        "`1141335463`\n\n"
        "After sending the payment, click Confirm."
    )
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Confirm Payment", callback_data="deposit_user_confirm"),
        InlineKeyboardButton("❌ Cancel Payment", callback_data="deposit_user_cancel")
    )
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == '📺 Tutorial')
def tutorial_handler(message):
    if not check_and_prompt_membership(message.chat.id, message.from_user.id): return
    link = db.get_setting('tutorial_link')
    if link:
        bot.send_message(message.chat.id, f"📺 **How to use this bot**\n\nWatch the tutorial here:\n{link}", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "📺 The tutorial video has not been added yet. Please check back later!")

@bot.callback_query_handler(func=lambda call: call.data.startswith('deposit_user_'))
def handle_deposit_user_callback(call):
    action = call.data.split('_')[2]
    
    if action == "cancel":
        bot.edit_message_text("❌ Deposit cancelled.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id)
    elif action == "confirm":
        bot.edit_message_text("✅ Please send a screenshot of your successful transaction:", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.register_next_step_handler(call.message, process_deposit_screenshot)
        bot.answer_callback_query(call.id)

def process_deposit_screenshot(message):
    if not message.photo:
        bot.send_message(message.chat.id, "❌ That doesn't look like a photo. Please click '📥 Deposit' to try again.")
        return
        
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    photo_file_id = message.photo[-1].file_id
    
    bot.send_message(message.chat.id, "⏳ Your screenshot has been sent to the admin for review. Please wait for confirmation.")
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Approve", callback_data=f"depadmin_approve_{user_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"depadmin_reject_{user_id}")
    )
    
    caption = f"🚨 **New Deposit Request**\nFrom User: {user_name} (ID: `{user_id}`)"
    bot.send_photo(ADMIN_ID, photo_file_id, caption=caption, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('depadmin_'))
def handle_deposit_admin_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "You are not an admin!")
        return
        
    data_parts = call.data.split('_')
    action = data_parts[1]
    user_id = int(data_parts[2])
    
    if action == "reject":
        bot.edit_message_caption(f"{call.message.caption}\n\n**Status:** ❌ Rejected", chat_id=call.message.chat.id, message_id=call.message.message_id)
        try:
            bot.send_message(user_id, "❌ Your deposit request was rejected. If you think this is a mistake, please contact support.")
        except Exception as e:
            print(f"Failed to notify user: {e}")
        bot.answer_callback_query(call.id)
        
    elif action == "approve":
        msg = bot.send_message(call.message.chat.id, f"How much $ should be added to user {user_id}? (e.g. 5.50)")
        bot.register_next_step_handler(msg, process_deposit_amount, user_id, call.message)
        bot.answer_callback_query(call.id)

def process_deposit_amount(message, user_id, original_message):
    try:
        amount = float(message.text)
        db.add_balance(user_id, amount)
        
        bot.edit_message_caption(f"{original_message.caption}\n\n**Status:** ✅ Approved (+${amount})", chat_id=original_message.chat.id, message_id=original_message.message_id)
        bot.send_message(message.chat.id, f"✅ Successfully added ${amount} to user {user_id}.")
        
        try:
            bot.send_message(user_id, f"🎉 Your deposit has been confirmed! ${amount} has been added to your balance.")
        except Exception as e:
            print(f"Failed to notify user: {e}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid amount. Deposit approval cancelled.")

# Admin commands
@bot.message_handler(commands=['admin'])
def admin_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    text = (
        "🛠 **Admin Panel**\n"
        "/stats - View bot statistics\n"
        "/setreward <amount> - Set dollars paid per referral\n"
        "/setchatgptprice <amount> - Set ChatGPT Plus price\n"
        "/settutorial <link> - Set tutorial video link\n"
        "/setrefcount <user_id> <count> - Set user's referral count\n"
        "/setbalance <user_id> <amount> - Set user's balance\n"
        "/addchannel @username - Add required channel\n"
        "/removechannel @username - Remove required channel\n"
        "/channels - List required channels"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['stats'])
def stats_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    total_users = db.get_total_users()
    total_balance = db.get_total_balance()
    reward = db.get_setting('referral_reward')
    
    text = (
        f"📊 **Bot Statistics**\n"
        f"Total Users: {total_users}\n"
        f"Total Balance Across Users: ${total_balance:.2f}\n"
        f"Current Referral Reward: ${reward}"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['setreward'])
def set_reward_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        args = message.text.split()
        if len(args) != 2:
            bot.send_message(message.chat.id, "Usage: /setreward <amount>")
            return
        
        amount = float(args[1])
        db.set_setting('referral_reward', str(amount))
        bot.send_message(message.chat.id, f"✅ Referral reward updated to ${amount}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid amount.")

@bot.message_handler(commands=['setchatgptprice'])
def set_chatgpt_price_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        args = message.text.split()
        if len(args) != 2:
            bot.send_message(message.chat.id, "Usage: /setchatgptprice <amount>")
            return
        
        amount = float(args[1])
        db.set_setting('chatgpt_price', str(amount))
        bot.send_message(message.chat.id, f"✅ ChatGPT Plus price updated to ${amount:.2f}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid amount.")

@bot.message_handler(commands=['settutorial'])
def set_tutorial_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        bot.send_message(message.chat.id, "Usage: /settutorial <video_link>")
        return
        
    link = args[1]
    db.set_setting('tutorial_link', link)
    bot.send_message(message.chat.id, f"✅ Tutorial link updated successfully to:\n{link}")

@bot.message_handler(commands=['setrefcount'])
def set_ref_count_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        args = message.text.split()
        if len(args) != 3:
            bot.send_message(message.chat.id, "Usage: /setrefcount <user_id> <count>")
            return
        
        user_id = int(args[1])
        count = int(args[2])
        if db.user_exists(user_id):
            with db.lock:
                cursor = db.conn.cursor()
                cursor.execute("UPDATE users SET referral_count = ? WHERE id = ?", (count, user_id))
                db.conn.commit()
            bot.send_message(message.chat.id, f"✅ Referral count for {user_id} updated to {count}")
        else:
            bot.send_message(message.chat.id, "❌ User not found.")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid arguments.")

@bot.message_handler(commands=['setbalance'])
def set_balance_command(message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        args = message.text.split()
        if len(args) != 3:
            bot.send_message(message.chat.id, "Usage: /setbalance <user_id> <amount>")
            return
        
        user_id = int(args[1])
        amount = float(args[2])
        if db.user_exists(user_id):
            with db.lock:
                cursor = db.conn.cursor()
                cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (amount, user_id))
                db.conn.commit()
            bot.send_message(message.chat.id, f"✅ Balance for {user_id} updated to ${amount}")
        else:
            bot.send_message(message.chat.id, "❌ User not found.")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid arguments.")

@bot.message_handler(commands=['addchannel'])
def add_channel_command(message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 2 or not args[1].startswith('@'):
        bot.send_message(message.chat.id, "Usage: /addchannel @username")
        return
    channel = args[1]
    if db.add_channel(channel):
        bot.send_message(message.chat.id, f"✅ Channel {channel} added to required list.")
    else:
        bot.send_message(message.chat.id, f"❌ Channel {channel} is already in the list.")

@bot.message_handler(commands=['removechannel'])
def remove_channel_command(message):
    if message.from_user.id != ADMIN_ID: return
    args = message.text.split()
    if len(args) != 2 or not args[1].startswith('@'):
        bot.send_message(message.chat.id, "Usage: /removechannel @username")
        return
    channel = args[1]
    if db.remove_channel(channel):
        bot.send_message(message.chat.id, f"✅ Channel {channel} removed.")
    else:
        bot.send_message(message.chat.id, f"❌ Channel {channel} not found.")

@bot.message_handler(commands=['channels'])
def list_channels_command(message):
    if message.from_user.id != ADMIN_ID: return
    channels = db.get_all_channels()
    if channels:
        bot.send_message(message.chat.id, "📋 **Required Channels:**\n" + "\n".join(channels), parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "No required channels currently set.")

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    print("Starting Web Server...")
    # Run Flask in a separate thread so it doesn't block the bot polling
    threading.Thread(target=run_web, daemon=True).start()
    
    print("Bot is running...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Bot polling error: {e}")
            time.sleep(5)
