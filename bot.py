"""
Точка входа. Запуск:  python bot.py
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
import db
import handlers_owner
import handlers_shared
from scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("lawbot")


async def main() -> None:
    # Инициализируем БД (создаём таблицы при первом запуске)
    await db.init_pool()
    log.info("База данных готова.")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Порядок важен: сначала владелец (с фильтром), потом общий роутер.
    dp.include_router(handlers_owner.router)
    dp.include_router(handlers_shared.router)

    # Планировщик напоминаний
    scheduler = setup_scheduler(bot)
    scheduler.start()
    log.info("Планировщик запущен (еженедельный опрос + проверка дедлайнов).")

    log.info("Бот запущен. Ожидаю сообщения…")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await db.close_pool()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Остановлено.")
