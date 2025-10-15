import os
import json
from datetime import datetime, timedelta, time as dt_time
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler,
    MessageHandler, filters, ConversationHandler
)

DATA_FILE = "data.json"
SETTINGS_FILE = "settings.json"

# --- состояния для ConversationHandler ---
SET_TIME, SET_DAY = range(2)

# --- загрузка и сохранение данных ---
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_settings():
    default = {"hour": 7, "minute": 30, "report_day": 0}  # понедельник по умолчанию
    if not os.path.exists(SETTINGS_FILE):
        return default
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

# --- главное меню ---
def main_menu():
    keyboard = [
        [KeyboardButton("📊 Статистика"), KeyboardButton("💊 Выпила!")],
        [KeyboardButton("⚙ Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- настройки ---
def settings_menu():
    keyboard = [
        [KeyboardButton("⏰ Поменять время"), KeyboardButton("📅 Поменять день отчёта")],
        [KeyboardButton("🗑 Обнулить все")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я буду напоминать тебе пить таблетки 💊",
        reply_markup=main_menu()
    )

# --- статистика ---
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = str(update.effective_user.id)
    today = datetime.now().date()
    week_count = 0
    month_count = 0
    if user in data:
        for date_str in data[user]:
            dt = datetime.strptime(date_str, "%Y-%m-%d").date()
            if (today - dt).days < 7:
                week_count += 1
            if dt.month == today.month:
                month_count += 1
    await update.message.reply_text(f"📅 За последнюю неделю: {week_count}\n🗓 За текущий месяц: {month_count}")

# --- фиксируем 'выпила' ---
async def mark_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = str(update.effective_user.id)
    today_str = datetime.now().strftime("%Y-%m-%d")
    if user not in data:
        data[user] = []
    if today_str in data[user]:
        await update.message.reply_text("✅ Уже зафиксировано!")
    else:
        data[user].append(today_str)
        save_data(data)
        await update.message.reply_text("✅ Зафиксировано!")
        
# --- настройки времени ---
async def change_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите новое время напоминания (ЧЧ:ММ):", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))
    return SET_TIME

async def save_new_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_time = datetime.strptime(update.message.text, "%H:%M").time()
        settings = load_settings()
        settings["hour"] = new_time.hour
        settings["minute"] = new_time.minute
        save_settings(settings)
        await update.message.reply_text(f"✅ Время напоминания изменено на {new_time.strftime('%H:%M')}", reply_markup=main_menu())

        # --- обновляем задачу на сегодня ---
        job_queue = context.job_queue
        chat_id = update.effective_chat.id
        # удаляем старую задачу
        for job in job_queue.get_jobs_by_name(f"reminder_{chat_id}"):
            job.schedule_removal()

        # добавляем новую ежедневную задачу
        job_queue.run_daily(
            daily_reminder,
            time=new_time,
            name=f"reminder_{chat_id}",
            chat_id=chat_id
        )

    except ValueError:
        await update.message.reply_text("⚠ Неверный формат. Введи время в формате ЧЧ:ММ.", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))
        return SET_TIME
    return ConversationHandler.END

# --- настройки дня отчёта ---
async def change_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите новый день недели для отчета (0-Пн ... 6-Вс):", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))
    return SET_DAY

async def save_new_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        day = int(update.message.text)
        if day not in range(7):
            raise ValueError
        settings = load_settings()
        settings["report_day"] = day
        save_settings(settings)
        await update.message.reply_text(f"✅ День отчета изменен на {day}", reply_markup=main_menu())
    except ValueError:
        await update.message.reply_text("⚠ Введи число от 0 (Пн) до 6 (Вс).", reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True))
        return SET_DAY
    return ConversationHandler.END

# --- обнуление всех записей ---
async def reset_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user = str(update.effective_user.id)
    if user in data:
        data[user] = []
        save_data(data)
    await update.message.reply_text("♻ Все записи обнулены!", reply_markup=main_menu())

# --- кнопка назад ---
async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return ConversationHandler.END

# --- ежедневное уведомление ---
async def daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = getattr(job, 'chat_id', None)
    if chat_id is None:
        return
    await context.bot.send_message(chat_id, "💊 Выпей таблетку!", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("💊 Выпила!")]], resize_keyboard=True))

# --- тестовое уведомление ---
async def test_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.job_queue.run_once(daily_reminder, datetime.now() + timedelta(seconds=3), chat_id=update.effective_chat.id)
    await update.message.reply_text("⏱ Тестовое уведомление через 3 секунды.")

# --- основная функция ---
def main():
    TOKEN = os.environ.get("TOKEN")
    if not TOKEN:
        print("⚠ Поставь токен в переменной окружения TOKEN")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("⏰ Поменять время"), change_time),
            MessageHandler(filters.Regex("📅 Поменять день отчёта"), change_day),
            MessageHandler(filters.Regex("🗑 Обнулить все"), reset_all)
        ],
        states={
            SET_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_time)],
            SET_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_day)],
        },
        fallbacks=[MessageHandler(filters.Regex("🔙 Назад"), go_back)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("💊 Выпила!"), mark_done))
    app.add_handler(MessageHandler(filters.Regex("📊 Статистика"), show_stats))
    app.add_handler(MessageHandler(filters.Regex("⚙ Настройки"), lambda u, c: u.message.reply_text("⚙ Настройки:", reply_markup=settings_menu())))
    app.add_handler(MessageHandler(filters.Regex("⏱ Тестовое уведомление"), test_reminder))
    app.add_handler(conv_handler)

    # --- получаем ID пользователя для запуска уведомлений ---
    # Здесь просто запускаем ежедневное напоминаение на 7:30 пользователю,
    # который написал /start (инициализация)
    # Для удобства, можно задать chat_id вручную или получить с первого взаимодействия

    # Для первого запуска можно использовать заглушку,
    # и поменять после получения chat_id пользователя. Пока оставим None и запустим с задержкой.

    # Запускаем polling асинхронно и потом добавим работу с задачами
    async def on_startup(app):
        settings = load_settings()
        hour, minute = settings["hour"], settings["minute"]

        # Для одного пользователя:
        # Нужно проверить, что у вас где-то сохранён chat_id.
        # Предположим, что chat_id хранится в файле settings.json как "chat_id"
        chat_id = settings.get("chat_id")
        if chat_id is None:
            print("⚠ Не найден chat_id в настройках, уведомления не запущены")
            return

        # Очистим старые задачи на этого пользователя
        for job in app.job_queue.get_jobs_by_name(f"reminder_{chat_id}"):
            job.schedule_removal()

        app.job_queue.run_daily(
            daily_reminder,
            time=dt_time(hour=hour, minute=minute),
            name=f"reminder_{chat_id}",
            chat_id=chat_id
        )

    app.post_init = on_startup

    # --- дополнительно, обработчик /start для сохранения chat_id ---
    async def start_and_save_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        settings = load_settings()
        if settings.get("chat_id") != chat_id:
            settings["chat_id"] = chat_id
            save_settings(settings)
            # После сохранения chat_id, создаём задачу если нужно
            hour, minute = settings["hour"], settings["minute"]
            for job in context.job_queue.get_jobs_by_name(f"reminder_{chat_id}"):
                job.schedule_removal()
            context.job_queue.run_daily(
                daily_reminder,
                time=dt_time(hour=hour, minute=minute),
                name=f"reminder_{chat_id}",
                chat_id=chat_id
            )
        await start(update, context)

    # Перерегистрируем handler start, чтобы сохранять chat_id
    app.handlers.clear()
    app.add_handler(CommandHandler("start", start_and_save_chat_id))
    app.add_handler(MessageHandler(filters.Regex("💊 Выпила!"), mark_done))
    app.add_handler(MessageHandler(filters.Regex("📊 Статистика"), show_stats))
    app.add_handler(MessageHandler(filters.Regex("⚙ Настройки"), lambda u, c: u.message.reply_text("⚙ Настройки:", reply_markup=settings_menu())))
    app.add_handler(MessageHandler(filters.Regex("⏱ Тестовое уведомление"), test_reminder))
    app.add_handler(conv_handler)

    app.run_polling()

if __name__ == "__main__":
    main()
