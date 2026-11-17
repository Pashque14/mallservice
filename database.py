import hashlib
import os
import sqlite3
from datetime import datetime

DB_NAME = "mall.db"
CREDENTIALS_FILE = "credentials.txt"
UPLOAD_DIR = "uploads"
TEMPLATE_CONTRACT_PATH = os.path.join(UPLOAD_DIR, "Шаблон_договора_аренды_ТЦ.txt")

os.makedirs(UPLOAD_DIR, exist_ok=True)


def ensure_contract_template():
    """Создает файл типового шаблона договора аренды, если его еще нет"""
    if os.path.exists(TEMPLATE_CONTRACT_PATH):
        return
    template_text = """ТИПОВОЙ ДОГОВОР АРЕНДЫ НЕЖИЛОГО ПОМЕЩЕНИЯ № ___/2026

г. Екатеринбург                                                 «___» __________ 2026 г.

ООО «Управляющая компания ТЦ» (Арендодатель) с одной стороны и
_____________________________________________ (Арендатор) с другой стороны
заключили настоящий Договор о нижеследующем:

1. ПРЕДМЕТ ДОГОВОРА
1.1. Арендодатель обязуется предоставить Арендатору за плату во временное владение
и пользование торговое помещение (павильон) в здании Торгового Центра.
1.2. Назначение помещения: розничная торговля / оказание услуг.

2. АРЕНДНАЯ ПЛАТА И ПОРЯДОК РАСЧЕТОВ
2.1. Постоянная часть арендной платы вносится ежемесячно не позднее 5-го числа
текущего месяца путем перечисления денежных средств на расчетный счет Арендодателя.
2.2. Переменная часть (электроэнергия, водоснабжение) оплачивается по показаниям
индивидуальных приборов учета.

3. ЭКСПЛУАТАЦИЯ И РЕМОНТ
3.1. Арендатор обязуется соблюдать правила пожарной безопасности и регламент ТЦ.
3.2. Заявки на устранение технических неисправностей подаются через систему MallService.

4. РЕКВИЗИТЫ И ПОДПИСИ СТОРОН
Арендодатель: ООО «УК ТЦ»                 Арендатор: _______________________
М.П.                                       М.П.
"""
    with open(TEMPLATE_CONTRACT_PATH, "w", encoding="utf-8") as f:
        f.write(template_text)


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def init_db():
    ensure_contract_template()

    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS spaces (
                id TEXT PRIMARY KEY,
                floor INTEGER NOT NULL,
                code TEXT NOT NULL,
                tenant TEXT,
                area REAL NOT NULL,
                price INTEGER NOT NULL,
                status TEXT NOT NULL,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                w INTEGER NOT NULL,
                h INTEGER NOT NULL,
                point_director TEXT DEFAULT '',
                area_director TEXT DEFAULT '',
                internal_notes TEXT DEFAULT '',
                contract_number TEXT DEFAULT '',
                contract_end_date TEXT DEFAULT '',
                contract_file_name TEXT DEFAULT '',
                contract_file_path TEXT DEFAULT ''
            )
        """)

        # Мягкая миграция таблицы spaces
        space_cols = {row["name"] for row in conn.execute("PRAGMA table_info(spaces)").fetchall()}
        migrations = {
            "point_director": "TEXT DEFAULT ''",
            "area_director": "TEXT DEFAULT ''",
            "internal_notes": "TEXT DEFAULT ''",
            "contract_number": "TEXT DEFAULT ''",
            "contract_end_date": "TEXT DEFAULT ''",
            "contract_file_name": "TEXT DEFAULT ''",
            "contract_file_path": "TEXT DEFAULT ''",
        }
        for col, col_type in migrations.items():
            if col not in space_cols:
                conn.execute(f"ALTER TABLE spaces ADD COLUMN {col} {col_type}")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                space_id TEXT NOT NULL,
                space_code TEXT NOT NULL,
                tenant TEXT,
                category TEXT NOT NULL DEFAULT 'other',
                priority TEXT NOT NULL DEFAULT 'normal',
                description TEXT NOT NULL,
                photo_name TEXT DEFAULT '',
                photo_path TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL
            )
        """)

        ticket_cols = {row["name"] for row in conn.execute("PRAGMA table_info(tickets)").fetchall()}
        if "category" not in ticket_cols:
            conn.execute("ALTER TABLE tickets ADD COLUMN category TEXT NOT NULL DEFAULT 'other'")
        if "priority" not in ticket_cols:
            conn.execute("ALTER TABLE tickets ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'")
        if "photo_name" not in ticket_cols:
            conn.execute("ALTER TABLE tickets ADD COLUMN photo_name TEXT DEFAULT ''")
        if "photo_path" not in ticket_cols:
            conn.execute("ALTER TABLE tickets ADD COLUMN photo_path TEXT DEFAULT ''")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_role TEXT NOT NULL,
                space_id TEXT NOT NULL,
                space_code TEXT NOT NULL,
                tenant_name TEXT NOT NULL,
                body TEXT NOT NULL,
                attachment_name TEXT DEFAULT '',
                attachment_path TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                space_id TEXT,
                display_name TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS mall_contacts (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                director_info TEXT NOT NULL,
                dispatcher_info TEXT NOT NULL,
                email TEXT NOT NULL
            )
        """)

        conn.execute("""
            INSERT OR IGNORE INTO mall_contacts (id, director_info, dispatcher_info, email)
            VALUES (
                1,
                'Соколов Андрей Викторович — +7 (912) 555-01-10',
                'Круглосуточная диспетчерская — +7 (343) 200-45-99',
                'uk-mall@mallservice.ru'
            )
        """)

        if conn.execute("SELECT COUNT(*) FROM spaces").fetchone()[0] == 0:
            initial_spaces = []
            sample_data = {
                "1_top_1": ("1-01", "Кофейня «Бодрость»", 42.0, 145000, "occupied", "Иванова Мария, +7 (904) 111-22-33", "Петров Сергей (куратор сети), +7 (904) 999-88-77", "Мокрая точка (подвод воды и канализации).", "№ 01-А/2026", "31.12.2026"),
                "1_top_2": ("1-02", "", 55.0, 175000, "free", "", "", "Потенциальный арендатор: табачная лавка, звонили 10.11.", "", ""),
                "1_top_3": ("1-03", "Аптека «Здоровье»", 60.0, 190000, "occupied", "Смирнова Елена, +7 (922) 333-44-55", "Кузнецов Олег (терр. директор), +7 (922) 777-66-55", "Якорный арендатор, оплата всегда вовремя.", "№ 03-А/2025", "30.06.2027"),
                "1_bot_1": ("1-04", "", 48.0, 150000, "free", "", "", "", "", ""),
                "1_bot_2": ("1-05", "Оптика «Взгляд»", 38.0, 125000, "reserved", "Волков Дмитрий, +7 (950) 444-11-22", "", "Ждем подписанный скан договора до пятницы.", "Проект № 05-А/2026", "01.12.2027"),
                "1_bot_3": ("1-06", "", 75.0, 220000, "free", "", "", "", "", ""),
                "2_top_1": ("2-01", "Одежда «Стиль»", 85.0, 160000, "occupied", "Морозова Анна, +7 (912) 888-00-11", "Белова Ольга (рег. директор), +7 (912) 888-00-99", "Просили рассмотреть скидку 10% на январь-февраль.", "№ 11-А/2026", "31.10.2026"),
                "2_top_2": ("2-02", "", 64.0, 120000, "free", "", "", "", "", ""),
                "2_top_3": ("2-03", "", 64.0, 120000, "free", "", "", "", "", ""),
                "2_bot_1": ("2-04", "Книги и канцтовары", 50.0, 95000, "occupied", "Новиков Илья (ИП), +7 (963) 222-33-44", "", "", "№ 14-А/2026", "15.08.2027"),
                "2_bot_2": ("2-05", "", 45.0, 88000, "free", "", "", "", "", ""),
                "2_bot_3": ("2-06", "Фудкорт / Пекарня", 90.0, 180000, "reserved", "Зайцева Наталья, +7 (908) 555-66-77", "", "Требуется усиленная вытяжка, согласовано с главным инженером.", "Проект № 16-А/2026", "31.12.2027"),
            }

            x_positions = [30, 215, 400]
            for floor in (1, 2):
                for idx, x in enumerate(x_positions, start=1):
                    top_id = f"{floor}_top_{idx}"
                    code, tenant, area, price, status, p_dir, a_dir, notes, c_num, c_end = sample_data[top_id]
                    initial_spaces.append((top_id, floor, code, tenant, area, price, status, x, 20, 170, 110, p_dir, a_dir, notes, c_num, c_end, "", ""))

                    bot_id = f"{floor}_bot_{idx}"
                    code, tenant, area, price, status, p_dir, a_dir, notes, c_num, c_end = sample_data[bot_id]
                    initial_spaces.append((bot_id, floor, code, tenant, area, price, status, x, 230, 170, 110, p_dir, a_dir, notes, c_num, c_end, "", ""))

            conn.executemany(
                "INSERT INTO spaces VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                initial_spaces,
            )
        else:
            # Дозаполним демо-номера договоров в существующей БД, если они пустые
            demo_contracts = {
                "1_top_1": ("№ 01-А/2026", "31.12.2026"),
                "1_top_3": ("№ 03-А/2025", "30.06.2027"),
                "1_bot_2": ("Проект № 05-А/2026", "01.12.2027"),
                "2_top_1": ("№ 11-А/2026", "31.10.2026"),
                "2_bot_1": ("№ 14-А/2026", "15.08.2027"),
                "2_bot_3": ("Проект № 16-А/2026", "31.12.2027"),
            }
            for sid, (c_num, c_end) in demo_contracts.items():
                conn.execute(
                    """UPDATE spaces SET contract_number = ?, contract_end_date = ?
                       WHERE id = ? AND COALESCE(contract_number, '') = ''""",
                    (c_num, c_end, sid),
                )

        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            default_users = [
                ("admin", "admin123", "landlord", None, "Управляющая компания ТЦ"),
                ("tenant_101", "coffee101", "tenant", "1_top_1", "Кофейня «Бодрость» (1-01)"),
                ("tenant_103", "apteka103", "tenant", "1_top_3", "Аптека «Здоровье» (1-03)"),
                ("tenant_201", "style201", "tenant", "2_top_1", "Одежда «Стиль» (2-01)"),
                ("tenant_204", "books204", "tenant", "2_bot_1", "Книги и канцтовары (2-04)"),
            ]

            conn.executemany(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
                [(u, hash_password(p), role, sid, name) for u, p, role, sid, name in default_users],
            )

            lines = [
                "==========================================",
                "УЧЕТНЫЕ ЗАПИСИ ДЛЯ ВХОДА В MALLSERVICE",
                "==========================================",
                "",
                "[АРЕНДОДАТЕЛЬ / УПРАВЛЯЮЩИЙ ТЦ]",
                "Логин:  admin",
                "Пароль: admin123",
                "",
                "[АРЕНДАТОРЫ]",
            ]
            for u, p, role, sid, name in default_users:
                if role == "tenant":
                    lines.append(f"• {name}")
                    lines.append(f"  Логин:  {u}")
                    lines.append(f"  Пароль: {p}")
                    lines.append("")

            with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))


def authenticate_user(username: str, password: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT username, role, space_id, display_name FROM users WHERE username = ? AND password_hash = ?",
            (username.strip(), hash_password(password)),
        ).fetchone()
        return dict(row) if row else None


def get_spaces_by_floor(floor: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM spaces WHERE floor = ? ORDER BY code", (floor,)
        ).fetchall()
        return [dict(row) for row in rows]


def get_all_spaces() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM spaces ORDER BY code").fetchall()
        return [dict(row) for row in rows]


def get_space_by_id(space_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM spaces WHERE id = ?", (space_id,)).fetchone()
        return dict(row) if row else None


def update_space(
    space_id: str,
    status: str,
    tenant: str,
    price: int,
    point_director: str,
    area_director: str,
    internal_notes: str,
):
    with get_connection() as conn:
        conn.execute(
            """UPDATE spaces
               SET status = ?, tenant = ?, price = ?, point_director = ?, area_director = ?, internal_notes = ?
               WHERE id = ?""",
            (
                status,
                tenant.strip(),
                price,
                point_director.strip(),
                area_director.strip(),
                internal_notes.strip(),
                space_id,
            ),
        )


def update_space_contract(
    space_id: str,
    contract_number: str,
    contract_end_date: str,
    file_name: str | None = None,
    file_path: str | None = None,
):
    with get_connection() as conn:
        if file_name is not None and file_path is not None:
            conn.execute(
                """UPDATE spaces
                   SET contract_number = ?, contract_end_date = ?, contract_file_name = ?, contract_file_path = ?
                   WHERE id = ?""",
                (contract_number.strip(), contract_end_date.strip(), file_name, file_path, space_id),
            )
        else:
            conn.execute(
                """UPDATE spaces
                   SET contract_number = ?, contract_end_date = ?
                   WHERE id = ?""",
                (contract_number.strip(), contract_end_date.strip(), space_id),
            )


def get_mall_contacts() -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM mall_contacts WHERE id = 1").fetchone()
        return dict(row) if row else {"director_info": "", "dispatcher_info": "", "email": ""}


# --- ЗАЯВКИ НА РЕМОНТ ---

def create_ticket(
    space_id: str,
    category: str,
    priority: str,
    description: str,
    photo_name: str = "",
    photo_path: str = "",
):
    space = get_space_by_id(space_id)
    if not space or not description.strip():
        return
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO tickets
               (space_id, space_code, tenant, category, priority, description, photo_name, photo_path, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)""",
            (
                space_id,
                space["code"],
                space["tenant"] or "Без названия",
                category,
                priority,
                description.strip(),
                photo_name,
                photo_path,
                now,
            ),
        )


def get_tickets(space_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if space_id:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE space_id = ? ORDER BY id DESC", (space_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM tickets
                   ORDER BY
                     CASE status WHEN 'new' THEN 1 WHEN 'in_progress' THEN 2 ELSE 3 END,
                     CASE priority WHEN 'urgent' THEN 1 ELSE 2 END,
                     id DESC"""
            ).fetchall()
        return [dict(row) for row in rows]


def update_ticket_status(ticket_id: int, status: str):
    with get_connection() as conn:
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))


def get_active_ticket_alerts() -> dict[str, str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT space_id, priority FROM tickets WHERE status != 'done'"
        ).fetchall()
        alerts: dict[str, str] = {}
        for row in rows:
            sid = row["space_id"]
            if row["priority"] == "urgent" or alerts.get(sid) != "urgent":
                alerts[sid] = row["priority"]
        return alerts


# --- СООБЩЕНИЯ И РАССЫЛКИ ---

def send_message(
    sender_role: str,
    target_space_id: str,
    body: str,
    attachment_name: str = "",
    attachment_path: str = "",
):
    if not body.strip() and not attachment_name:
        return

    if target_space_id == "ALL":
        space_code = "ВСЕМ"
        tenant_name = "Общая рассылка по ТЦ"
    else:
        space = get_space_by_id(target_space_id)
        if not space:
            return
        space_code = space["code"]
        tenant_name = space["tenant"] or "Свободный павильон"

    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO messages
               (sender_role, space_id, space_code, tenant_name, body, attachment_name, attachment_path, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (sender_role, target_space_id, space_code, tenant_name, body.strip(), attachment_name, attachment_path, now),
        )


def get_messages_for_landlord() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM messages ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]


def get_messages_for_tenant(space_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE space_id = ? OR space_id = 'ALL' ORDER BY id DESC",
            (space_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_sync_signature() -> tuple:
    with get_connection() as conn:
        tickets_sig = conn.execute(
            "SELECT COUNT(*), COALESCE(GROUP_CONCAT(id || ':' || status), '') FROM tickets"
        ).fetchone()
        spaces_sig = conn.execute(
            """SELECT COALESCE(GROUP_CONCAT(
                id || ':' || status || ':' || COALESCE(tenant, '') || ':' || price || ':' ||
                COALESCE(point_director, '') || ':' || COALESCE(area_director, '') || ':' ||
                COALESCE(internal_notes, '') || ':' || COALESCE(contract_number, '') || ':' ||
                COALESCE(contract_end_date, '') || ':' || COALESCE(contract_file_name, '')
            ), '') FROM spaces"""
        ).fetchone()
        msgs_sig = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM messages"
        ).fetchone()
        return (tickets_sig[0], tickets_sig[1], spaces_sig[0], msgs_sig[0], msgs_sig[1])