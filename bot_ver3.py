import json
import os
from datetime import datetime, timedelta, time as dt_time
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)

# --- Путь к файлам ---
DATA_FILE = "data.json"
SETTINGS_FILE = "settings.json"

# --- Константы состояний ---
SET_TIME, SET_DAY = range(2)

# --- Функции работы с файлами ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {"hour": 7, "minute": 30, "report_day": 0}
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)

# --- Команды и обработчики ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("💊 Выпила!"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("⚙ Настройки"), KeyboardButton("🧪 Тест уведомления")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Привет! Я твой трекер таблеток 💊", reply_markup=reply_markup)

async def record_pill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    data.setdefault(user, []).append(today)
    save_data(data)
    await update.message.reply_text("✅ Зафиксировано!")

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = str(update.effective_user.id)
    data = load_data().get(user, [])
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    week_count = sum(1 for d in data if datetime.strptime(d, "%Y-%m-%d") >= week_ago)
    month_count = sum(1 for d in data if datetime.strptime(d, "%Y-%m-%d") >= month_ago)
    await update.message.reply_text(
        f"📊 За последнюю неделю: {week_count}\n📅 За месяц: {month_count}"
    )

# --- Настройки ---
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("⏰ Поменять время"), KeyboardButton("📅 Поменять день отчёта")],
        [KeyboardButton("🔙 Назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Выбери настройку:", reply_markup=reply_markup)

async def change_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введи новое время уведомления в формате ЧЧ:ММ (например, 08:15)")
    return SET_TIME

async def save_new_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_time = datetime.strptime(update.message.text, "%H:%M").time()
        settings = load_settings()
        settings["hour"] = new_time.hour
        settings["minute"] = new_time.minute
        save_settings(settings)
        await update.message.reply_text(f"✅ Время напоминания изменено на {new_time.strftime('%H:%M')}")
    except ValueError:
        await update.message.reply_text("⚠ Неверный формат. Введи время в формате ЧЧ:ММ.")
    return ConversationHandler.END

async def change_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введи день недели для отчёта (0 - понедельник, 6 - воскресенье):")
    return SET_DAY

async def save_new_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        day = int(update.message.text)
        if day not in range(7):
            raise ValueError
        settings = load_settings()
        settings["report_day"] = day
        save_settings(settings)
        await update.message.reply_text(f"✅ День отчёта изменён на {day}")
    except ValueError:
        await update.message.reply_text("⚠ Введи число от 0 до 6.")
    return ConversationHandler.END

async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return ConversationHandler.END

# --- Напоминания ---
async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    for user in load_data().keys():
        await context.bot.send_message(
            chat_id=user,
            text="💊 Напоминание: пора выпить таблетку!",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("💊 Выпила!")]], resize_keyboard=True)
        )

async def weekly_report(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    for user, dates in data.items():
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        week_count = sum(1 for d in dates if datetime.strptime(d, "%Y-%m-%d") >= week_ago)
        month_ago = now - timedelta(days=30)
        month_count = sum(1 for d in dates if datetime.strptime(d, "%Y-%m-%d") >= month_ago)
        await context.bot.send_message(
            chat_id=user,
            text=f"📊 Отчёт за неделю: {week_count}\n📅 За месяц: {month_count}"
        )

async def test_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Через 3 секунды придёт тестовое уведомление.")
    await context.job_queue.run_once(send_test_message, when=3, chat_id=update.effective_chat.id)

async def send_test_message(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=context.job.chat_id, text="💊 Тестовое уведомление!")

# --- Основная функция ---
def main():
    TOKEN = os.environ["TOKEN"]
    app = ApplicationBuilder().token(TOKEN).build()

    # Основные хендлеры
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("💊 Выпила!"), record_pill))
    app.add_handler(MessageHandler(filters.Regex("📊 Статистика"), show_stats))
    app.add_handler(MessageHandler(filters.Regex("⚙ Настройки"), settings_menu))
    app.add_handler(MessageHandler(filters.Regex("🧪 Тест уведомления"), test_notification))

    # Настройки
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("⏰ Поменять время"), change_time),
            MessageHandler(filters.Regex("📅 Поменять день отчёта"), change_day)
        ],
        states={
            SET_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_time)],
            SET_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_day)],
        },
        fallbacks=[MessageHandler(filters.Regex("🔙 Назад"), go_back)],
    )
    app.add_handler(conv_handler)

    # Планировщик задач
    job_queue = app.job_queue
    settings = load_settings()
    reminder_time = dt_time(hour=settings["hour"], minute=settings["minute"])
    report_day = settings["report_day"]

    job_queue.run_daily(daily_reminder, reminder_time)
    job_queue.run_daily(weekly_report, reminder_time, days=(report_day,))

    app.run_polling()

if __name__ == "__main__":
    main()
