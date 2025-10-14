import os
import json
from datetime import datetime, timedelta, time
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, JobQueue

DATA_FILE = "data.json"
TOKEN = os.environ["TOKEN"]  # В Render: Environment Variables -> TOKEN

# --- Работа с данными ---
def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

def record_today(chat_id):
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    data.setdefault(str(chat_id), []).append(today)
    save_data(data)

def count_last_week(chat_id):
    data = load_data()
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    dates = data.get(str(chat_id), [])
    return sum(1 for d in dates if week_ago.strftime("%Y-%m-%d") <= d <= today.strftime("%Y-%m-%d"))

def count_total(chat_id):
    data = load_data()
    return len(data.get(str(chat_id), []))

# --- Обработчики ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    keyboard = [
        [KeyboardButton("💊 Выпила")],
        [KeyboardButton("📋 Команды")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Я буду напоминать тебе про таблетки.", 
        reply_markup=reply_markup
    )

async def mark_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    record_today(chat_id)
    await update.message.reply_text("Зафиксировано! ✅")

async def show_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    last_week = count_last_week(chat_id)
    total = count_total(chat_id)
    text = (
        "Доступные команды:\n"
        "💊 Выпила — отметить таблетку\n"
        "📋 Команды — показать это меню\n\n"
        f"Таблеток выпито за последнюю неделю: {last_week}\n"
        f"Всего таблеток: {total}"
    )
    await update.message.reply_text(text)

# --- Напоминания ---
async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in context.job.chat_ids:
        keyboard = [[KeyboardButton("💊 Выпила")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await context.bot.send_message(chat_id, "Не забудь выпить таблетку! 💊", reply_markup=reply_markup)

async def weekly_report(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in context.job.chat_ids:
        last_week = count_last_week(chat_id)
        await context.bot.send_message(chat_id, f"Отчёт за неделю:\nТаблеток выпито: {last_week}")

# --- Основная функция ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", start))
    # Кнопки
    app.add_handler(MessageHandler(filters.Regex("💊 Выпила"), mark_done))
    app.add_handler(MessageHandler(filters.Regex("📋 Команды"), show_commands))

    # --- Планировщик ---
    job_queue = app.job_queue

    # Ежедневное напоминание в 9:00
    job_queue.run_daily(daily_reminder, time(hour=9, minute=0))

    # Еженедельный отчёт в понедельник в 9:00
    job_queue.run_daily(weekly_report, time(hour=9, minute=0), days=(0,))  # 0 = Monday

    app.run_polling()

if __name__ == "__main__":
    main()
