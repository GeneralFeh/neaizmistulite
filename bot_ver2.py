import json
import os
from datetime import datetime, timedelta, time
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

DATA_FILE = "data.json"
SETTINGS_FILE = "settings.json"

# ---------------- Работа с данными ----------------
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

# ---------------- Настройки ----------------
def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {"report_day": 0}  # Понедельник по умолчанию
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
        return json.loads(content) if content else {"report_day": 0}

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

# ---------------- Клавиатуры ----------------
def main_keyboard():
    keyboard = [
        [KeyboardButton("Статистика"), KeyboardButton("Выпила!")],
        [KeyboardButton("Настройки"), KeyboardButton("Тест уведомления")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def settings_keyboard():
    keyboard = [
        [KeyboardButton("Поменять день")],
        [KeyboardButton("Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def back_to_main_keyboard():
    keyboard = [[KeyboardButton("Назад")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ---------------- Хэндлеры ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я помогу тебе не забывать таблетки.", reply_markup=main_keyboard())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    settings = context.bot_data.get("settings", load_settings())

    if text == "Статистика":
        week, month = get_stats()
        await update.message.reply_text(f"Таблетки за неделю: {week}\nТаблетки за месяц: {month}")

    elif text == "Выпила!":
        if record_today():
            await update.message.reply_text("Зафиксировано!")
        else:
            await update.message.reply_text("Уже зафиксировано сегодня!")

    elif text == "Настройки":
        await update.message.reply_text("Выбери настройку:", reply_markup=settings_keyboard())

    elif text == "Поменять день":
        days = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]
        keyboard = [[KeyboardButton(day) for day in days[:4]],
                    [KeyboardButton(day) for day in days[4:]],
                    [KeyboardButton("Назад")]]
        await update.message.reply_text("Выбери день недели для отчёта:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        context.user_data["awaiting_day"] = True

    elif text == "Назад":
        await update.message.reply_text("Возврат в главное меню", reply_markup=main_keyboard())
        context.user_data["awaiting_day"] = False

    elif context.user_data.get("awaiting_day"):
        days_dict = {"Понедельник":0,"Вторник":1,"Среда":2,"Четверг":3,"Пятница":4,"Суббота":5,"Воскресенье":6}
        if text in days_dict:
            settings["report_day"] = days_dict[text]
            save_settings(settings)
            context.bot_data["settings"] = settings
            context.user_data["awaiting_day"] = False
            await update.message.reply_text(f"День отчёта изменён на {text}", reply_markup=main_keyboard())
        else:
            await update.message.reply_text("Выбери день из списка")

    elif text == "Тест уведомления":
        chat_id = update.message.chat_id
        context.job_queue.run_once(send_today_reminder, when=3, data={"chat_id": chat_id})
        await update.message.reply_text("Тестовое уведомление будет отправлено через 3 секунды.")

# ---------------- Inline кнопка "Выпила!" ----------------
async def send_today_reminder(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    keyboard = [[InlineKeyboardButton("Выпила!", callback_data="done")]]
    markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id, "💊 Напоминание: выпей таблетку сегодня!", reply_markup=markup)

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "done":
        if record_today():
            await query.edit_message_text("Зафиксировано!")
        else:
            await query.edit_message_text("Уже зафиксировано сегодня!")

# ---------------- Еженедельный отчёт ----------------
async def weekly_report(context: ContextTypes.DEFAULT_TYPE):
    chat_id = list(context.bot_data.keys())[0] if context.bot_data else None
    if chat_id:
        week, month = get_stats()
        await context.bot.send_message(chat_id, f"Отчёт за неделю:\nТаблетки за неделю: {week}\nТаблетки за месяц: {month}")

# ---------------- Запуск ----------------
def main():
    import os
    TOKEN = os.environ["TOKEN"]
    app = ApplicationBuilder().token(TOKEN).build()

    settings = load_settings()
    app.bot_data["settings"] = settings

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # --- JobQueue: стандартное ежедневное уведомление в 7:30 ---
    app.job_queue.run_daily(send_today_reminder, time(7,30), name="daily_reminder")
    # --- Еженедельный отчёт ---
    app.job_queue.run_daily(weekly_report, time(7,30), days=(settings["report_day"],), name="weekly_report")

    app.run_polling()

if __name__ == "__main__":
    main()
