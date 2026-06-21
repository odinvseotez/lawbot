"""Разбор даты/времени, введённых человеком."""
from datetime import datetime

import config


def parse_deadline(text: str) -> datetime | None:
    """
    Принимает строки вида:
      '31.12.2026 18:00'  /  '31.12.2026'  /  '31.12 18:00'  /  '31.12'
    Возвращает datetime с часовым поясом из config.TZ или None, если не распознано.
    Если время не указано — ставится 18:00.
    """
    text = text.strip()
    now = datetime.now(config.TZ)

    fmts_with_time = ["%d.%m.%Y %H:%M", "%d.%m.%y %H:%M", "%d.%m %H:%M"]
    fmts_date_only = ["%d.%m.%Y", "%d.%m.%y", "%d.%m"]

    for fmt in fmts_with_time:
        try:
            dt = datetime.strptime(text, fmt)
            if "%Y" not in fmt and "%y" not in fmt:
                dt = dt.replace(year=now.year)
            return dt.replace(tzinfo=config.TZ)
        except ValueError:
            continue

    for fmt in fmts_date_only:
        try:
            dt = datetime.strptime(text, fmt)
            if "%Y" not in fmt and "%y" not in fmt:
                dt = dt.replace(year=now.year)
            return dt.replace(hour=18, minute=0, tzinfo=config.TZ)
        except ValueError:
            continue

    return None
