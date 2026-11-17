import csv
import hashlib
import os
import sqlite3
from datetime import datetime

DB_NAME = "mall.db"
CREDENTIALS_FILE = "credentials.txt"
UPLOAD_DIR = "uploads"
TEMPLATE_CONTRACT_PATH = os.path.join(UPLOAD_DIR, "Шаблон_договора_аренды_ТЦ.txt")

# Тарифы ТЦ для автоматического расчета переменной части аренды (коммуналки)
HVS_TARIFF = 48.0      # Холодная вода (ХВС), ₽ за 1 м³
GVS_TARIFF = 195.0     # Горячая вода (ГВС), ₽ за 1 м³
ELEC_TARIFF = 6.5      # Электроэнергия, ₽ за 1 кВт·ч

os.makedirs(UPLOAD_DIR, exist_ok=True)


def current_month_str() -> str:
    return datetime.now().strftime("%m.%Y")


def is_due_date_passed(due_date_str: str) -> bool:
    """Проверяет, истек ли срок оплаты (формат ДД.ММ.ГГГГ)"""
    if not due_date_str or not due_date_str.strip():
        return False
    try:
        due_dt = datetime.strptime(due_date_str.strip(), "%d.%m.%Y").date()
        return datetime.now().date() > due_dt
    except ValueError:
        return False


def ensure_contract_template():
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

2. АРЕНДНАЯ ПЛАТА И ПОРЯДОК РАСЧЕТОВ
2.1. Постоянная часть арендной платы вносится ежемесячно не позднее 5-го числа
текущего месяца путем перечисления денежных средств на расчетный счет Арендодателя.
2.2. Переменная часть (ХВС, ГВС, электроэнергия) оплачивается по показаниям
индивидуальных приборов учета.

3. ЭКСПЛУАТАЦИЯ И РЕМОНТ
3.1. Заявки на устранение технических неисправностей подаются через систему MallService.
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
                contract_file_path TEXT DEFAULT '',
                payment_status TEXT DEFAULT 'paid',
                prev_hvs REAL DEFAULT 0,
                prev_gvs REAL DEFAULT 0,
                prev_elec REAL DEFAULT 0
            )
        """)

        space_cols = {row["name"] for row in conn.execute("PRAGMA table_info(spaces)").fetchall()}
        migrations = {
            "point_director": "TEXT DEFAULT ''",
            "area_director": "TEXT DEFAULT ''",
            "internal_notes": "TEXT DEFAULT ''",
            "contract_number": "TEXT DEFAULT ''",
            "contract_end_date": "TEXT DEFAULT ''",
            "contract_file_name": "TEXT DEFAULT ''",
            "contract_file_path": "TEXT DEFAULT ''",
            "payment_status": "TEXT DEFAULT 'paid'",
            "prev_hvs": "REAL DEFAULT 0",
            "prev_gvs": "REAL DEFAULT 0",
            "prev_elec": "REAL DEFAULT 0",
            "deposit_required": "INTEGER DEFAULT 0",
            "deposit_paid": "INTEGER DEFAULT 0",
            "penalty_rate": "REAL DEFAULT 0.1",
            "turnover_percent": "REAL DEFAULT 0.0",
        }
        for col, col_type in migrations.items():
            if col not in space_cols:
                conn.execute(f"ALTER TABLE spaces ADD COLUMN {col} {col_type}")

        # Обновим дефолты для депозитов и % товарооборота для существующих павильонов
        conn.execute("""
            UPDATE spaces
            SET deposit_required = price, deposit_paid = price, penalty_rate = 0.1
            WHERE (deposit_required IS NULL OR deposit_required = 0) AND price > 0 AND status = 'occupied'
        """)
        conn.execute("""
            UPDATE spaces
            SET turnover_percent = 3.0
            WHERE code = '1-01' AND (turnover_percent IS NULL OR turnover_percent = 0.0)
        """)
        conn.execute("""
            UPDATE spaces
            SET turnover_percent = 5.0
            WHERE code = '2-01' AND (turnover_percent IS NULL OR turnover_percent = 0.0)
        """)

        if "prev_water" in space_cols:
            conn.execute("UPDATE spaces SET prev_hvs = prev_water WHERE prev_hvs = 0 AND prev_water > 0")

        conn.execute("UPDATE spaces SET payment_status = 'unpaid' WHERE payment_status = 'pending'")

        # Помесячная история платежей и фиксации просрочек
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rent_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                space_id TEXT NOT NULL,
                period TEXT NOT NULL,
                amount INTEGER NOT NULL,
                is_paid INTEGER NOT NULL DEFAULT 0,
                was_overdue INTEGER NOT NULL DEFAULT 0,
                paid_date TEXT DEFAULT '',
                note TEXT DEFAULT '',
                UNIQUE(space_id, period)
            )
        """)

        # Формы-заявки на оплату (Счет/Акт УК -> Платежка Арендатора -> Закрытие УК)
        # Статусы: 'awaiting_payment' | 'under_review' | 'closed'
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                space_id TEXT NOT NULL,
                space_code TEXT NOT NULL,
                tenant_name TEXT NOT NULL,
                period TEXT NOT NULL,
                title TEXT NOT NULL,
                amount INTEGER NOT NULL,
                due_date TEXT NOT NULL,
                bill_file_name TEXT DEFAULT '',
                bill_file_path TEXT DEFAULT '',
                receipt_file_name TEXT DEFAULT '',
                receipt_file_path TEXT DEFAULT '',
                tenant_comment TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'awaiting_payment',
                was_overdue INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                paid_uploaded_at TEXT DEFAULT '',
                closed_at TEXT DEFAULT ''
            )
        """)

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
            CREATE TABLE IF NOT EXISTS meter_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                space_id TEXT NOT NULL,
                space_code TEXT NOT NULL,
                tenant_name TEXT NOT NULL,
                period TEXT NOT NULL,
                prev_hvs REAL NOT NULL DEFAULT 0,
                curr_hvs REAL NOT NULL DEFAULT 0,
                prev_gvs REAL NOT NULL DEFAULT 0,
                curr_gvs REAL NOT NULL DEFAULT 0,
                prev_elec REAL NOT NULL DEFAULT 0,
                curr_elec REAL NOT NULL DEFAULT 0,
                total_cost INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'submitted',
                created_at TEXT NOT NULL
            )
        """)

        mr_cols = {row["name"] for row in conn.execute("PRAGMA table_info(meter_readings)").fetchall()}
        if "prev_hvs" not in mr_cols:
            conn.execute("ALTER TABLE meter_readings ADD COLUMN prev_hvs REAL NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE meter_readings ADD COLUMN curr_hvs REAL NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE meter_readings ADD COLUMN prev_gvs REAL NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE meter_readings ADD COLUMN curr_gvs REAL NOT NULL DEFAULT 0")
            if "prev_water" in mr_cols:
                conn.execute("UPDATE meter_readings SET prev_hvs = prev_water, curr_hvs = curr_water")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS financial_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                space_id TEXT NOT NULL,
                space_code TEXT NOT NULL,
                tenant_name TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                title TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
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

        # БЛОК 1: Электронные пропуска
        conn.execute("""
            CREATE TABLE IF NOT EXISTS access_passes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                space_id TEXT NOT NULL,
                space_code TEXT NOT NULL,
                tenant_name TEXT NOT NULL,
                pass_type TEXT NOT NULL,
                work_date TEXT NOT NULL,
                time_window TEXT NOT NULL,
                vehicle_info TEXT DEFAULT '',
                workers_list TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                uk_comment TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        # БЛОК 1: Журнал плановых проверок и предписаний (ПБ, СЭС, Охрана труда)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS inspections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                space_id TEXT NOT NULL,
                space_code TEXT NOT NULL,
                tenant_name TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                deadline TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                uk_photo_path TEXT DEFAULT '',
                uk_photo_name TEXT DEFAULT '',
                tenant_report TEXT DEFAULT '',
                tenant_photo_path TEXT DEFAULT '',
                tenant_photo_name TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        # БЛОК 3: Маркетинг и согласование акций/вывесок
        conn.execute("""
            CREATE TABLE IF NOT EXISTS marketing_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                space_id TEXT NOT NULL,
                space_code TEXT NOT NULL,
                tenant_name TEXT NOT NULL,
                promo_type TEXT NOT NULL,
                title TEXT NOT NULL,
                date_range TEXT NOT NULL,
                description TEXT NOT NULL,
                mockup_file_name TEXT DEFAULT '',
                mockup_file_path TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                uk_feedback TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

        # БЛОК 3: Товарооборот арендаторов (% от выручки)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tenant_turnovers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                space_id TEXT NOT NULL,
                space_code TEXT NOT NULL,
                tenant_name TEXT NOT NULL,
                period TEXT NOT NULL,
                reported_revenue INTEGER NOT NULL,
                calculated_fee INTEGER NOT NULL,
                report_file_name TEXT DEFAULT '',
                report_file_path TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'submitted',
                created_at TEXT NOT NULL
            )
        """)

        # Демо-записи для пропусков
        if conn.execute("SELECT COUNT(*) FROM access_passes").fetchone()[0] == 0:
            demo_passes = [
                (
                    "1_top_1", "1-01", "Кофейня «Бодрость»", "cargo_in",
                    (datetime.now()).strftime("%d.%m.%Y"), "22:00 - 00:00",
                    "Газель Next В 123 АР 196", "Водитель: Сидоров А., экспедитор: Мельников К.",
                    "Доставка партии кофемашин, сиропов и зерен", "approved",
                    "Пропуск одобрен службой безопасности. Разгрузка через Дебаркадер №2.",
                    "16.11.2026 14:20"
                ),
                (
                    "2_top_1", "2-01", "Одежда «Стиль»", "night_work",
                    "25.11.2026", "23:00 - 05:00",
                    "Лада Ларгус М 777 ТТ 196", "Бригада монтажников: Кузнецов И., Лебедев С.",
                    "Монтаж новых рейлов и светодиодной подсветки витрины", "pending",
                    "",
                    "17.11.2026 11:45"
                ),
            ]
            conn.executemany(
                """INSERT INTO access_passes
                   (space_id, space_code, tenant_name, pass_type, work_date, time_window,
                    vehicle_info, workers_list, description, status, uk_comment, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                demo_passes,
            )

        # Демо-записи для предписаний
        if conn.execute("SELECT COUNT(*) FROM inspections").fetchone()[0] == 0:
            demo_inspections = [
                (
                    "1_top_1", "1-01", "Кофейня «Бодрость»", "fire_safety",
                    "Освободить проход к эвакуационному выходу от коробок с одноразовой посудой",
                    "28.11.2026", "open", "", "", "", "", "", "16.11.2026 10:15"
                ),
                (
                    "2_top_1", "2-01", "Одежда «Стиль»", "sanitary",
                    "Устранить скопление упаковочного полиэтилена в зоне примерочных кабинок",
                    "15.11.2026", "open", "", "", "", "", "", "12.11.2026 15:30"
                ),
            ]
            conn.executemany(
                """INSERT INTO inspections
                   (space_id, space_code, tenant_name, category, title, deadline, status,
                    uk_photo_path, uk_photo_name, tenant_report, tenant_photo_path, tenant_photo_name, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                demo_inspections,
            )

        # Демо-записи для маркетинга
        if conn.execute("SELECT COUNT(*) FROM marketing_requests").fetchone()[0] == 0:
            demo_marketing = [
                (
                    "1_top_1", "1-01", "Кофейня «Бодрость»", "promo_zone",
                    "Промо-стойка с дегустацией сезонного раф-кофе",
                    "25.11.2026 - 27.11.2026",
                    "Установка компактной брендированной промо-стойки 1.5х1.5м у центрального входа в атриум",
                    "", "", "approved",
                    "Согласовано отделом маркетинга. Подключение к сети у колонны №4.",
                    "15.11.2026 12:00"
                ),
                (
                    "2_top_1", "2-01", "Одежда «Стиль»", "sale_event",
                    "Распродажа Black Friday — скидки до 50%",
                    "27.11.2026 - 30.11.2026",
                    "Размещение плакатов формата А1 на внутренних стеклах витрины павильона",
                    "", "", "pending",
                    "",
                    "17.11.2026 10:30"
                ),
            ]
            conn.executemany(
                """INSERT INTO marketing_requests
                   (space_id, space_code, tenant_name, promo_type, title, date_range, description,
                    mockup_file_name, mockup_file_path, status, uk_feedback, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                demo_marketing,
            )

        # Демо-записи для товарооборота
        if conn.execute("SELECT COUNT(*) FROM tenant_turnovers").fetchone()[0] == 0:
            demo_turnovers = [
                (
                    "1_top_1", "1-01", "Кофейня «Бодрость»", "10.2026",
                    1850000, 55500, "Z_отчет_Октябрь_2026.pdf", "", "accepted", "03.11.2026 14:10"
                ),
                (
                    "2_top_1", "2-01", "Одежда «Стиль»", "10.2026",
                    2400000, 120000, "Справка_ОФД_Октябрь_2026.pdf", "", "submitted", "04.11.2026 16:45"
                ),
            ]
            conn.executemany(
                """INSERT INTO tenant_turnovers
                   (space_id, space_code, tenant_name, period, reported_revenue, calculated_fee,
                    report_file_name, report_file_path, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                demo_turnovers,
            )

        if conn.execute("SELECT COUNT(*) FROM spaces").fetchone()[0] == 0:
            initial_spaces = []
            sample_data = {
                "1_top_1": ("1-01", "Кофейня «Бодрость»", 42.0, 145000, "occupied", "Иванова Мария, +7 (904) 111-22-33", "Петров Сергей (куратор сети), +7 (904) 999-88-77", "Мокрая точка (подвод воды и канализации).", "№ 01-А/2026", "31.12.2026", "paid", 84.5, 40.0, 3420.0),
                "1_top_2": ("1-02", "", 55.0, 175000, "free", "", "", "Потенциальный арендатор: табачная лавка, звонили 10.11.", "", "", "paid", 0.0, 0.0, 0.0),
                "1_top_3": ("1-03", "Аптека «Здоровье»", 60.0, 190000, "occupied", "Смирнова Елена, +7 (922) 333-44-55", "Кузнецов Олег (терр. директор), +7 (922) 777-66-55", "Якорный арендатор, оплата всегда вовремя.", "№ 03-А/2025", "30.06.2027", "paid", 32.0, 16.0, 2150.0),
                "1_bot_1": ("1-04", "", 48.0, 150000, "free", "", "", "", "", "", "paid", 0.0, 0.0, 0.0),
                "1_bot_2": ("1-05", "Оптика «Взгляд»", 38.0, 125000, "reserved", "Волков Дмитрий, +7 (950) 444-11-22", "", "Ждем подписанный скан договора до пятницы.", "Проект № 05-А/2026", "01.12.2027", "unpaid", 8.0, 4.0, 610.0),
                "1_bot_3": ("1-06", "", 75.0, 220000, "free", "", "", "", "", "", "paid", 0.0, 0.0, 0.0),
                "2_top_1": ("2-01", "Одежда «Стиль»", 85.0, 160000, "occupied", "Морозова Анна, +7 (912) 888-00-11", "Белова Ольга (рег. директор), +7 (912) 888-00-99", "Просили рассмотреть скидку 10% на январь-февраль.", "№ 11-А/2026", "31.10.2026", "unpaid", 12.0, 7.0, 1890.0),
                "2_top_2": ("2-02", "", 64.0, 120000, "free", "", "", "", "", "", "paid", 0.0, 0.0, 0.0),
                "2_top_3": ("2-03", "", 64.0, 120000, "free", "", "", "", "", "", "paid", 0.0, 0.0, 0.0),
                "2_bot_1": ("2-04", "Книги и канцтовары", 50.0, 95000, "occupied", "Новиков Илья (ИП), +7 (963) 222-33-44", "", "", "№ 14-А/2026", "15.08.2027", "unpaid", 10.0, 5.0, 940.0),
                "2_bot_2": ("2-05", "", 45.0, 88000, "free", "", "", "", "", "", "paid", 0.0, 0.0, 0.0),
                "2_bot_3": ("2-06", "Фудкорт / Пекарня", 90.0, 180000, "reserved", "Зайцева Наталья, +7 (908) 555-66-77", "", "Требуется усиленная вытяжка, согласовано с главным инженером.", "Проект № 16-А/2026", "31.12.2027", "unpaid", 52.0, 28.0, 4100.0),
            }

            x_positions = [30, 215, 400]
            for floor in (1, 2):
                for idx, x in enumerate(x_positions, start=1):
                    top_id = f"{floor}_top_{idx}"
                    code, tenant, area, price, status, p_dir, a_dir, notes, c_num, c_end, pay_st, ph, pg, pe = sample_data[top_id]
                    initial_spaces.append((top_id, floor, code, tenant, area, price, status, x, 20, 170, 110, p_dir, a_dir, notes, c_num, c_end, "", "", pay_st, ph, pg, pe))

                    bot_id = f"{floor}_bot_{idx}"
                    code, tenant, area, price, status, p_dir, a_dir, notes, c_num, c_end, pay_st, ph, pg, pe = sample_data[bot_id]
                    initial_spaces.append((bot_id, floor, code, tenant, area, price, status, x, 230, 170, 110, p_dir, a_dir, notes, c_num, c_end, "", "", pay_st, ph, pg, pe))

            conn.executemany(
                "INSERT INTO spaces VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                initial_spaces,
            )

        if conn.execute("SELECT COUNT(*) FROM rent_payments").fetchone()[0] == 0:
            demo_history = [
                ("1_top_1", "08.2026", 145000, 1, 0, "03.08.2026", ""),
                ("1_top_1", "09.2026", 145000, 1, 0, "04.09.2026", ""),
                ("1_top_1", "10.2026", 145000, 1, 0, "02.10.2026", ""),
                ("1_top_1", "11.2026", 145000, 1, 0, "05.11.2026", ""),
                ("1_top_3", "08.2026", 190000, 1, 0, "04.08.2026", ""),
                ("1_top_3", "09.2026", 190000, 1, 1, "14.09.2026", "Задержка банковского перевода на 9 дней"),
                ("1_top_3", "10.2026", 190000, 1, 0, "03.10.2026", ""),
                ("1_top_3", "11.2026", 190000, 1, 0, "04.11.2026", ""),
                ("1_bot_2", "10.2026", 125000, 1, 0, "05.10.2026", ""),
                ("1_bot_2", "11.2026", 125000, 0, 0, "", "Ожидается платеж по договору"),
                ("2_top_1", "08.2026", 160000, 1, 0, "05.08.2026", ""),
                ("2_top_1", "09.2026", 160000, 1, 1, "18.09.2026", "Оплата поступила с просрочкой 13 дней"),
                ("2_top_1", "10.2026", 160000, 1, 1, "12.10.2026", "Оплата поступила с просрочкой 7 дней"),
                ("2_top_1", "11.2026", 160000, 0, 1, "", "Просрочка оплаты за текущий месяц"),
                ("2_bot_1", "09.2026", 95000, 1, 0, "04.09.2026", ""),
                ("2_bot_1", "10.2026", 95000, 1, 0, "05.10.2026", ""),
                ("2_bot_1", "11.2026", 95000, 0, 0, "", ""),
                ("2_bot_3", "11.2026", 180000, 0, 0, "", ""),
            ]
            conn.executemany(
                "INSERT OR IGNORE INTO rent_payments (space_id, period, amount, is_paid, was_overdue, paid_date, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
                demo_history,
            )

        # Демонстрационные формы на оплату (для наглядности сразу после запуска)
        if conn.execute("SELECT COUNT(*) FROM payment_requests").fetchone()[0] == 0:
            demo_bills = [
                (
                    "2_top_1", "2-01", "Одежда «Стиль»", "11.2026",
                    "Счет-акт за аренду и коммуналку (Ноябрь 2026)", 168450, "10.11.2026",
                    "", "", "", "", "", "awaiting_payment", 0, "01.11.2026 10:00", "", ""
                ),
                (
                    "2_bot_1", "2-04", "Книги и канцтовары", "11.2026",
                    "Счет-акт № 114 за аренду (Ноябрь 2026)", 95000, "25.11.2026",
                    "", "", "", "", "", "awaiting_payment", 0, "02.11.2026 11:30", "", ""
                ),
            ]
            conn.executemany(
                """INSERT INTO payment_requests
                   (space_id, space_code, tenant_name, period, title, amount, due_date,
                    bill_file_name, bill_file_path, receipt_file_name, receipt_file_path,
                    tenant_comment, status, was_overdue, created_at, paid_uploaded_at, closed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                demo_bills,
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
    payment_status: str = "paid",
    deposit_required: int = 0,
    deposit_paid: int = 0,
    penalty_rate: float = 0.1,
    turnover_percent: float = 0.0,
):
    with get_connection() as conn:
        conn.execute(
            """UPDATE spaces
               SET status = ?, tenant = ?, price = ?, point_director = ?, area_director = ?,
                   internal_notes = ?, payment_status = ?, deposit_required = ?, deposit_paid = ?,
                   penalty_rate = ?, turnover_percent = ?
               WHERE id = ?""",
            (
                status,
                tenant.strip(),
                price,
                point_director.strip(),
                area_director.strip(),
                internal_notes.strip(),
                payment_status,
                deposit_required,
                deposit_paid,
                penalty_rate,
                turnover_percent,
                space_id,
            ),
        )
    sync_current_month_payment(space_id, payment_status == "paid")


def sync_current_month_payment(space_id: str, is_paid: bool, was_overdue: bool | None = None):
    space = get_space_by_id(space_id)
    if not space:
        return
    period = current_month_str()
    today_str = datetime.now().strftime("%d.%m.%Y") if is_paid else ""
    new_status = "paid" if is_paid else "unpaid"

    with get_connection() as conn:
        conn.execute("UPDATE spaces SET payment_status = ? WHERE id = ?", (new_status, space_id))
        existing = conn.execute(
            "SELECT * FROM rent_payments WHERE space_id = ? AND period = ?",
            (space_id, period),
        ).fetchone()

        if existing:
            overdue_flag = int(was_overdue) if was_overdue is not None else existing["was_overdue"]
            paid_dt = (existing["paid_date"] or today_str) if is_paid else ""
            conn.execute(
                """UPDATE rent_payments
                   SET is_paid = ?, was_overdue = ?, paid_date = ?, amount = ?
                   WHERE id = ?""",
                (1 if is_paid else 0, overdue_flag, paid_dt, space["price"], existing["id"]),
            )
        else:
            overdue_flag = int(was_overdue) if was_overdue is not None else 0
            conn.execute(
                """INSERT INTO rent_payments (space_id, period, amount, is_paid, was_overdue, paid_date, note)
                   VALUES (?, ?, ?, ?, ?, ?, '')""",
                (space_id, period, space["price"], 1 if is_paid else 0, overdue_flag, today_str),
            )


def get_rent_payments(space_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM rent_payments WHERE space_id = ? ORDER BY substr(period, 4, 4) DESC, substr(period, 1, 2) DESC, id DESC",
            (space_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def save_rent_payment_record(
    space_id: str,
    period: str,
    amount: int,
    is_paid: bool,
    was_overdue: bool,
    paid_date: str = "",
    note: str = "",
):
    period_clean = period.strip() or current_month_str()
    p_date = paid_date.strip() if is_paid else ""
    if is_paid and not p_date:
        p_date = datetime.now().strftime("%d.%m.%Y")

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO rent_payments (space_id, period, amount, is_paid, was_overdue, paid_date, note)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(space_id, period) DO UPDATE SET
                 amount = excluded.amount,
                 is_paid = excluded.is_paid,
                 was_overdue = excluded.was_overdue,
                 paid_date = excluded.paid_date,
                 note = excluded.note""",
            (space_id, period_clean, amount, 1 if is_paid else 0, 1 if was_overdue else 0, p_date, note.strip()),
        )
        if period_clean == current_month_str():
            conn.execute(
                "UPDATE spaces SET payment_status = ? WHERE id = ?",
                ("paid" if is_paid else "unpaid", space_id),
            )


def get_overdue_space_ids() -> set[str]:
    """Возвращает ID павильонов с активной просрочкой в истории или в открытых формах на оплату"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT space_id FROM rent_payments WHERE is_paid = 0 AND was_overdue = 1"
        ).fetchall()
        overdue = {r["space_id"] for r in rows}

        open_reqs = conn.execute(
            "SELECT space_id, due_date FROM payment_requests WHERE status != 'closed'"
        ).fetchall()
        for req in open_reqs:
            if is_due_date_passed(req["due_date"]):
                overdue.add(req["space_id"])
        return overdue


def get_payment_history_stats(space_id: str) -> tuple[int, int]:
    with get_connection() as conn:
        unpaid_ov = conn.execute(
            "SELECT COUNT(*) FROM rent_payments WHERE space_id = ? AND is_paid = 0 AND was_overdue = 1",
            (space_id,),
        ).fetchone()[0]
        paid_ov = conn.execute(
            "SELECT COUNT(*) FROM rent_payments WHERE space_id = ? AND is_paid = 1 AND was_overdue = 1",
            (space_id,),
        ).fetchone()[0]
        return unpaid_ov, paid_ov


# --- ФОРМЫ НА ОПЛАТУ (СЧЕТ/АКТ -> ПЛАТЕЖКА -> ЗАКРЫТИЕ) ---

def create_payment_request(
    space_id: str,
    period: str,
    title: str,
    amount: int,
    due_date: str,
    bill_file_name: str = "",
    bill_file_path: str = "",
):
    space = get_space_by_id(space_id)
    if not space:
        return
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    period_val = period.strip() or current_month_str()
    title_val = title.strip() or f"Акт/счет на оплату за {period_val}"
    due_val = due_date.strip() or datetime.now().strftime("%d.%m.%Y")

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO payment_requests
               (space_id, space_code, tenant_name, period, title, amount, due_date,
                bill_file_name, bill_file_path, status, was_overdue, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'awaiting_payment', 0, ?)""",
            (
                space_id,
                space["code"],
                space["tenant"] or "Без названия",
                period_val,
                title_val,
                int(amount or space["price"]),
                due_val,
                bill_file_name,
                bill_file_path,
                now,
            ),
        )
    # Если выставлен новый акт на текущий месяц, статус месяца переходит в "Не оплачено"
    if period_val == current_month_str():
        sync_current_month_payment(space_id, False)


def attach_payment_receipt(
    request_id: int,
    receipt_file_name: str,
    receipt_file_path: str,
    tenant_comment: str = "",
):
    if not receipt_file_name:
        return
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_connection() as conn:
        conn.execute(
            """UPDATE payment_requests
               SET receipt_file_name = ?, receipt_file_path = ?, tenant_comment = ?,
                   status = 'under_review', paid_uploaded_at = ?
               WHERE id = ?""",
            (receipt_file_name, receipt_file_path, tenant_comment.strip(), now, request_id),
        )


def return_payment_request_to_tenant(request_id: int):
    """УК возвращает форму арендатору на доработку (если платежка неверная)"""
    with get_connection() as conn:
        conn.execute(
            "UPDATE payment_requests SET status = 'awaiting_payment' WHERE id = ?",
            (request_id,),
        )


def close_payment_request(request_id: int, force_overdue: bool | None = None):
    """УК проверяет платежку и закрывает форму как оплаченную с фиксацией возможной просрочки"""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,)).fetchone()
        if not row:
            return
        req = dict(row)
        overdue = force_overdue if force_overdue is not None else is_due_date_passed(req["due_date"])
        now = datetime.now().strftime("%d.%m.%Y %H:%M")

        conn.execute(
            """UPDATE payment_requests
               SET status = 'closed', was_overdue = ?, closed_at = ?
               WHERE id = ?""",
            (1 if overdue else 0, now, request_id),
        )

    note_text = f"Закрыто по форме №{request_id}" + (" (оплата после срока)" if overdue else "")
    save_rent_payment_record(
        space_id=req["space_id"],
        period=req["period"],
        amount=req["amount"],
        is_paid=True,
        was_overdue=overdue,
        note=note_text,
    )


def get_payment_requests(space_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if space_id:
            rows = conn.execute(
                """SELECT * FROM payment_requests
                   WHERE space_id = ?
                   ORDER BY CASE status WHEN 'awaiting_payment' THEN 1 WHEN 'under_review' THEN 2 ELSE 3 END, id DESC""",
                (space_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM payment_requests
                   ORDER BY CASE status WHEN 'under_review' THEN 1 WHEN 'awaiting_payment' THEN 2 ELSE 3 END, id DESC"""
            ).fetchall()
        return [dict(row) for row in rows]


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


# --- ПОКАЗАНИЯ СЧЕТЧИКОВ (ХВС, ГВС, ЭЛЕКТРОЭНЕРГИЯ) ---

def submit_meter_reading(
    space_id: str,
    period: str,
    curr_hvs: float,
    curr_gvs: float,
    curr_elec: float,
) -> tuple[bool, str]:
    space = get_space_by_id(space_id)
    if not space:
        return False, "Помещение не найдено"

    prev_h = float(space.get("prev_hvs") or 0)
    prev_g = float(space.get("prev_gvs") or 0)
    prev_e = float(space.get("prev_elec") or 0)

    if curr_hvs < prev_h or curr_gvs < prev_g or curr_elec < prev_e:
        return False, "Текущие показания не могут быть меньше предыдущих"

    diff_h = curr_hvs - prev_h
    diff_g = curr_gvs - prev_g
    diff_e = curr_elec - prev_e
    total_cost = round(diff_h * HVS_TARIFF + diff_g * GVS_TARIFF + diff_e * ELEC_TARIFF)
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO meter_readings
               (space_id, space_code, tenant_name, period, prev_hvs, curr_hvs, prev_gvs, curr_gvs, prev_elec, curr_elec, total_cost, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?)""",
            (
                space_id,
                space["code"],
                space["tenant"] or "Без названия",
                period.strip() or "Текущий месяц",
                prev_h,
                curr_hvs,
                prev_g,
                curr_gvs,
                prev_e,
                curr_elec,
                total_cost,
                now,
            ),
        )
    return True, f"Показания переданы! Переменная часть аренды: {total_cost:,} ₽".replace(",", " ")


def get_meter_readings(space_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if space_id:
            rows = conn.execute(
                "SELECT * FROM meter_readings WHERE space_id = ? ORDER BY id DESC", (space_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM meter_readings ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]


def accept_meter_reading(reading_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM meter_readings WHERE id = ?", (reading_id,)).fetchone()
        if not row:
            return
        conn.execute("UPDATE meter_readings SET status = 'accepted' WHERE id = ?", (reading_id,))
        conn.execute(
            "UPDATE spaces SET prev_hvs = ?, prev_gvs = ?, prev_elec = ? WHERE id = ?",
            (row["curr_hvs"], row["curr_gvs"], row["curr_elec"], row["space_id"]),
        )


# --- ЗАКРЫВАЮЩИЕ ДОКУМЕНТЫ И ПЛАТЕЖКИ ---

def add_financial_doc(
    space_id: str,
    doc_type: str,
    title: str,
    file_name: str,
    file_path: str,
    uploaded_by: str,
):
    space = get_space_by_id(space_id)
    if not space or not file_name:
        return
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO financial_docs
               (space_id, space_code, tenant_name, doc_type, title, file_name, file_path, uploaded_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                space_id,
                space["code"],
                space["tenant"] or "Без названия",
                doc_type,
                title.strip() or file_name,
                file_name,
                file_path,
                uploaded_by,
                now,
            ),
        )


def get_financial_docs(space_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if space_id:
            rows = conn.execute(
                "SELECT * FROM financial_docs WHERE space_id = ? ORDER BY id DESC", (space_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM financial_docs ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]


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


# --- РАСЧЕТ ПЕНЕЙ И ПРОСРОЧЕК ---

def calculate_overdue_penalty(amount: int, due_date_str: str, rate_percent: float = 0.1) -> tuple[int, int]:
    """Возвращает (кол-во дней просрочки, сумма пени в рублях)"""
    if not due_date_str or not due_date_str.strip() or amount <= 0:
        return 0, 0
    try:
        due_dt = datetime.strptime(due_date_str.strip(), "%d.%m.%Y").date()
        today = datetime.now().date()
        delta_days = (today - due_dt).days
        if delta_days <= 0:
            return 0, 0
        rate = max(0.0, float(rate_percent or 0.1))
        penalty = int(round(amount * (rate / 100.0) * delta_days))
        return delta_days, penalty
    except ValueError:
        return 0, 0


# --- БЛОК 1: ЭЛЕКТРОННЫЕ ПРОПУСКА НА ВВОЗ/ВЫВОЗ И НОЧНЫЕ РАБОТЫ ---

def create_access_pass(
    space_id: str,
    pass_type: str,
    work_date: str,
    time_window: str,
    vehicle_info: str,
    workers_list: str,
    description: str,
):
    space = get_space_by_id(space_id)
    if not space:
        return
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO access_passes
               (space_id, space_code, tenant_name, pass_type, work_date, time_window,
                vehicle_info, workers_list, description, status, uk_comment, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', ?)""",
            (
                space_id,
                space["code"],
                space["tenant"] or "Без названия",
                pass_type,
                work_date.strip(),
                time_window.strip(),
                vehicle_info.strip(),
                workers_list.strip(),
                description.strip(),
                now,
            ),
        )


def get_access_passes(space_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if space_id:
            rows = conn.execute(
                """SELECT * FROM access_passes
                   WHERE space_id = ?
                   ORDER BY CASE status WHEN 'pending' THEN 1 WHEN 'approved' THEN 2 ELSE 3 END, id DESC""",
                (space_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM access_passes
                   ORDER BY CASE status WHEN 'pending' THEN 1 WHEN 'approved' THEN 2 ELSE 3 END, id DESC"""
            ).fetchall()
        return [dict(row) for row in rows]


def update_access_pass_status(pass_id: int, status: str, uk_comment: str = ""):
    with get_connection() as conn:
        conn.execute(
            "UPDATE access_passes SET status = ?, uk_comment = ? WHERE id = ?",
            (status, uk_comment.strip(), pass_id),
        )


# --- БЛОК 1: ЖУРНАЛ ПРОВЕРОК И ПРЕДПИСАНИЙ (ПБ, СЭС, ОХРАНА ТРУДА) ---

def create_inspection(
    space_id: str,
    category: str,
    title: str,
    deadline: str,
    uk_photo_name: str = "",
    uk_photo_path: str = "",
):
    space = get_space_by_id(space_id)
    if not space or not title.strip():
        return
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO inspections
               (space_id, space_code, tenant_name, category, title, deadline, status,
                uk_photo_path, uk_photo_name, tenant_report, tenant_photo_path, tenant_photo_name, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, '', '', '', ?)""",
            (
                space_id,
                space["code"],
                space["tenant"] or "Без названия",
                category,
                title.strip(),
                deadline.strip(),
                uk_photo_path,
                uk_photo_name,
                now,
            ),
        )


def get_inspections(space_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if space_id:
            rows = conn.execute(
                """SELECT * FROM inspections
                   WHERE space_id = ?
                   ORDER BY CASE status WHEN 'open' THEN 1 WHEN 'review' THEN 2 ELSE 3 END, id DESC""",
                (space_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM inspections
                   ORDER BY CASE status WHEN 'review' THEN 1 WHEN 'open' THEN 2 ELSE 3 END, id DESC"""
            ).fetchall()
        return [dict(row) for row in rows]


def submit_inspection_report(
    inspection_id: int,
    report: str,
    photo_name: str = "",
    photo_path: str = "",
):
    with get_connection() as conn:
        conn.execute(
            """UPDATE inspections
               SET tenant_report = ?, tenant_photo_name = ?, tenant_photo_path = ?, status = 'review'
               WHERE id = ?""",
            (report.strip(), photo_name, photo_path, inspection_id),
        )


def resolve_inspection(inspection_id: int):
    with get_connection() as conn:
        conn.execute("UPDATE inspections SET status = 'resolved' WHERE id = ?", (inspection_id,))


# --- БЛОК 3: МАРКЕТИНГ И СОГЛАСОВАНИЕ АКЦИЙ / ВЫВЕСОК ---

def create_marketing_request(
    space_id: str,
    promo_type: str,
    title: str,
    date_range: str,
    description: str,
    mockup_file_name: str = "",
    mockup_file_path: str = "",
):
    space = get_space_by_id(space_id)
    if not space or not title.strip():
        return
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO marketing_requests
               (space_id, space_code, tenant_name, promo_type, title, date_range, description,
                mockup_file_name, mockup_file_path, status, uk_feedback, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', ?)""",
            (
                space_id,
                space["code"],
                space["tenant"] or "Без названия",
                promo_type,
                title.strip(),
                date_range.strip(),
                description.strip(),
                mockup_file_name,
                mockup_file_path,
                now,
            ),
        )


def get_marketing_requests(space_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if space_id:
            rows = conn.execute(
                """SELECT * FROM marketing_requests
                   WHERE space_id = ?
                   ORDER BY CASE status WHEN 'pending' THEN 1 WHEN 'revision' THEN 2 ELSE 3 END, id DESC""",
                (space_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM marketing_requests
                   ORDER BY CASE status WHEN 'pending' THEN 1 WHEN 'revision' THEN 2 ELSE 3 END, id DESC"""
            ).fetchall()
        return [dict(row) for row in rows]


def update_marketing_status(request_id: int, status: str, uk_feedback: str = ""):
    with get_connection() as conn:
        conn.execute(
            "UPDATE marketing_requests SET status = ?, uk_feedback = ? WHERE id = ?",
            (status, uk_feedback.strip(), request_id),
        )


# --- БЛОК 3: ТОВАРООБОРОТ АРЕНДАТОРОВ (% ОТ ВЫРУЧКИ) ---

def submit_turnover_report(
    space_id: str,
    period: str,
    reported_revenue: int,
    report_file_name: str = "",
    report_file_path: str = "",
):
    space = get_space_by_id(space_id)
    if not space:
        return
    t_percent = float(space.get("turnover_percent") or 0.0)
    calculated_fee = int(round(reported_revenue * (t_percent / 100.0)))
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO tenant_turnovers
               (space_id, space_code, tenant_name, period, reported_revenue, calculated_fee,
                report_file_name, report_file_path, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'submitted', ?)""",
            (
                space_id,
                space["code"],
                space["tenant"] or "Без названия",
                period.strip() or current_month_str(),
                int(reported_revenue),
                calculated_fee,
                report_file_name,
                report_file_path,
                now,
            ),
        )


def get_turnovers(space_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if space_id:
            rows = conn.execute(
                "SELECT * FROM tenant_turnovers WHERE space_id = ? ORDER BY id DESC",
                (space_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM tenant_turnovers
                   ORDER BY CASE status WHEN 'submitted' THEN 1 ELSE 2 END, id DESC"""
            ).fetchall()
        return [dict(row) for row in rows]


def get_latest_turnover(space_id: str, period: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT * FROM tenant_turnovers
               WHERE space_id = ? AND period = ?
               ORDER BY CASE status WHEN 'accepted' THEN 1 ELSE 2 END, id DESC LIMIT 1""",
            (space_id, period.strip()),
        ).fetchone()
        return dict(row) if row else None


def update_turnover_status(turnover_id: int, status: str):
    with get_connection() as conn:
        conn.execute("UPDATE tenant_turnovers SET status = ? WHERE id = ?", (status, turnover_id))


# --- АВТОРАСЧЕТ СЧЕТА-АКТА (СТАВКА + СЧЕТЧИКИ + % С ОБОРОТА) ---

def get_billing_calculation(space_id: str, period: str) -> dict:
    space = get_space_by_id(space_id)
    if not space:
        return {"total": 0, "title": "", "desc": "", "base": 0, "meter": 0, "turnover": 0}
    base_price = space["price"]

    with get_connection() as conn:
        row_mr = conn.execute(
            """SELECT total_cost, status FROM meter_readings
               WHERE space_id = ? AND period = ?
               ORDER BY CASE status WHEN 'accepted' THEN 1 ELSE 2 END, id DESC LIMIT 1""",
            (space_id, period),
        ).fetchone()
        meter_cost = row_mr["total_cost"] if row_mr else 0

        row_to = conn.execute(
            """SELECT calculated_fee, status FROM tenant_turnovers
               WHERE space_id = ? AND period = ?
               ORDER BY CASE status WHEN 'accepted' THEN 1 ELSE 2 END, id DESC LIMIT 1""",
            (space_id, period),
        ).fetchone()
        turnover_fee = row_to["calculated_fee"] if row_to else 0

    total = base_price + meter_cost + turnover_fee
    parts = [f"аренда {base_price:,} ₽".replace(",", " ")]
    if meter_cost:
        parts.append(f"коммунальные услуги {meter_cost:,} ₽".replace(",", " "))
    if turnover_fee:
        parts.append(f"% с оборота {turnover_fee:,} ₽".replace(",", " "))

    title = f"Акт за {period}: " + " + ".join(parts)
    desc = " + ".join(parts)
    return {
        "total": total,
        "title": title,
        "desc": desc,
        "base": base_price,
        "meter": meter_cost,
        "turnover": turnover_fee,
    }


# --- ВЫГРУЗКА РЕЕСТРОВ В CSV (EXCEL-СОВМЕСТИМЫЙ UTF-8-SIG) ---

def export_financial_summary_csv() -> tuple[str, str]:
    exports_dir = os.path.join(UPLOAD_DIR, "exports")
    os.makedirs(exports_dir, exist_ok=True)
    fname = f"Ведомость_оплат_и_долгов_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    fpath = os.path.join(exports_dir, fname)

    spaces = get_all_spaces()
    pay_requests = get_payment_requests()

    with open(fpath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "Павильон", "Арендатор", "Этаж", "Площадь (м²)", "Базовая ставка (₽/мес)",
            "Статус текущего месяца", "Депозит по договору (₽)", "Депозит внесен (₽)",
            "% от оборота", "Открытые счета (₽)", "Просроченные счета (₽)", "Начисленные пени (₽)",
            "Директор точки"
        ])
        for s in spaces:
            if s["status"] == "free":
                continue
            sp_reqs = [r for r in pay_requests if r["space_id"] == s["id"] and r["status"] != "closed"]
            open_sum = sum(r["amount"] for r in sp_reqs)
            overdue_sum = 0
            penalty_sum = 0
            p_rate = float(s.get("penalty_rate") or 0.1)
            for r in sp_reqs:
                if is_due_date_passed(r["due_date"]):
                    overdue_sum += r["amount"]
                    _, p_val = calculate_overdue_penalty(r["amount"], r["due_date"], p_rate)
                    penalty_sum += p_val

            pay_st = "Оплачено" if s.get("payment_status") == "paid" else "Не оплачено"
            contact = s.get("point_director") or ""
            writer.writerow([
                s["code"], s["tenant"] or "Без названия", s["floor"], s["area"], s["price"],
                pay_st, s.get("deposit_required") or 0, s.get("deposit_paid") or 0,
                f"{s.get('turnover_percent') or 0.0}%", open_sum, overdue_sum, penalty_sum, contact
            ])
    return fpath, fname


def export_meter_readings_csv() -> tuple[str, str]:
    exports_dir = os.path.join(UPLOAD_DIR, "exports")
    os.makedirs(exports_dir, exist_ok=True)
    fname = f"Реестр_показаний_счетчиков_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    fpath = os.path.join(exports_dir, fname)

    readings = get_meter_readings()
    with open(fpath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([
            "ID", "Павильон", "Арендатор", "Период",
            "ХВС нач (м³)", "ХВС тек (м³)", "ХВС расход (м³)",
            "ГВС нач (м³)", "ГВС тек (м³)", "ГВС расход (м³)",
            "Э/Э нач (кВт·ч)", "Э/Э тек (кВт·ч)", "Э/Э расход (кВт·ч)",
            "Начислено (₽)", "Статус", "Дата передачи"
        ])
        for r in readings:
            diff_h = round(r["curr_hvs"] - r["prev_hvs"], 2)
            diff_g = round(r["curr_gvs"] - r["prev_gvs"], 2)
            diff_e = round(r["curr_elec"] - r["prev_elec"], 2)
            st_text = "Принято УК" if r["status"] == "accepted" else "На проверке"
            writer.writerow([
                r["id"], r["space_code"], r["tenant_name"], r["period"],
                r["prev_hvs"], r["curr_hvs"], diff_h,
                r["prev_gvs"], r["curr_gvs"], diff_g,
                r["prev_elec"], r["curr_elec"], diff_e,
                r["total_cost"], st_text, r["created_at"]
            ])
    return fpath, fname


def get_sync_signature() -> tuple:
    with get_connection() as conn:
        tickets_sig = conn.execute(
            "SELECT COUNT(*), COALESCE(GROUP_CONCAT(id || ':' || status), '') FROM tickets"
        ).fetchone()
        spaces_sig = conn.execute(
            """SELECT COALESCE(GROUP_CONCAT(
                id || ':' || status || ':' || COALESCE(tenant, '') || ':' || price || ':' ||
                COALESCE(payment_status, '') || ':' || COALESCE(contract_number, '') || ':' ||
                COALESCE(contract_file_name, '') || ':' || prev_hvs || ':' || prev_gvs || ':' || prev_elec || ':' ||
                COALESCE(deposit_required, 0) || ':' || COALESCE(deposit_paid, 0) || ':' ||
                COALESCE(penalty_rate, 0) || ':' || COALESCE(turnover_percent, 0)
            ), '') FROM spaces"""
        ).fetchone()
        msgs_sig = conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM messages"
        ).fetchone()
        fin_sig = conn.execute(
            """SELECT
                (SELECT COUNT(*) || ':' || COALESCE(GROUP_CONCAT(id || ':' || status), '') FROM meter_readings),
                (SELECT COUNT(*) FROM financial_docs),
                (SELECT COALESCE(GROUP_CONCAT(id || ':' || is_paid || ':' || was_overdue), '') FROM rent_payments),
                (SELECT COUNT(*) || ':' || COALESCE(GROUP_CONCAT(id || ':' || status || ':' || receipt_file_name), '') FROM payment_requests)
            """
        ).fetchone()
        passes_sig = conn.execute(
            "SELECT COUNT(*) || ':' || COALESCE(GROUP_CONCAT(id || ':' || status || ':' || COALESCE(uk_comment, '')), '') FROM access_passes"
        ).fetchone()[0]
        inspections_sig = conn.execute(
            "SELECT COUNT(*) || ':' || COALESCE(GROUP_CONCAT(id || ':' || status || ':' || COALESCE(tenant_report, '')), '') FROM inspections"
        ).fetchone()[0]
        marketing_sig = conn.execute(
            "SELECT COUNT(*) || ':' || COALESCE(GROUP_CONCAT(id || ':' || status || ':' || COALESCE(uk_feedback, '')), '') FROM marketing_requests"
        ).fetchone()[0]
        turnovers_sig = conn.execute(
            "SELECT COUNT(*) || ':' || COALESCE(GROUP_CONCAT(id || ':' || status), '') FROM tenant_turnovers"
        ).fetchone()[0]

        return (
            tickets_sig[0],
            tickets_sig[1],
            spaces_sig[0],
            msgs_sig[0],
            msgs_sig[1],
            fin_sig[0],
            fin_sig[1],
            fin_sig[2],
            fin_sig[3],
            passes_sig,
            inspections_sig,
            marketing_sig,
            turnovers_sig,
        )