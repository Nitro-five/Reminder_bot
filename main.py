import logging
import pytz
from datetime import datetime, timedelta
from pytz import all_timezones
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

# Настройки
TOKEN = ''
GROUP_CHAT_ID = -100
BERLIN_TZ = pytz.timezone('Europe/Berlin')

# Глобальные переменные для хранения настроек
reminder_time = datetime.now(BERLIN_TZ).time()  # Время напоминаний (по умолчанию текущее)
current_timezone = BERLIN_TZ  # Текущая таймзона (по умолчанию Европа/Берлин)

# Глобальный список участников
group_participants = []

# Количество сообщений отправленные пользователем
user_message_count = {}

# Глобальный объект бота
bot = None

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Функция для проверки неактивных пользователей
async def check_inactive_users(context: CallbackContext):
    global bot  # Ссылаемся на глобальный объект бота
    logger.info("Проверка неактивных пользователей.")

    # Используем время, заданное пользователем, для напоминания
    reminder_datetime = datetime.combine(datetime.today(), reminder_time).replace(tzinfo=current_timezone)

    # Проверка неактивных пользователей
    inactive_users = []
    for participant in group_participants:
        last_message_time = participant.get("last_message_time")
        if last_message_time is None or reminder_datetime - last_message_time > timedelta(hours=1):  # Пример 1 час
            inactive_users.append(participant["nickname"])

    # Если есть неактивные пользователи, отправляем сообщение в группу
    if inactive_users:
        logger.info(f"Неактивные пользователи: {', '.join(inactive_users)}")

        # Отправляем сообщение в группу
        group_message = "Неактивные пользователи: " + ", ".join(inactive_users)
        try:
            await bot.send_message(chat_id=GROUP_CHAT_ID, text=group_message)
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения в группу: {e}")
    else:
        logger.info("Все пользователи активны.")


# Команда /start
async def start(update: Update, context: CallbackContext):
    logger.info("Запуск команды /start")
    comands = (
        "Привет! Я бот-напоминалка. Вот что я умею:\n\n"
        "/add_participant @username - Добавить участника в список отслеживания\n"
        "/remove_participant @username - Удалить участника из списка\n"
        "/list_participants - Показать список участников\n"
        "/manual_check - Проверить активность участников вручную\n"
        "/set_time - Установка времени и таймзоны\n"
        "/stats - Показать статистику сообщений участников за сегодня"
    )
    await update.message.reply_text(comands)


async def set_time(update: Update, context: CallbackContext):
    global reminder_time, current_timezone

    if len(context.args) != 3:
        await update.message.reply_text("Использование: /set_time <часы> <минуты> <таймзона>\n"
                                        "Пример: /set_time 11 30 Europe/Odessa")
        return

    try:
        hours = int(context.args[0])
        minutes = int(context.args[1])
        tz_name = context.args[2]

        # Проверяем, существует ли указанная таймзона
        if tz_name not in all_timezones:
            await update.message.reply_text("Ошибка: Некорректная таймзона.\n"
                                            "Пример правильной таймзоны: Europe/Kyiv, UTC, Asia/Tokyo")
            return

        # Обновляем настройки
        reminder_time = datetime.strptime(f"{hours}:{minutes}", "%H:%M").time()
        current_timezone = pytz.timezone(tz_name)

        await update.message.reply_text(f"Время напоминаний установлено на {hours}:{minutes}, Таймзона: {tz_name}")

        # Перезапускаем планировщик с новым временем
        setup_daily_check()

    except ValueError:
        await update.message.reply_text("Ошибка: Часы и минуты должны быть числами!")


# Обертка для асинхронной задачи
def async_job_wrapper(coro, context=None):
    def wrapper():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            new_loop.run_until_complete(coro(context))  # Передаем context в корутину
        finally:
            new_loop.close()  # Закрываем loop после выполнения

    return wrapper


# Настройка планировщика для ежедневной задачи
def setup_daily_check():
    global reminder_time, current_timezone
    scheduler = BackgroundScheduler()

    # Проверка неактивных пользователей в заданное пользователем время
    scheduler.add_job(
        async_job_wrapper(check_inactive_users, context=None),  # Правильный контекст здесь
        CronTrigger(hour=reminder_time.hour, minute=reminder_time.minute, second=0, timezone=current_timezone)
    )

    # Сброс статистики сообщений в 00:00
    scheduler.add_job(
        async_job_wrapper(reset_message_count, context=None),  # Для сброса статистики тоже передаем контекст
        CronTrigger(hour=0, minute=0, second=0, timezone=current_timezone)
    )

    scheduler.start()


# Команда для добавления участника по никнейму
async def add_participant(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /add_participant <никнейм>")
        return

    nickname = context.args[0]

    # Проверяем, что никнейм начинается с '@'
    if not nickname.startswith("@"):
        await update.message.reply_text("Никнейм должен начинаться с '@'.")
        return

    # Проверяем, не добавлен ли уже этот участник
    if nickname in [participant["nickname"] for participant in group_participants]:
        await update.message.reply_text(f"Участник с никнеймом {nickname} уже добавлен!")
        return

    # Добавляем участника в список с None в качестве last_message_time
    participant = {"nickname": nickname, "last_message_time": None}
    group_participants.append(participant)

    await update.message.reply_text(f"Участник {nickname} успешно добавлен!")
    print(f"Участник добавлен: {participant}")


# Команда для вывода списка участников
async def list_participants(update: Update, context: CallbackContext):
    if not group_participants:
        await update.message.reply_text("Список участников пуст.")
    else:
        participants_list = "\n".join(
            [participant["nickname"] for participant in group_participants]
        )
        await update.message.reply_text(f"Список участников:\n{participants_list}")


# Команда для удаления участника
async def remove_participant(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /remove_participant <никнейм>")
        return

    nickname = context.args[0]
    global group_participants
    group_participants = [p for p in group_participants if p["nickname"] != nickname]
    await update.message.reply_text(f"Участник {nickname} удален из отслеживания!")


# Команда для ручной проверки
async def manual_check(update: Update, context: CallbackContext):
    # Проверяем активность участников
    inactive_users = []
    current_time = datetime.now(BERLIN_TZ)  # Текущее время по Берлину

    # Ищем неактивных пользователей (не писавших в группе)
    for participant in group_participants:
        # Игнорируем пользователей, которые не отправляли сообщения еще
        if participant["last_message_time"] is None or current_time - participant["last_message_time"] > timedelta(
                minutes=10):
            inactive_users.append(participant["nickname"])

    # Сообщаем пользователю, вызвавшему команду
    if inactive_users:
        await update.message.reply_text(f"Неактивные пользователи: {', '.join(inactive_users)}")

        # Отправляем сообщение в группу
        group_message = "Неактивные пользователи: " + ", ".join(inactive_users)
        await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=group_message)
    else:
        await update.message.reply_text("Все пользователи активны!")


# Функция для отслеживания сообщений пользователей
async def track_message(update: Update, context: CallbackContext):
    username = update.effective_user.username
    if username:
        user_message_count[username] = user_message_count.get(username, 0) + 1


# Команда для отображения статистики сообщений
async def stats(update: Update, context: CallbackContext):
    if not user_message_count:
        await update.message.reply_text("Сегодня ещё никто не писал сообщений.")
        return

    stats_text = "Пользователи написали за сегодня столько сообщений:\n"
    stats_text += "\n".join([f"@{user} - {count}" for user, count in user_message_count.items()])

    await update.message.reply_text(stats_text)


# Функция для сброса статистики (выполняется ежедневно)
async def reset_message_count():
    global user_message_count
    user_message_count = {}
    logger.info("Статистика сообщений сброшена.")


# Главная функция для запуска бота
def main():
    global bot
    # Создаем приложение Telegram
    application = Application.builder().token(TOKEN).build()

    # Сохраняем объект бота в глобальной переменной
    bot = application.bot

    # Регистрация команд
    application.add_handler(CommandHandler("add_participant", add_participant))
    application.add_handler(CommandHandler("list_participants", list_participants))
    application.add_handler(CommandHandler("remove_participant", remove_participant))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("manual_check", manual_check))  # Команда ручной проверки
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("set_time", set_time))
    # Обработчик всех текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_message))

    # Запускаем планировщик
    setup_daily_check()

    logger.info("Бот запущен!")
    application.run_polling()


if __name__ == "__main__":
    main()
