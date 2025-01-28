import logging
import pytz
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Настройки
TOKEN = '1'
GROUP_CHAT_ID = -1
BERLIN_TZ = pytz.timezone('Europe/Berlin')

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Глобальный список участников
group_participants = []


# Функция для проверки неактивных пользователей
async def check_inactive_users():
    logger.info("Проверка неактивных пользователей.")
    now = datetime.now(BERLIN_TZ)
    # Здесь ваша логика для проверки активности участников
    inactive_users = []
    for participant in group_participants:
        last_message_time = participant.get("last_message_time")
        if last_message_time is None or now - last_message_time > timedelta(hours=1):  # Пример 1 час
            inactive_users.append(participant["nickname"])

    if inactive_users:
        logger.info(f"Неактивные пользователи: {', '.join(inactive_users)}")
    else:
        logger.info("Все пользователи активны.")


# Настройка планировщика для ежедневной задачи в 11:00 по Берлину
def setup_daily_check():
    scheduler = BackgroundScheduler()

    # Добавляем задачу для ежедневной проверки в 11:00 по времени Берлина
    scheduler.add_job(
        async_job_wrapper(check_inactive_users),  # Оборачиваем в асинхронную задачу
        CronTrigger(hour=11, minute=0, second=0, timezone=BERLIN_TZ)  # Время 11:00 по Берлину
    )

    scheduler.start()


# Обертка для асинхронной задачи
def async_job_wrapper(func):
    async def wrapper():
        await func()

    return wrapper


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


# Главная функция для запуска бота
def main():
    # Создаем приложение Telegram
    application = Application.builder().token(TOKEN).build()

    # Регистрация команд
    application.add_handler(CommandHandler("add_participant", add_participant))
    application.add_handler(CommandHandler("list_participants", list_participants))
    application.add_handler(CommandHandler("manual_check", manual_check))  # Команда ручной проверки

    # Запускаем планировщик
    setup_daily_check()

    logger.info("Бот запущен!")
    application.run_polling()


if __name__ == "__main__":
    main()
