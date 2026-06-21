"""
Слой работы с базой данных (PostgreSQL через asyncpg).

Схема:
  assistants      — ассистенты (Telegram-пользователи, которым отдаются дела)
  clients         — клиенты
  cases           — дела (привязаны к клиенту, опционально к ассистенту)
  tasks           — задачи внутри дела, поставленные ассистенту (с дедлайном)
  stages          — журнал стадий движения дела
  reports         — еженедельные отчёты ассистентов
"""
import asyncpg

import config

_pool: asyncpg.Pool | None = None


async def init_pool() -> None:
    """Создать пул соединений и таблицы (если их ещё нет)."""
    global _pool
    _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=10)
    await _create_schema()


async def close_pool() -> None:
    if _pool:
        await _pool.close()


def pool() -> asyncpg.Pool:
    assert _pool is not None, "Пул БД не инициализирован"
    return _pool


async def _create_schema() -> None:
    async with _pool.acquire() as con:
        await con.execute(
            """
        CREATE TABLE IF NOT EXISTS assistants (
            id          SERIAL PRIMARY KEY,
            tg_id       BIGINT UNIQUE,           -- Telegram ID; NULL пока не привязан
            full_name   TEXT NOT NULL,
            username    TEXT,                    -- @username для подсказки
            active      BOOLEAN NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS clients (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            contact     TEXT,                    -- телефон/почта/иное
            note        TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS cases (
            id            SERIAL PRIMARY KEY,
            client_id     INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            title         TEXT NOT NULL,         -- краткое название дела
            description   TEXT,                  -- суть дела
            assistant_id  INTEGER REFERENCES assistants(id) ON DELETE SET NULL,
            price         NUMERIC(12, 2),        -- стоимость услуги для клиента
            assistant_fee NUMERIC(12, 2),        -- доля ассистента
            fee_paid      BOOLEAN NOT NULL DEFAULT FALSE,  -- заплатил ли я ассистенту
            court_link    TEXT,                  -- ссылка на КАД/суд
            status        TEXT NOT NULL DEFAULT 'open',  -- open / closed
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id            SERIAL PRIMARY KEY,
            case_id       INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            description   TEXT NOT NULL,
            assigned_at   TIMESTAMPTZ NOT NULL DEFAULT now(),  -- когда поставлена
            deadline      TIMESTAMPTZ,                          -- дедлайн (может быть NULL)
            remind_before INTEGER NOT NULL DEFAULT 24,          -- за сколько часов напомнить
            reminded      BOOLEAN NOT NULL DEFAULT FALSE,       -- напоминание уже отправлено
            done          BOOLEAN NOT NULL DEFAULT FALSE,
            done_at       TIMESTAMPTZ
        );

        CREATE TABLE IF NOT EXISTS stages (
            id          SERIAL PRIMARY KEY,
            case_id     INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            text        TEXT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            author      TEXT                      -- 'owner' или имя ассистента
        );

        CREATE TABLE IF NOT EXISTS reports (
            id            SERIAL PRIMARY KEY,
            case_id       INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            assistant_id  INTEGER REFERENCES assistants(id) ON DELETE SET NULL,
            text          TEXT NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
        )


# ----------------------------------------------------------------------------
#  Ассистенты
# ----------------------------------------------------------------------------
async def add_assistant(full_name: str, username: str | None) -> int:
    async with _pool.acquire() as con:
        return await con.fetchval(
            "INSERT INTO assistants (full_name, username) VALUES ($1, $2) RETURNING id",
            full_name,
            username,
        )


async def link_assistant_tg(assistant_id: int, tg_id: int) -> None:
    async with _pool.acquire() as con:
        await con.execute(
            "UPDATE assistants SET tg_id = $1 WHERE id = $2", tg_id, assistant_id
        )


async def get_assistant_by_tg(tg_id: int) -> asyncpg.Record | None:
    async with _pool.acquire() as con:
        return await con.fetchrow("SELECT * FROM assistants WHERE tg_id = $1", tg_id)


async def get_assistant(assistant_id: int) -> asyncpg.Record | None:
    async with _pool.acquire() as con:
        return await con.fetchrow("SELECT * FROM assistants WHERE id = $1", assistant_id)


async def list_assistants(active_only: bool = True) -> list[asyncpg.Record]:
    q = "SELECT * FROM assistants"
    if active_only:
        q += " WHERE active = TRUE"
    q += " ORDER BY full_name"
    async with _pool.acquire() as con:
        return await con.fetch(q)


# ----------------------------------------------------------------------------
#  Клиенты
# ----------------------------------------------------------------------------
async def add_client(name: str, contact: str | None, note: str | None) -> int:
    async with _pool.acquire() as con:
        return await con.fetchval(
            "INSERT INTO clients (name, contact, note) VALUES ($1, $2, $3) RETURNING id",
            name,
            contact,
            note,
        )


async def list_clients() -> list[asyncpg.Record]:
    async with _pool.acquire() as con:
        return await con.fetch("SELECT * FROM clients ORDER BY name")


async def get_client(client_id: int) -> asyncpg.Record | None:
    async with _pool.acquire() as con:
        return await con.fetchrow("SELECT * FROM clients WHERE id = $1", client_id)


# ----------------------------------------------------------------------------
#  Дела
# ----------------------------------------------------------------------------
async def add_case(
    client_id: int,
    title: str,
    description: str | None,
    assistant_id: int | None,
    price: float | None,
    assistant_fee: float | None,
    court_link: str | None,
) -> int:
    async with _pool.acquire() as con:
        return await con.fetchval(
            """INSERT INTO cases
               (client_id, title, description, assistant_id, price, assistant_fee, court_link)
               VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
            client_id,
            title,
            description,
            assistant_id,
            price,
            assistant_fee,
            court_link,
        )


async def get_case(case_id: int) -> asyncpg.Record | None:
    async with _pool.acquire() as con:
        return await con.fetchrow(
            """SELECT c.*, cl.name AS client_name, a.full_name AS assistant_name,
                      a.tg_id AS assistant_tg
               FROM cases c
               JOIN clients cl ON cl.id = c.client_id
               LEFT JOIN assistants a ON a.id = c.assistant_id
               WHERE c.id = $1""",
            case_id,
        )


async def list_cases(status: str | None = "open") -> list[asyncpg.Record]:
    q = """SELECT c.*, cl.name AS client_name, a.full_name AS assistant_name
           FROM cases c
           JOIN clients cl ON cl.id = c.client_id
           LEFT JOIN assistants a ON a.id = c.assistant_id"""
    args = []
    if status:
        q += " WHERE c.status = $1"
        args.append(status)
    q += " ORDER BY c.created_at DESC"
    async with _pool.acquire() as con:
        return await con.fetch(q, *args)


async def list_cases_for_assistant(assistant_id: int, status: str | None = "open"):
    q = """SELECT c.*, cl.name AS client_name
           FROM cases c
           JOIN clients cl ON cl.id = c.client_id
           WHERE c.assistant_id = $1"""
    args = [assistant_id]
    if status:
        q += " AND c.status = $2"
        args.append(status)
    q += " ORDER BY c.created_at DESC"
    async with _pool.acquire() as con:
        return await con.fetch(q, *args)


async def set_fee_paid(case_id: int, paid: bool) -> None:
    async with _pool.acquire() as con:
        await con.execute("UPDATE cases SET fee_paid = $1 WHERE id = $2", paid, case_id)


async def assign_case(case_id: int, assistant_id: int | None) -> None:
    async with _pool.acquire() as con:
        await con.execute(
            "UPDATE cases SET assistant_id = $1 WHERE id = $2", assistant_id, case_id
        )


async def close_case(case_id: int) -> None:
    async with _pool.acquire() as con:
        await con.execute("UPDATE cases SET status = 'closed' WHERE id = $1", case_id)


# ----------------------------------------------------------------------------
#  Задачи
# ----------------------------------------------------------------------------
async def add_task(
    case_id: int, description: str, deadline, remind_before: int
) -> int:
    async with _pool.acquire() as con:
        return await con.fetchval(
            """INSERT INTO tasks (case_id, description, deadline, remind_before)
               VALUES ($1, $2, $3, $4) RETURNING id""",
            case_id,
            description,
            deadline,
            remind_before,
        )


async def get_task(task_id: int) -> asyncpg.Record | None:
    async with _pool.acquire() as con:
        return await con.fetchrow(
            """SELECT t.*, c.title AS case_title, c.assistant_id,
                      a.tg_id AS assistant_tg, a.full_name AS assistant_name
               FROM tasks t
               JOIN cases c ON c.id = t.case_id
               LEFT JOIN assistants a ON a.id = c.assistant_id
               WHERE t.id = $1""",
            task_id,
        )


async def list_tasks_for_case(case_id: int, only_open: bool = False):
    q = "SELECT * FROM tasks WHERE case_id = $1"
    if only_open:
        q += " AND done = FALSE"
    q += " ORDER BY deadline NULLS LAST, assigned_at"
    async with _pool.acquire() as con:
        return await con.fetch(q, case_id)


async def mark_task_done(task_id: int) -> None:
    async with _pool.acquire() as con:
        await con.execute(
            "UPDATE tasks SET done = TRUE, done_at = now() WHERE id = $1", task_id
        )


async def due_tasks_for_reminder():
    """
    Задачи, у которых дедлайн наступит в пределах remind_before часов,
    ещё не выполнены и напоминание ещё не отправлялось.
    """
    async with _pool.acquire() as con:
        return await con.fetch(
            """SELECT t.*, c.title AS case_title, a.tg_id AS assistant_tg,
                      a.full_name AS assistant_name
               FROM tasks t
               JOIN cases c ON c.id = t.case_id
               LEFT JOIN assistants a ON a.id = c.assistant_id
               WHERE t.done = FALSE
                 AND t.reminded = FALSE
                 AND t.deadline IS NOT NULL
                 AND t.deadline <= now() + (t.remind_before || ' hours')::interval
                 AND t.deadline > now()"""
        )


async def mark_task_reminded(task_id: int) -> None:
    async with _pool.acquire() as con:
        await con.execute("UPDATE tasks SET reminded = TRUE WHERE id = $1", task_id)


# ----------------------------------------------------------------------------
#  Стадии
# ----------------------------------------------------------------------------
async def add_stage(case_id: int, text: str, author: str) -> None:
    async with _pool.acquire() as con:
        await con.execute(
            "INSERT INTO stages (case_id, text, author) VALUES ($1, $2, $3)",
            case_id,
            text,
            author,
        )


async def list_stages(case_id: int):
    async with _pool.acquire() as con:
        return await con.fetch(
            "SELECT * FROM stages WHERE case_id = $1 ORDER BY created_at", case_id
        )


# ----------------------------------------------------------------------------
#  Отчёты
# ----------------------------------------------------------------------------
async def add_report(case_id: int, assistant_id: int | None, text: str) -> None:
    async with _pool.acquire() as con:
        await con.execute(
            "INSERT INTO reports (case_id, assistant_id, text) VALUES ($1, $2, $3)",
            case_id,
            assistant_id,
            text,
        )


async def cases_with_active_assistant():
    """Открытые дела, у которых назначен ассистент с привязанным Telegram."""
    async with _pool.acquire() as con:
        return await con.fetch(
            """SELECT c.id, c.title, cl.name AS client_name,
                      a.tg_id AS assistant_tg, a.full_name AS assistant_name
               FROM cases c
               JOIN clients cl ON cl.id = c.client_id
               JOIN assistants a ON a.id = c.assistant_id
               WHERE c.status = 'open' AND a.tg_id IS NOT NULL AND a.active = TRUE"""
        )
