"""
Конфигурация бота. Все секреты и настройки берутся из переменных окружения
(см. файл .env). Ничего секретного в коде не хранится.
"""
import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

# --- Обязательные настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("Не задан BOT_TOKEN в .env")

# Telegram ID владельца (главного юриста). Узнать можно у @userinfobot.
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
if not OWNER_ID:
    raise RuntimeError("Не задан OWNER_ID в .env")

# --- База данных ---
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://lawbot:lawbot@localhost:5432/lawbot",
)

# --- Время / часовой пояс ---
# По умолчанию Томск (UTC+7). Поменяйте при необходимости.
TZ_NAME = os.getenv("TZ", "Asia/Tomsk")
TZ = ZoneInfo(TZ_NAME)

# Время еженедельного опроса ассистентов (день недели + час).
# 0 = понедельник ... 6 = воскресенье.
WEEKLY_POLL_DOW = int(os.getenv("WEEKLY_POLL_DOW", "0"))   # понедельник
WEEKLY_POLL_HOUR = int(os.getenv("WEEKLY_POLL_HOUR", "10"))  # 10:00

# Час, в который ежедневно проверяются приближающиеся дедлайны.
DEADLINE_CHECK_HOUR = int(os.getenv("DEADLINE_CHECK_HOUR", "9"))  # 09:00

# --- Полезные внешние ссылки (российские суды) ---
COURT_LINKS = {
    "Картотека арбитражных дел (КАД)": "https://kad.arbitr.ru/",
    "ГАС «Правосудие» (суды общей юрисдикции)": "https://ej.sudrf.ru/",
    "Поиск по судам общей юрисдикции": "https://sudrf.ru/",
    "Верховный Суд РФ": "https://vsrf.ru/",
    "Конституционный Суд РФ": "http://www.ksrf.ru/",
    "Электронное правосудие (my.arbitr)": "https://my.arbitr.ru/",
    "ФССП (банк исполнительных производств)": "https://fssp.gov.ru/iss/ip",
}
