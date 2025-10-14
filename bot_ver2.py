import json
import os
from datetime import datetime, timedelta, time
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

DATA_FILE = "data.json"

# --- Работа с данными ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
        return json.loads(content) if content else {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def record_today():
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    if today in data:
        return False
    data[today] = True
    save_data(data)
    return True

def get_stats():
    data = load_data()
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    month_start = today.replace(day=1)
    week_count = sum(1 for d in data if week_ago.strftime("%Y-%m-%d") <= d <= today.strftime("%Y-%m-%d"))
    month_count = sum(1 for d in data if month_start.strftime("%Y-%m-%d") <= d <= today.strftime("%Y-%m-%d"))
    return week_count, month_count

# --- Бот ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Статистика"), KeyboardButton("Выпила!")],
        [KeyboardButton("Настройки")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Привет! Я помогу тебе не забывать таблетки.", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "Статистика":
        week, month = get_stats()
        await update.message.reply_text(f"Таблетки за неделю: {week}\nТаблетки за месяц: {month}")
    elif text == "Выпила!":
        if record_today():
            await update.message.reply_text("Зафиксировано!")
        else:
            await update.message.reply_text("Уже зафиксировано сегодня!")
    elif text == "Настройки":
        keyboard = [
            [KeyboardButton("Поменять время"), KeyboardButton("Поменять день")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выбери настройку:", reply_markup=reply_markup)
    elif text == "Поменять время":
        await update.message.reply_text("Отправь новое время в формате ЧЧ:ММ (например, 09:30)")
        context.user_data["awaiting_time"] = True
    elif text == "Поменять день":
        days = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
        keyboard = [[KeyboardButton(day) for day in days[:4]],
                    [KeyboardButton(day) for day in days[4:]]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Выбери день недели для отчёта:", reply_markup=reply_markup)
        context.user_data["awaiting_day"] = True
    elif context.user_data.get("awaiting_time"):
        try:
            new_time = datetime.strptime(text, "%H:%M").time()
            context.user_data["reminder_time"] = new_time
            context.user_data["awaiting_time"] = False
            await update.message.reply_text(f"Время уведомлений изменено на {new_time.strftime('%H:%M')}")
        except:
            await update.message.reply_text("Неверный формат! Отправь в формате ЧЧ:ММ")
    elif context.user_data.get("awaiting_day"):
        days_dict = {"Понедельник":0,"Вторник":1,"Среда":2,"Четверг":3,"Пятница":4,"Суббота":5,"Воскресенье":6}
        if text in days_dict:
            context.user_data["report_day"] = days_dict[text]
            context.user_data["awaiting_day"] = False
            await update.message.reply_text(f"День отчёта изменён на {text}")
        else:
            await update.message.reply_text("Выбери день из списка")

# --- Настройки уведомлений ---
async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = list(context.bot_data.keys())[0] if context.bot_data else None
    if chat_id:
        await context.bot.send_message(chat_id, "💊 Не забудь выпить таблетку!")

async def weekly_report(context: ContextTypes.DEFAULT_TYPE):
    chat_id = list(context.bot_data.keys())[0] if context.bot_data else None
    if chat_id:
        week, month = get_stats()
        await context.bot.send_message(chat_id, f"Отчёт за неделю:\nТаблетки за неделю: {week}\nТаблетки за месяц: {month}")

# --- Запуск ---
def main():
    TOKEN = os.environ["TOKEN"]
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # --- JobQueue ---
    if not hasattr(app, "job_queue") or app.job_queue is None:
        import warnings
        warnings.warn("JobQueue не настроен! Для работы уведомлений установи python-telegram-bot[job-queue]")
    else:
        # Ежедневное напоминание в 9:00
        app.job_queue.run_daily(daily_reminder, time(hour=9, minute=0))
        # Еженедельный отчёт по понедельникам
        app.job_queue.run_daily(weekly_report, time(hour=9, minute=0), days=(0,))

    app.run_polling()

if __name__ == "__main__":
    main()
