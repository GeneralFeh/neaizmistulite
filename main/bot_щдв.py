from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from datetime import datetime, timedelta, time as dt_time
import json
import os

TOKEN = os.environ["TOKEN"]
DATA_FILE = "data.json"
DEFAULT_REMINDER_TIME = dt_time(hour=9, minute=0)  # стандартное время

# ------------------ Работа с данными ------------------

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

def record_today(chat_id):
    chat_id = str(chat_id)
    today = datetime.now().strftime("%Y-%m-%d")
    data = load_data()
    if chat_id not in data:
        data[chat_id] = []
    if today not in data[chat_id]:
        data[chat_id].append(today)
        save_data(data)
        return True
    return False

# ------------------ Обработчики ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    keyboard = [
        [KeyboardButton("📋 Команды"), KeyboardButton("📈 Статистика за неделю")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! 💊 Я буду напоминать тебе каждый день и вести статистику.\n"
        "Выберите команду:",
        reply_markup=reply_markup
    )

    # ежедневное напоминание
    if context.job_queue:
        if not context.job_queue.get_jobs_by_name(f"reminder_{chat_id}"):
            context.job_queue.run_daily(
                send_reminder, DEFAULT_REMINDER_TIME, chat_id=chat_id, name=f"reminder_{chat_id}"
            )

        # понедельничный отчёт
        if not context.job_queue.get_jobs_by_name(f"report_{chat_id}"):
            context.job_queue.run_daily(
                weekly_report, dt_time(hour=9, minute=0), days=(0,), chat_id=chat_id, name=f"report_{chat_id}"
            )

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    keyboard = [[InlineKeyboardButton("✅ Выпила", callback_data="done")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text="💊 Выпей таблетку", reply_markup=reply_markup)

async def push(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("✅ Выпила", callback_data="done")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("💊 Выпей таблетку", reply_markup=reply_markup)

async def mark_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if record_today(chat_id):
        await update.message.reply_text("✅ Зафиксирован!")
    else:
        await update.message.reply_text("💊 Уже отмечено сегодня.")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "done":
        if record_today(query.message.chat_id):
            await query.edit_message_text(text="✅ Зафиксирован!")
        else:
            await query.edit_message_text(text="💊 Уже отмечено сегодня.")

# ------------------ Авто-отчёт ------------------

async def weekly_report(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    data = load_data()
    dates = data.get(str(chat_id), [])

    today = datetime.now()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    week_count = sum(1 for d in dates if datetime.strptime(d, "%Y-%m-%d") >= week_ago)
    month_count = sum(1 for d in dates if datetime.strptime(d, "%Y-%m-%d") >= month_ago)

    msg = f"📊 Отчёт:\nДней пропито за неделю: {week_count}\nДней пропито за месяц: {month_count}"
    await context.bot.send_message(chat_id=chat_id, text=msg)

# ------------------ Смена времени напоминания ------------------

async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if len(context.args) != 1 or ":" not in context.args[0]:
        await update.message.reply_text("❌ Формат неправильный. Используй /settime ЧЧ:ММ")
        return

    try:
        hours, minutes = map(int, context.args[0].split(":"))
        new_time = dt_time(hour=hours, minute=minutes)
    except:
        await update.message.reply_text("❌ Неправильное время. Используй /settime ЧЧ:ММ")
        return

    # удаляем старые задачи напоминаний
    if context.job_queue:
        for job in context.job_queue.get_jobs_by_name(f"reminder_{chat_id}"):
            job.schedule_removal()

        # добавляем новое время
        context.job_queue.run_daily(send_reminder, new_time, chat_id=chat_id, name=f"reminder_{chat_id}")

    await update.message.reply_text(f"⏰ Время ежедневного напоминания изменено на {context.args[0]} ✅")

# ------------------ Статистика за неделю ------------------

async def weekly_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = load_data()
    dates = data.get(str(chat_id), [])

    today = datetime.now()
    week_ago = today - timedelta(days=7)
    week_count = sum(1 for d in dates if datetime.strptime(d, "%Y-%m-%d") >= week_ago)

    await update.message.reply_text(f"📊 За последнюю неделю вы приняли {week_count} таблеток 💊")

# ------------------ Справка ------------------

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands = (
        "/start — Приветствие и включение напоминаний\n"
        "/push — Напомнить прямо сейчас\n"
        "/done — Отметить таблетку вручную\n"
        "/settime ЧЧ:ММ — Сменить время ежедневного напоминания\n"
        "/help — Список команд"
    )
    await update.message.reply_text(f"📋 Список команд:\n{commands}")

async def show_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await help_command(update, context)

# ------------------ Основная функция ------------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("push", push))
    app.add_handler(CommandHandler("done", mark_done))
    app.add_handler(CommandHandler("settime", settime))
    app.add_handler(CommandHandler("help", help_command))

    # кнопки callback
    app.add_handler(CallbackQueryHandler(button))

    # кнопки меню
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("📋 Команды"), show_commands))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("📈 Статистика за неделю"), weekly_stats))

    # запуск бота
    app.run_polling()

if __name__ == "__main__":
    main()
