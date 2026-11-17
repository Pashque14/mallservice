import os
import time
from nicegui import app, events, ui
import database as db

db.init_db()

STATUS_META = {
    "free": {
        "label": "Свободно",
        "fill": "#ecfdf5",
        "border": "#10b981",
        "text": "#065f46",
        "accent": "#059669",
        "badge": "positive",
    },
    "reserved": {
        "label": "Бронь",
        "fill": "#fffbeb",
        "border": "#f59e0b",
        "text": "#92400e",
        "accent": "#d97706",
        "badge": "warning",
    },
    "occupied": {
        "label": "Занято",
        "fill": "#f8fafc",
        "border": "#cbd5e1",
        "text": "#1e293b",
        "accent": "#64748b",
        "badge": "grey",
    },
}

TICKET_META = {
    "new": {"label": "Новая", "badge": "red"},
    "in_progress": {"label": "В работе", "badge": "orange"},
    "done": {"label": "Выполнено", "badge": "green"},
}

TICKET_CATEGORIES = {
    "plumbing": "Сантехника / вода",
    "electric": "Электрика / освещение",
    "hvac": "Вентиляция / кондиционер",
    "cleaning": "Клининг / охрана",
    "other": "Общий ремонт / прочее",
}

TICKET_PRIORITIES = {
    "normal": {"label": "Плановая", "badge": "blue-grey"},
    "urgent": {"label": "Аварийная", "badge": "red"},
}


def inject_global_styles():
    ui.add_head_html("""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
            background-color: #f4f6f9 !important;
            color: #1e293b;
        }
        .tabular-nums {
            font-variant-numeric: tabular-nums;
        }
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: #f1f5f9;
        }
        ::-webkit-scrollbar-thumb {
            background: #cbd5e1;
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #94a3b8;
        }
    </style>
    """)


def logout():
    app.storage.user.clear()
    ui.navigate.to("/login")


async def save_uploaded_file(e: events.UploadEventArguments) -> tuple[str, str]:
    """Сохраняет загруженный файл в папку uploads/"""
    file_obj = getattr(e, "file", e)
    safe_name = os.path.basename(file_obj.name)
    stored_name = f"{int(time.time())}_{safe_name}"
    full_path = os.path.join(db.UPLOAD_DIR, stored_name)

    if hasattr(file_obj, "save"):
        await file_obj.save(full_path)
    else:
        with open(full_path, "wb") as f:
            f.write(file_obj.content.read())

    return safe_name, full_path


def render_empty_state(icon: str, title: str, description: str):
    """Центрированный блок пустого состояния в стиле PropTech SaaS"""
    with ui.column().classes("w-full py-12 items-center justify-center text-center gap-2"):
        with ui.element("div").classes("w-14 h-14 rounded-full bg-slate-100 flex items-center justify-center mb-1 text-slate-400"):
            ui.icon(icon, size="30px")
        ui.label(title).classes("text-base font-semibold text-slate-800")
        ui.label(description).classes("text-sm text-slate-500 max-w-md")


def open_photo_preview(photo_path: str, photo_name: str):
    """Модальное окно для быстрого просмотра фото поломки"""
    with ui.dialog() as dialog, ui.card().classes("max-w-2xl w-full p-5 gap-3 bg-white border border-slate-200/90 shadow-xl rounded-2xl").props("flat"):
        with ui.row().classes("w-full justify-between items-center"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("photo_camera", size="sm").classes("text-slate-600")
                ui.label(f"Фотофиксация: {photo_name}").classes("font-bold text-slate-800 text-base")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense text-color=slate-500")

        ext = os.path.splitext(photo_name)[1].lower()
        if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            ui.image(photo_path).classes("w-full max-h-[500px] object-contain rounded-xl border border-slate-200 bg-slate-50")
        else:
            ui.label("Предпросмотр доступен только для изображений. Вы можете скачать файл:").classes("text-sm text-slate-600")

        with ui.row().classes("w-full justify-end gap-2 pt-2 border-t border-slate-100"):
            ui.button("Скачать файл", icon="download", on_click=lambda: ui.download(photo_path, photo_name)).props("outline dense")
            ui.button("Закрыть", on_click=dialog.close).props("dense color=primary")
    dialog.open()


def open_contract_dialog(space: dict, is_landlord: bool, on_saved=None):
    """Модальное окно договора: для свободных помещений — шаблон, для занятых/брони — просмотр и загрузка"""
    is_free = space["status"] == "free"

    with ui.dialog() as dialog, ui.card().classes("max-w-2xl w-full p-6 gap-4 bg-white border border-slate-200/90 shadow-xl rounded-2xl").props("flat"):
        with ui.row().classes("w-full justify-between items-center"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("description", size="sm").classes("text-indigo-600")
                title = (
                    f"Шаблон договора аренды • Павильон {space['code']}"
                    if is_free
                    else f"Договор аренды • Павильон {space['code']}"
                )
                ui.label(title).classes("text-lg font-bold text-slate-800")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense text-color=slate-500")

        ui.separator().classes("bg-slate-200/70")

        if is_free:
            ui.label("Помещение свободно. Ниже представлен типовой шаблон договора с подставленными параметрами павильона:").classes("text-sm text-slate-600")

            template_preview = (
                f"ТИПОВОЙ ДОГОВОР АРЕНДЫ НЕЖИЛОГО ПОМЕЩЕНИЯ № ___/2026\n\n"
                f"Объект аренды: Павильон {space['code']}, {space['floor']} этаж ТЦ\n"
                f"Общая площадь помещения: {space['area']} м²\n"
                f"Базовая арендная ставка: {space['price']:,} ₽/мес (вкл. НДС / УСН)\n"
                f"-------------------------------------------------------------------\n"
                f"1. Арендодатель передает, а Арендатор принимает во временное владение и пользование "
                f"указанное нежилое помещение для осуществления коммерческой деятельности.\n"
                f"2. Оплата производится ежемесячно авансом не позднее 5-го числа расчетного месяца.\n"
                f"3. Коммунальные платежи (электроэнергия, ХВС/ГВС) оплачиваются отдельно по приборам учета.\n"
                f"4. Передача помещения оформляется Актом приема-передачи в день подписания договора."
            ).replace(",", " ")

            ui.textarea(value=template_preview).classes("w-full font-mono text-xs bg-slate-50 border-slate-200 rounded-lg").props("readonly rows=11 outlined")

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                if os.path.exists(db.TEMPLATE_CONTRACT_PATH):
                    ui.button(
                        "Скачать файл шаблона (.txt)",
                        icon="download",
                        on_click=lambda: ui.download(db.TEMPLATE_CONTRACT_PATH, f"Шаблон_договора_{space['code']}.txt"),
                    ).props("outline dense")
                ui.button("Закрыть", on_click=dialog.close).props("dense color=primary")

        else:
            uploaded_contract = {"data": None}

            with ui.row().classes("w-full gap-4 bg-slate-50 p-3.5 rounded-xl border border-slate-200/80 items-center"):
                with ui.column().classes("gap-0.5"):
                    ui.label("Арендатор / Бренд").classes("text-xs text-slate-400 uppercase font-semibold")
                    ui.label(space["tenant"] or "Не указан").classes("font-bold text-slate-800")
                ui.space()
                with ui.column().classes("items-end gap-0.5"):
                    ui.label("Параметры лота").classes("text-xs text-slate-400 uppercase font-semibold")
                    rent_str = f"{space['price']:,} ₽/мес".replace(",", " ")
                    ui.label(f"{space['area']} м² • {rent_str}").classes("text-sm font-semibold text-slate-700 tabular-nums")

            if is_landlord:
                num_input = ui.input(
                    label="Номер договора",
                    value=space.get("contract_number") or "",
                    placeholder="Например: № 01-А/2026",
                ).classes("w-full").props("outlined dense")

                end_input = ui.input(
                    label="Срок действия договора (до)",
                    value=space.get("contract_end_date") or "",
                    placeholder="Например: 31.12.2026",
                ).classes("w-full").props("outlined dense")

                @ui.refreshable
                def current_file_box():
                    fname = space.get("contract_file_name") or ""
                    fpath = space.get("contract_file_path") or ""
                    if uploaded_contract["data"]:
                        ui.badge(f"Новый файл готов к сохранению: {uploaded_contract['data'][0]}", color="green")
                    elif fname and os.path.exists(fpath):
                        with ui.row().classes("w-full items-center justify-between p-3 bg-indigo-50/60 border border-indigo-200 rounded-xl"):
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("description", color="primary")
                                ui.label(fname).classes("text-sm font-medium text-slate-800")
                            ui.button(
                                "Скачать файл",
                                icon="download",
                                on_click=lambda: ui.download(fpath, fname),
                            ).props("dense flat color=primary")
                    else:
                        ui.label("Электронный скан договора еще не прикреплен.").classes("text-xs text-slate-400")

                current_file_box()

                async def on_contract_upload(e: events.UploadEventArguments):
                    c_name, c_path = await save_uploaded_file(e)
                    uploaded_contract["data"] = (c_name, c_path)
                    current_file_box.refresh()
                    ui.notify(f"Файл договора «{c_name}» загружен", type="info")

                ui.upload(
                    label="Прикрепить файл договора (PDF, DOCX, скан)",
                    auto_upload=True,
                    on_upload=on_contract_upload,
                ).classes("w-full").props("flat bordered")

                def save_contract():
                    if uploaded_contract["data"]:
                        db.update_space_contract(
                            space["id"],
                            num_input.value or "",
                            end_input.value or "",
                            uploaded_contract["data"][0],
                            uploaded_contract["data"][1],
                        )
                    else:
                        db.update_space_contract(
                            space["id"],
                            num_input.value or "",
                            end_input.value or "",
                        )
                    ui.notify("Данные договора сохранены", type="positive")
                    if on_saved:
                        on_saved()
                    dialog.close()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Отмена", on_click=dialog.close).props("flat dense")
                    ui.button("Сохранить договор", icon="save", on_click=save_contract).props("dense color=primary")

            else:
                c_num = space.get("contract_number") or "Не указан"
                c_end = space.get("contract_end_date") or "Не указан"
                fname = space.get("contract_file_name") or ""
                fpath = space.get("contract_file_path") or ""

                with ui.column().classes("w-full gap-2 p-4 border border-slate-200/90 bg-white rounded-xl"):
                    with ui.row().classes("w-full justify-between items-center"):
                        ui.label("Номер договора:").classes("text-sm text-slate-500")
                        ui.label(c_num).classes("font-semibold text-slate-800")
                    with ui.row().classes("w-full justify-between items-center"):
                        ui.label("Срок действия:").classes("text-sm text-slate-500")
                        ui.label(f"до {c_end}").classes("font-semibold text-slate-800")

                if fname and os.path.exists(fpath):
                    with ui.row().classes("w-full items-center justify-between p-3.5 bg-indigo-50/60 border border-indigo-200 rounded-xl"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("description", color="primary")
                            ui.label(fname).classes("text-sm font-medium text-slate-800")
                        ui.button(
                            "Скачать договор",
                            icon="download",
                            on_click=lambda: ui.download(fpath, fname),
                        ).props("dense color=primary")
                else:
                    ui.label("Электронная копия договора еще не прикреплена управляющей компанией.").classes("text-sm text-slate-500")

                with ui.row().classes("w-full justify-end mt-2"):
                    ui.button("Закрыть", on_click=dialog.close).props("dense color=primary")

    dialog.open()


def render_header(user: dict):
    role_label = "Управляющий ТЦ (Арендодатель)" if user["role"] == "landlord" else "Арендатор"
    with ui.row().classes("w-full bg-slate-950 text-white px-6 py-3.5 items-center justify-between border-b border-slate-800 shadow-sm"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("domain", size="sm").classes("text-indigo-400")
            ui.label("MallService").classes("font-extrabold text-lg tracking-tight")
            ui.badge(role_label, color="indigo").props("rounded")

            # LIVE индикатор реального времени
            with ui.row().classes("items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-950/60 border border-emerald-500/40 text-emerald-400 text-xs font-semibold ml-1").tooltip("Синхронизация в реальном времени каждые 2 сек"):
                ui.html('<span class="relative flex h-2 w-2"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span><span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span></span>')
                ui.label("LIVE").classes("text-[11px] font-bold tracking-wider")

        with ui.row().classes("items-center gap-4"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("account_circle", size="sm").classes("text-slate-400")
                ui.label(user["display_name"]).classes("text-sm text-slate-200 font-medium")
            ui.button("Выйти", icon="logout", on_click=logout).props("flat dense color=white").classes("text-slate-400 hover:text-white")


# =====================================================================
# СТРАНИЦА ВХОДА (/login) — Split-Screen
# =====================================================================
@ui.page("/login")
def login_page():
    inject_global_styles()
    ui.colors(primary="#1e1b4b", secondary="#475569", positive="#10b981", negative="#ef4444", warning="#f59e0b")

    current_user = app.storage.user.get("user")
    if current_user:
        ui.navigate.to("/" if current_user["role"] == "landlord" else "/tenant")
        return

    with ui.element("div").classes("w-full min-h-screen grid grid-cols-1 md:grid-cols-2 m-0 p-0"):
        # Левая половина: темная брендированная панель
        with ui.element("div").classes("bg-slate-950 text-white p-8 md:p-14 flex flex-col justify-between relative overflow-hidden"):
            ui.html('''
            <div style="position: absolute; top: -80px; left: -80px; width: 340px; height: 340px; background: radial-gradient(circle, rgba(99,102,241,0.18) 0%, rgba(15,23,42,0) 70%); border-radius: 50%; pointer-events: none;"></div>
            <div style="position: absolute; bottom: -60px; right: -60px; width: 320px; height: 320px; background: radial-gradient(circle, rgba(56,189,248,0.12) 0%, rgba(15,23,42,0) 70%); border-radius: 50%; pointer-events: none;"></div>
            ''')

            with ui.column().classes("gap-6 relative z-10 my-auto"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("domain", size="md").classes("text-indigo-400")
                    ui.label("MallService").classes("text-3xl md:text-4xl font-extrabold tracking-tight text-white")
                    ui.badge("PropTech Platform", color="indigo").props("outline")

                ui.label("Система управления коммерческой недвижимостью и эксплуатацией ТЦ").classes("text-base md:text-lg text-slate-300 font-normal leading-relaxed")

                ui.separator().classes("bg-slate-800/80 my-2")

                with ui.column().classes("gap-6 mt-2"):
                    # Тезис 1
                    with ui.row().classes("items-start gap-4"):
                        with ui.element("div").classes("w-10 h-10 rounded-xl bg-indigo-950/90 border border-indigo-700/50 flex items-center justify-center shrink-0 mt-0.5"):
                            ui.icon("map", size="sm").classes("text-indigo-300")
                        with ui.column().classes("gap-1"):
                            ui.label("Интерактивный поэтажный план").classes("font-semibold text-white text-base")
                            ui.label("Наглядная схема павильонов, статусов аренды, свободных лотов и технических зон в реальном времени.").classes("text-sm text-slate-400 leading-normal")

                    # Тезис 2
                    with ui.row().classes("items-start gap-4"):
                        with ui.element("div").classes("w-10 h-10 rounded-xl bg-emerald-950/90 border border-emerald-700/50 flex items-center justify-center shrink-0 mt-0.5"):
                            ui.icon("engineering", size="sm").classes("text-emerald-300")
                        with ui.column().classes("gap-1"):
                            ui.label("Диспетчеризация и эксплуатация").classes("font-semibold text-white text-base")
                            ui.label("Моментальный прием аварийных и плановых заявок на ремонт с фотофиксацией и контролем устранения.").classes("text-sm text-slate-400 leading-normal")

                    # Тезис 3
                    with ui.row().classes("items-start gap-4"):
                        with ui.element("div").classes("w-10 h-10 rounded-xl bg-sky-950/90 border border-sky-700/50 flex items-center justify-center shrink-0 mt-0.5"):
                            ui.icon("assessment", size="sm").classes("text-sky-300")
                        with ui.column().classes("gap-1"):
                            ui.label("Документооборот и MRR-аналитика").classes("font-semibold text-white text-base")
                            ui.label("Расчет арендной выручки (MRR), процент заполняемости, реестр договоров и централизованные рассылки.").classes("text-sm text-slate-400 leading-normal")

            with ui.row().classes("items-center justify-between text-xs text-slate-500 pt-6 border-t border-slate-800/80 relative z-10"):
                ui.label("© 2026 MallService Platform • Версия 2.4")
                ui.label("Диспетчерская служба ТЦ")

        # Правая половина: светлая область с формой
        with ui.element("div").classes("bg-slate-50 p-6 md:p-12 flex items-center justify-center"):
            with ui.card().classes("w-full max-w-md p-8 gap-5 bg-white border border-slate-200/90 shadow-sm rounded-2xl").props("flat"):
                with ui.column().classes("gap-1"):
                    ui.label("Вход в систему").classes("text-2xl font-bold text-slate-900")
                    ui.label("Введите учетные данные для доступа в личный кабинет").classes("text-sm text-slate-500")

                username_input = ui.input("Логин").classes("w-full mt-2").props("outlined dense")
                password_input = ui.input("Пароль", password=True, password_toggle_button=True).classes("w-full").props("outlined dense")

                def try_login():
                    user = db.authenticate_user(username_input.value or "", password_input.value or "")
                    if not user:
                        ui.notify("Неверный логин или пароль", type="negative", icon="warning")
                        return

                    app.storage.user["user"] = user
                    ui.notify(f"Добро пожаловать, {user['display_name']}!", type="positive")
                    ui.navigate.to("/" if user["role"] == "landlord" else "/tenant")

                password_input.on("keydown.enter", try_login)

                ui.button("Войти в кабинет", icon="login", on_click=try_login).classes("w-full py-2.5 rounded-xl text-white font-medium mt-1 shadow-sm").props("color=primary")

                with ui.row().classes("w-full items-center justify-center p-3 bg-slate-50 rounded-xl border border-slate-200/60 mt-1"):
                    ui.icon("info", size="xs").classes("text-slate-400 mr-1.5")
                    ui.label("Тестовые логины и пароли указаны в файле credentials.txt").classes("text-xs text-slate-500 text-center")


# =====================================================================
# СТРАНИЦА 1: КАБИНЕТ АРЕНДОДАТЕЛЯ (/)
# =====================================================================
@ui.page("/")
def landlord_page():
    user = app.storage.user.get("user")
    if not user:
        ui.navigate.to("/login")
        return
    if user["role"] != "landlord":
        ui.navigate.to("/tenant")
        return

    inject_global_styles()
    ui.colors(primary="#1e1b4b", secondary="#475569", positive="#10b981", negative="#ef4444", warning="#f59e0b")
    render_header(user)

    state = {
        "floor": 1,
        "selected_id": None,
        "last_sig": db.get_sync_signature(),
        "upload_file": None,
    }

    def build_floor_svg(floor: int) -> str:
        spaces = db.get_spaces_by_floor(floor)
        alert_spaces = db.get_active_ticket_alerts()

        elements = [
            '<defs>',
            '  <pattern id="grid-pattern-landlord" width="20" height="20" patternUnits="userSpaceOnUse">',
            '    <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#e2e8f0" stroke-width="0.8" />',
            '  </pattern>',
            '  <filter id="select-shadow-landlord" x="-10%" y="-10%" width="125%" height="125%">',
            '    <feDropShadow dx="0" dy="3" stdDeviation="3.5" flood-color="#1e1b4b" flood-opacity="0.32" />',
            '  </filter>',
            '</defs>',
            # Контур этажа и сетка
            '<rect x="5" y="5" width="590" height="350" rx="10" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2" />',
            '<rect x="5" y="5" width="590" height="350" rx="10" fill="url(#grid-pattern-landlord)" />',
            # Центральный коридор / атриум
            '<rect x="15" y="138" width="570" height="84" rx="8" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1.5" stroke-dasharray="6,4" />',
            # Вход A слева
            '<path d="M 20 180 L 38 180 M 32 174 L 38 180 L 32 186" fill="none" stroke="#64748b" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />',
            '<text x="29" y="166" text-anchor="middle" fill="#64748b" font-size="8.5" font-weight="700" font-family="\'Inter\', sans-serif" letter-spacing="1">ВХОД A</text>',
            # Вход B справа
            '<path d="M 580 180 L 562 180 M 568 174 L 562 180 L 568 186" fill="none" stroke="#64748b" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />',
            '<text x="571" y="166" text-anchor="middle" fill="#64748b" font-size="8.5" font-weight="700" font-family="\'Inter\', sans-serif" letter-spacing="1">ВХОД B</text>',
            # Текстовые метки галереи
            '<text x="155" y="184" text-anchor="middle" fill="#94a3b8" font-size="11" font-weight="600" font-family="\'Inter\', sans-serif" letter-spacing="3">ГАЛЕРЕЯ</text>',
            '<text x="445" y="184" text-anchor="middle" fill="#94a3b8" font-size="11" font-weight="600" font-family="\'Inter\', sans-serif" letter-spacing="3">ГАЛЕРЕЯ</text>',
            # Блок эскалаторов и лифта в центре коридора
            '<rect x="270" y="148" width="60" height="64" rx="6" fill="#ffffff" stroke="#94a3b8" stroke-width="1.5" />',
            '<line x1="300" y1="148" x2="300" y2="212" stroke="#e2e8f0" stroke-width="1.5" />',
            # Эскалатор слева
            '<path d="M 275 200 L 295 158" stroke="#64748b" stroke-width="1.5" stroke-linecap="round" />',
            '<path d="M 276 192 L 280 192 L 280 186 L 284 186 L 284 180 L 288 180 L 288 174 L 292 174" fill="none" stroke="#94a3b8" stroke-width="1" />',
            '<text x="285" y="208" text-anchor="middle" fill="#64748b" font-size="7" font-weight="700" font-family="\'Inter\', sans-serif">ЭСКАЛ</text>',
            # Лифт справа
            '<rect x="306" y="156" width="18" height="26" rx="2" fill="none" stroke="#64748b" stroke-width="1.2" />',
            '<line x1="315" y1="156" x2="315" y2="182" stroke="#64748b" stroke-width="1" stroke-dasharray="2,2" />',
            '<polygon points="312,165 315,161 318,165" fill="#64748b" />',
            '<polygon points="312,173 315,177 318,173" fill="#64748b" />',
            '<text x="315" y="208" text-anchor="middle" fill="#64748b" font-size="7" font-weight="700" font-family="\'Inter\', sans-serif">ЛИФТ</text>',
        ]

        for s in spaces:
            is_selected = s["id"] == state["selected_id"]
            meta = STATUS_META[s["status"]]

            fill = meta["fill"]
            border = meta["border"]
            text_color = meta["text"]
            accent = meta["accent"]

            stroke = "#1e1b4b" if is_selected else border
            stroke_width = "2.5" if is_selected else "1.5"
            filter_attr = 'filter="url(#select-shadow-landlord)"' if is_selected else ""
            clip_id = f"clip-landlord-{s['id']}"
            x, y, w, h = s["x"], s["y"], s["w"], s["h"]

            # Отрисовка павильона с аккуратным скруглением и левой акцентной полосой 4px
            elements.append(f'<clipPath id="{clip_id}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" /></clipPath>')
            elements.append(f'<g clip-path="url(#{clip_id})">')
            elements.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" />')
            elements.append(f'<rect x="{x}" y="{y}" width="4" height="{h}" fill="{accent}" />')
            elements.append("</g>")
            elements.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="none" stroke="{stroke}" stroke-width="{stroke_width}" {filter_attr} />')

            # Типографическая иерархия
            # 1. Код помещения (крупно сверху слева)
            elements.append(
                f'<text x="{x + 14}" y="{y + 25}" text-anchor="start" fill="{text_color}" font-weight="700" '
                f'font-size="15" font-family="\'Inter\', sans-serif">{s["code"]}</text>'
            )

            # 2. Метраж (мелко сверху справа с tabular-nums)
            elements.append(
                f'<text x="{x + w - 14}" y="{y + 25}" text-anchor="end" fill="#64748b" font-weight="500" '
                f'font-size="12" font-family="\'Inter\', sans-serif" class="tabular-nums">{s["area"]} м²</text>'
            )

            # Тонкий внутренний разделитель
            elements.append(f'<line x1="{x + 12}" y1="{y + 35}" x2="{x + w - 12}" y2="{y + 35}" stroke="{border}" stroke-opacity="0.3" stroke-width="1" />')

            # 3. Название бренда / статус (по центру)
            tenant_label = s["tenant"] if s["tenant"] else meta["label"]
            if len(tenant_label) > 18:
                tenant_label = tenant_label[:16] + "…"
            elements.append(
                f'<text x="{x + w // 2}" y="{y + 66}" text-anchor="middle" fill="{text_color}" font-weight="600" '
                f'font-size="13" font-family="\'Inter\', sans-serif">{tenant_label}</text>'
            )

            # 4. Ставка аренды (снизу)
            price_str = f"{s['price']:,} ₽/мес".replace(",", " ")
            elements.append(
                f'<text x="{x + w // 2}" y="{y + 88}" text-anchor="middle" fill="#64748b" font-weight="500" '
                f'font-size="11" font-family="\'Inter\', sans-serif" class="tabular-nums">{price_str}</text>'
            )

            # Индикатор активных заявок
            alert_priority = alert_spaces.get(s["id"])
            if alert_priority:
                is_urgent = alert_priority == "urgent"
                badge_fill = "#ef4444" if is_urgent else "#f59e0b"
                badge_stroke = "#ffffff"
                bx, by = x + w - 8, y + 8
                elements.append(f'<circle cx="{bx}" cy="{by}" r="9" fill="{badge_fill}" stroke="{badge_stroke}" stroke-width="2" />')
                elements.append(
                    f'<text x="{bx}" y="{by + 3.5}" text-anchor="middle" fill="#ffffff" font-weight="bold" '
                    f'font-size="11" font-family="\'Inter\', sans-serif">!</text>'
                )

        return "".join(elements)

    def on_floor_change(new_floor: int):
        state["floor"] = new_floor
        state["selected_id"] = None
        refresh_all(update_inspector=True)

    def on_map_mouse(e: events.MouseEventArguments):
        for s in db.get_spaces_by_floor(state["floor"]):
            if s["x"] <= e.image_x <= s["x"] + s["w"] and s["y"] <= e.image_y <= s["y"] + s["h"]:
                state["selected_id"] = s["id"]
                refresh_all(update_inspector=True)
                return

    def update_tab_labels():
        tickets = db.get_tickets()
        active_cnt = sum(1 for t in tickets if t["status"] != "done")
        urgent_cnt = sum(1 for t in tickets if t["status"] != "done" and t["priority"] == "urgent")
        t_label = f"Заявки на ремонт ({active_cnt})" if not urgent_cnt else f"Заявки на ремонт ({active_cnt} • {urgent_cnt} ав.)"
        tab_tickets.set_label(t_label)
        msgs = db.get_messages_for_landlord()
        tab_messages.set_label(f"Сообщения и рассылки ({len(msgs)})")

    def refresh_all(update_inspector: bool = False):
        state["last_sig"] = db.get_sync_signature()
        map_view.content = build_floor_svg(state["floor"])
        floor_buttons.refresh()
        stats_bar.refresh()
        tickets_panel.refresh()
        messages_feed.refresh()
        update_tab_labels()
        if update_inspector:
            inspector_panel.refresh()

    def poll_updates():
        current_sig = db.get_sync_signature()
        if current_sig != state["last_sig"]:
            if current_sig[0] > state["last_sig"][0]:
                ui.notify("Поступила новая заявка на ремонт!", type="warning", icon="build")
            if current_sig[3] > state["last_sig"][3]:
                ui.notify("Новое сообщение в чате с арендаторами!", type="info", icon="mail")
            refresh_all(update_inspector=False)

    ui.timer(2.0, poll_updates)

    with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6"):
        # Верхняя панель управления и переключения этажей
        with ui.row().classes("w-full justify-between items-center"):
            with ui.column().classes("gap-0.5"):
                ui.label("Карта площадей и управление ТЦ").classes("text-2xl font-bold text-slate-900 tracking-tight")
                ui.label("Интерактивный поэтажный план коммерческих помещений").classes("text-xs text-slate-500")

            @ui.refreshable
            def floor_buttons():
                with ui.row().classes("bg-slate-200/80 p-1 rounded-xl items-center gap-1 border border-slate-300/60"):
                    for f in (1, 2):
                        is_active = state["floor"] == f
                        btn_classes = (
                            "bg-white text-slate-900 font-semibold shadow-xs rounded-lg px-4 py-1.5 transition-all"
                            if is_active
                            else "text-slate-600 hover:text-slate-900 font-medium px-4 py-1.5 transition-all"
                        )
                        ui.button(
                            f"{f} этаж",
                            on_click=lambda fl=f: on_floor_change(fl),
                        ).classes(btn_classes).props("flat dense")

            floor_buttons()

        # KPI-дашборд вместо текстовой полоски (4 равные KPI-карточки)
        @ui.refreshable
        def stats_bar():
            spaces = db.get_spaces_by_floor(state["floor"])
            tickets = db.get_tickets()

            total_area = sum(s["area"] for s in spaces) or 1.0
            occupied_area = sum(s["area"] for s in spaces if s["status"] == "occupied")
            occupancy_rate = (occupied_area / total_area) * 100.0

            total_income = sum(s["price"] for s in spaces if s["status"] == "occupied")
            potential_income = sum(s["price"] for s in spaces)

            free_spaces = [s for s in spaces if s["status"] == "free"]
            free_area = sum(s["area"] for s in free_spaces)
            free_cnt = len(free_spaces)

            active_tickets = [t for t in tickets if t["status"] != "done"]
            urgent_cnt = sum(1 for t in active_tickets if t["priority"] == "urgent")
            active_cnt = len(active_tickets)

            with ui.grid(columns=4).classes("w-full gap-4"):
                # 1. Заполняемость этажа
                with ui.card().classes("bg-white border border-slate-200/90 shadow-sm rounded-xl p-4 flex flex-col justify-between").props("flat"):
                    with ui.row().classes("w-full justify-between items-center"):
                        ui.label("Заполняемость этажа").classes("text-xs font-semibold text-slate-500 uppercase tracking-wider")
                        ui.icon("pie_chart", size="xs").classes("text-slate-400")
                    with ui.column().classes("gap-1 mt-2"):
                        ui.label(f"{occupancy_rate:.1f}%").classes("text-2xl font-bold text-slate-900 tabular-nums")
                        ui.label(f"{occupied_area:.0f} из {total_area:.0f} м² занято").classes("text-xs text-slate-500 tabular-nums")
                        ui.linear_progress(value=occupancy_rate / 100.0, show_value=False).classes("w-full rounded-full h-1.5 mt-2 bg-slate-100").props("color=primary")

                # 2. Ежемесячный доход (MRR)
                with ui.card().classes("bg-white border border-slate-200/90 shadow-sm rounded-xl p-4 flex flex-col justify-between").props("flat"):
                    with ui.row().classes("w-full justify-between items-center"):
                        ui.label("Ежемесячный доход (MRR)").classes("text-xs font-semibold text-slate-500 uppercase tracking-wider")
                        ui.icon("payments", size="xs").classes("text-emerald-500")
                    with ui.column().classes("gap-1 mt-2"):
                        income_str = f"{total_income:,} ₽".replace(",", " ")
                        ui.label(income_str).classes("text-2xl font-bold text-slate-900 tabular-nums")
                        potential_str = f"{potential_income:,} ₽".replace(",", " ")
                        ui.label(f"Потенциал этажа: {potential_str}").classes("text-xs text-slate-500 tabular-nums")
                        with ui.row().classes("items-center gap-1 mt-2 text-xs text-emerald-600 font-medium"):
                            ui.icon("trending_up", size="xs")
                            ui.label("Текущий арендный сбор")

                # 3. Свободный фонд
                with ui.card().classes("bg-white border border-slate-200/90 shadow-sm rounded-xl p-4 flex flex-col justify-between").props("flat"):
                    with ui.row().classes("w-full justify-between items-center"):
                        ui.label("Свободный фонд").classes("text-xs font-semibold text-slate-500 uppercase tracking-wider")
                        ui.icon("storefront", size="xs").classes("text-amber-500")
                    with ui.column().classes("gap-1 mt-2"):
                        ui.label(f"{free_area:.1f} м²").classes("text-2xl font-bold text-slate-900 tabular-nums")
                        lot_word = "лотов" if free_cnt == 0 or free_cnt >= 5 else ("лот" if free_cnt == 1 else "лота")
                        ui.label(f"{free_cnt} {lot_word} готово к сдаче").classes("text-xs text-slate-500 tabular-nums")
                        with ui.row().classes("items-center gap-1 mt-2 text-xs text-slate-500"):
                            ui.badge(f"Свободно: {free_cnt}", color="emerald").props("outline dense")

                # 4. Эксплуатация
                border_class = "border-red-300 bg-red-50/20" if urgent_cnt > 0 else "border-slate-200/90 bg-white"
                with ui.card().classes(f"{border_class} shadow-sm rounded-xl p-4 flex flex-col justify-between").props("flat"):
                    with ui.row().classes("w-full justify-between items-center"):
                        ui.label("Эксплуатация").classes("text-xs font-semibold text-slate-500 uppercase tracking-wider")
                        icon_color = "text-red-500" if urgent_cnt > 0 else "text-slate-400"
                        ui.icon("build", size="xs").classes(icon_color)
                    with ui.column().classes("gap-1 mt-2"):
                        val_color = "text-red-600" if urgent_cnt > 0 else "text-slate-900"
                        ui.label(f"{active_cnt} активных").classes(f"text-2xl font-bold {val_color} tabular-nums")
                        if urgent_cnt > 0:
                            with ui.row().classes("items-center gap-1 mt-1 text-xs text-red-600 font-semibold"):
                                ui.icon("error", size="xs")
                                ui.label(f"{urgent_cnt} аварийная заявка!")
                        else:
                            ui.label("Все системы работают штатно").classes("text-xs text-emerald-600 mt-1 font-medium")
                        with ui.row().classes("items-center gap-1 mt-2"):
                            if urgent_cnt > 0:
                                ui.badge(f"Аварийных: {urgent_cnt}", color="red").props("dense")
                            else:
                                ui.badge("Штатный режим", color="emerald").props("outline dense")

        stats_bar()

        # Средний блок: Слева карта, справа Инспектор помещения
        with ui.row().classes("w-full gap-6 items-start no-wrap"):
            with ui.card().classes("flex-1 p-4 bg-white border border-slate-200/90 shadow-sm rounded-xl flex flex-col gap-3").props("flat"):
                with ui.row().classes("w-full justify-between items-center text-xs text-slate-500 px-1"):
                    ui.label("Интерактивная карта (кликните по павильону для выбора)").classes("font-medium")
                    with ui.row().classes("items-center gap-3"):
                        with ui.row().classes("items-center gap-1"):
                            ui.element("div").classes("w-2.5 h-2.5 rounded-full bg-emerald-500")
                            ui.label("Свободно")
                        with ui.row().classes("items-center gap-1"):
                            ui.element("div").classes("w-2.5 h-2.5 rounded-full bg-amber-500")
                            ui.label("Бронь")
                        with ui.row().classes("items-center gap-1"):
                            ui.element("div").classes("w-2.5 h-2.5 rounded-full bg-slate-400")
                            ui.label("Занято")

                map_view = ui.interactive_image(
                    size=(600, 360),
                    content=build_floor_svg(state["floor"]),
                    on_mouse=on_map_mouse,
                    events=["click"],
                ).classes("w-full border border-slate-200 rounded-lg bg-slate-50 cursor-pointer overflow-hidden")

            @ui.refreshable
            def inspector_panel():
                with ui.card().classes("w-96 shrink-0 p-5 bg-white border border-slate-200/90 shadow-sm rounded-xl flex flex-col gap-3").props("flat"):
                    sid = state["selected_id"]
                    if not sid:
                        with ui.column().classes("w-full py-8 items-center text-center gap-2"):
                            ui.icon("touch_app", size="42px").classes("text-slate-300")
                            ui.label("Карточка помещения").classes("text-base font-bold text-slate-800")
                            ui.label("Нажмите на любой павильон на схеме слева, чтобы посмотреть параметры, договор, контакты руководства или изменить статус.").classes("text-xs text-slate-500 leading-relaxed max-w-xs")
                        return

                    space = db.get_space_by_id(sid)
                    meta = STATUS_META[space["status"]]
                    is_free = space["status"] == "free"

                    with ui.row().classes("w-full justify-between items-center"):
                        ui.label(f"Павильон {space['code']}").classes("text-xl font-bold text-slate-900")
                        ui.badge(meta["label"], color=meta["badge"]).props("dense")

                    ui.label(f"Этаж: {space['floor']} • Площадь: {space['area']} м²").classes("text-xs text-slate-500 tabular-nums -mt-1")

                    if is_free:
                        ui.button(
                            "Шаблон договора аренды",
                            icon="description",
                            on_click=lambda sp=space: open_contract_dialog(sp, is_landlord=True),
                        ).classes("w-full mb-1").props("outline dense")
                    else:
                        has_file = bool(space.get("contract_file_name"))
                        c_num = space.get("contract_number") or "Без номера"
                        btn_label = f"Договор ({c_num})" if not has_file else f"Договор ({c_num}) • Файл"
                        ui.button(
                            btn_label,
                            icon="folder_shared",
                            on_click=lambda sp=space: open_contract_dialog(
                                sp, is_landlord=True, on_saved=lambda: refresh_all(update_inspector=True)
                            ),
                        ).classes("w-full mb-1").props("outline dense color=primary")

                    ui.separator().classes("bg-slate-200/60 my-1")

                    status_select = ui.select(
                        options={k: v["label"] for k, v in STATUS_META.items()},
                        value=space["status"],
                        label="Статус помещения",
                    ).classes("w-full").props("outlined dense")

                    tenant_input = ui.input(
                        label="Арендатор / Бренд",
                        value=space["tenant"] or "",
                        placeholder="Например: Кофейня",
                    ).classes("w-full").props("outlined dense")

                    price_input = ui.number(
                        label="Ставка аренды (₽/мес)",
                        value=space["price"],
                        step=5000,
                    ).classes("w-full").props("outlined dense")

                    ui.label("Контакты руководства точки").classes("text-[11px] font-bold uppercase tracking-wider text-slate-500 mt-2")

                    point_dir_input = ui.input(
                        label="Директор точки",
                        value=space["point_director"] or "",
                        placeholder="ФИО, телефон",
                    ).classes("w-full").props("outlined dense")

                    area_dir_input = ui.input(
                        label="Вышестоящий директор (если есть)",
                        value=space["area_director"] or "",
                        placeholder="ФИО, телефон (необязательно)",
                    ).classes("w-full").props("outlined dense")

                    ui.label("Служебная информация (видит только УК)").classes("text-[11px] font-bold uppercase tracking-wider text-amber-700 mt-2")

                    notes_input = ui.textarea(
                        label="Внутренние заметки арендодателя",
                        value=space["internal_notes"] or "",
                        placeholder="История переговоров, скидки, технические особенности точки...",
                    ).classes("w-full bg-amber-50/40").props("outlined dense rows=2")

                    def save_changes():
                        db.update_space(
                            space_id=sid,
                            status=status_select.value,
                            tenant=tenant_input.value,
                            price=int(price_input.value or 0),
                            point_director=point_dir_input.value,
                            area_director=area_dir_input.value,
                            internal_notes=notes_input.value,
                        )
                        ui.notify(f"Павильон {space['code']} успешно обновлен", type="positive")
                        refresh_all(update_inspector=True)

                    ui.button("Сохранить изменения", icon="save", on_click=save_changes).classes("w-full mt-2 text-white font-medium").props("color=primary dense")

            inspector_panel()

        # Нижний блок: Аккуратные вкладки (Заявки на ремонт / Сообщения и рассылки)
        with ui.card().classes("w-full p-0 bg-white border border-slate-200/90 shadow-sm rounded-xl overflow-hidden").props("flat"):
            with ui.tabs().classes("w-full border-b border-slate-200 bg-slate-50/70 px-4 text-slate-700") as landlord_tabs:
                tab_tickets = ui.tab("tickets", label="Заявки на ремонт", icon="build")
                tab_messages = ui.tab("messages", label="Сообщения и рассылки", icon="forum")

            with ui.tab_panels(landlord_tabs, value=tab_tickets).classes("w-full p-6 bg-white"):
                # Панель 1: Заявки на ремонт
                with ui.tab_panel(tab_tickets):
                    @ui.refreshable
                    def tickets_panel():
                        tickets = db.get_tickets()
                        active_cnt = sum(1 for t in tickets if t["status"] != "done")
                        urgent_cnt = sum(1 for t in tickets if t["status"] != "done" and t["priority"] == "urgent")

                        with ui.row().classes("w-full justify-between items-center mb-4"):
                            with ui.row().classes("items-center gap-3"):
                                ui.label("Журнал заявок на ремонт и обслуживание").classes("text-lg font-bold text-slate-800")
                                if active_cnt:
                                    ui.badge(f"Активных: {active_cnt}", color="orange").props("dense")
                                if urgent_cnt:
                                    ui.badge(f"Аварийных: {urgent_cnt}", color="red").props("dense")

                        if not tickets:
                            render_empty_state("task_alt", "Заявок на ремонт нет", "Все инженерно-технические заявки арендаторов выполнены либо еще не создавались.")
                            return

                        with ui.column().classes("w-full gap-3"):
                            for t in tickets:
                                t_meta = TICKET_META[t["status"]]
                                p_meta = TICKET_PRIORITIES.get(t["priority"], TICKET_PRIORITIES["normal"])
                                cat_label = TICKET_CATEGORIES.get(t["category"], "Общий ремонт")
                                space_info = db.get_space_by_id(t["space_id"]) or {}
                                p_dir = space_info.get("point_director", "")
                                a_dir = space_info.get("area_director", "")

                                is_urgent_active = t["priority"] == "urgent" and t["status"] != "done"
                                card_border = "border-red-300 bg-red-50/30" if is_urgent_active else "border-slate-200 bg-slate-50/50"

                                with ui.row().classes(f"w-full items-start justify-between p-4 border rounded-xl gap-4 {card_border}"):
                                    with ui.column().classes("gap-1.5 flex-1"):
                                        with ui.row().classes("items-center gap-2 flex-wrap"):
                                            ui.badge(f"Павильон {t['space_code']}", color="indigo").props("dense")
                                            ui.badge(p_meta["label"], color=p_meta["badge"]).props("dense")
                                            ui.badge(cat_label, color="grey").props("outline dense")
                                            ui.label(t["tenant"]).classes("font-semibold text-slate-800 ml-1")
                                            ui.label(f"• {t['created_at']}").classes("text-xs text-slate-400 tabular-nums")

                                        ui.label(t["description"]).classes("text-sm text-slate-800 mt-1")

                                        if t.get("photo_name") and os.path.exists(t.get("photo_path", "")):
                                            ui.button(
                                                f"Фотофиксация: {t['photo_name']}",
                                                icon="photo_camera",
                                                on_click=lambda p=t["photo_path"], n=t["photo_name"]: open_photo_preview(p, n),
                                            ).props("dense flat size=sm color=primary").classes("mt-1")

                                        if p_dir or a_dir:
                                            contact_parts = []
                                            if p_dir:
                                                contact_parts.append(f"Директор точки: {p_dir}")
                                            if a_dir:
                                                contact_parts.append(f"Вышестоящий: {a_dir}")
                                            ui.label(" • ".join(contact_parts)).classes("text-xs text-slate-500 mt-1")

                                    with ui.column().classes("items-end gap-2 shrink-0"):
                                        ui.badge(t_meta["label"], color=t_meta["badge"]).props("dense")
                                        with ui.row().classes("gap-1.5"):
                                            if t["status"] == "new":
                                                ui.button(
                                                    "В работу",
                                                    icon="play_arrow",
                                                    on_click=lambda tid=t["id"]: (db.update_ticket_status(tid, "in_progress"), refresh_all()),
                                                ).props("dense outline size=sm")
                                            if t["status"] != "done":
                                                ui.button(
                                                    "Выполнено",
                                                    icon="check",
                                                    color="positive",
                                                    on_click=lambda tid=t["id"]: (db.update_ticket_status(tid, "done"), refresh_all()),
                                                ).props("dense size=sm")

                    tickets_panel()

                # Панель 2: Сообщения и рассылки
                with ui.tab_panel(tab_messages):
                    with ui.row().classes("w-full gap-8 items-start"):
                        # Форма отправки сообщения
                        with ui.column().classes("w-96 shrink-0 gap-3 p-4 bg-slate-50 rounded-xl border border-slate-200/90"):
                            ui.label("Новая рассылка или сообщение").classes("text-base font-bold text-slate-800")

                            recipient_options = {"ALL": "📢 Всем арендаторам (Общая рассылка)"}
                            for s in db.get_all_spaces():
                                label = f"Павильон {s['code']} — {s['tenant']}" if s["tenant"] else f"Павильон {s['code']} (свободен)"
                                recipient_options[s["id"]] = label

                            target_select = ui.select(
                                options=recipient_options,
                                value="ALL",
                                label="Кому отправить",
                            ).classes("w-full").props("outlined dense")

                            msg_input = ui.textarea(
                                label="Текст сообщения / рассылки",
                                placeholder="Например: Просим направить показания приборов учета до 25 числа.",
                            ).classes("w-full").props("outlined dense rows=3")

                            async def handle_upload(e: events.UploadEventArguments):
                                att_name, att_path = await save_uploaded_file(e)
                                state["upload_file"] = (att_name, att_path)
                                ui.notify(f"Файл «{att_name}» прикреплен", type="info")

                            uploader = ui.upload(
                                label="Прикрепить файл (счет, шаблон, акт)",
                                auto_upload=True,
                                on_upload=handle_upload,
                            ).classes("w-full").props("flat bordered dense")

                            def send_landlord_msg():
                                has_file = state["upload_file"] is not None
                                if (not msg_input.value or not msg_input.value.strip()) and not has_file:
                                    ui.notify("Введите текст сообщения или прикрепите файл", type="warning")
                                    return

                                att_name, att_path = state["upload_file"] if has_file else ("", "")
                                db.send_message(
                                    sender_role="landlord",
                                    target_space_id=target_select.value,
                                    body=msg_input.value or "",
                                    attachment_name=att_name,
                                    attachment_path=att_path,
                                    )
                                msg_input.value = ""
                                state["upload_file"] = None
                                uploader.reset()
                                refresh_all()
                                ui.notify("Сообщение успешно отправлено!", type="positive")

                            ui.button("Отправить сообщение", icon="send", on_click=send_landlord_msg).classes("w-full py-2 text-white font-medium").props("color=primary dense")

                        # Лента сообщений
                        with ui.column().classes("flex-1 gap-3"):
                            ui.label("История переписки и рассылок").classes("text-base font-bold text-slate-800")

                            @ui.refreshable
                            def messages_feed():
                                msgs = db.get_messages_for_landlord()
                                if not msgs:
                                    render_empty_state("chat_bubble_outline", "Переписка пуста", "История диалогов и рассылок арендаторам появится здесь после отправки первого сообщения.")
                                    return

                                with ui.column().classes("w-full gap-2.5 max-h-[500px] overflow-y-auto pr-1"):
                                    for m in msgs:
                                        is_from_uk = m["sender_role"] == "landlord"
                                        card_bg = "bg-indigo-50/60 border-indigo-200" if is_from_uk else "bg-emerald-50/60 border-emerald-200"

                                        with ui.column().classes(f"w-full p-4 border rounded-xl gap-1.5 {card_bg}"):
                                            with ui.row().classes("w-full justify-between items-center"):
                                                if is_from_uk:
                                                    badge_text = "📢 Всем арендаторам" if m["space_id"] == "ALL" else f"УК → Павильон {m['space_code']}"
                                                    ui.badge(badge_text, color="indigo").props("dense")
                                                else:
                                                    ui.badge(f"От: Павильон {m['space_code']} ({m['tenant_name']})", color="emerald").props("dense")
                                                ui.label(m["created_at"]).classes("text-xs text-slate-400 tabular-nums")

                                            if m["body"]:
                                                ui.label(m["body"]).classes("text-sm text-slate-800 whitespace-pre-line leading-relaxed")

                                            if m["attachment_name"] and os.path.exists(m["attachment_path"]):
                                                ui.button(
                                                    f"Скачать файл: {m['attachment_name']}",
                                                    icon="attach_file",
                                                    on_click=lambda p=m["attachment_path"], n=m["attachment_name"]: ui.download(p, n),
                                                ).props("dense flat size=sm color=primary").classes("mt-1")

                            messages_feed()

        update_tab_labels()


# =====================================================================
# СТРАНИЦА 2: КАБИНЕТ АРЕНДАТОРА (/tenant)
# =====================================================================
@ui.page("/tenant")
def tenant_page():
    user = app.storage.user.get("user")
    if not user:
        ui.navigate.to("/login")
        return
    if user["role"] != "tenant" or not user["space_id"]:
        ui.navigate.to("/")
        return

    inject_global_styles()
    ui.colors(primary="#1e1b4b", secondary="#475569", positive="#10b981", negative="#ef4444", warning="#f59e0b")
    render_header(user)

    my_space_id = user["space_id"]
    state = {
        "last_sig": db.get_sync_signature(),
        "upload_file": None,
        "ticket_photo": None,
    }

    def build_tenant_mini_map(space: dict) -> str:
        spaces = db.get_spaces_by_floor(space["floor"])
        elements = [
            '<defs>',
            '  <pattern id="grid-pattern-tenant" width="20" height="20" patternUnits="userSpaceOnUse">',
            '    <path d="M 20 0 L 0 0 0 20" fill="none" stroke="#e2e8f0" stroke-width="0.8" />',
            '  </pattern>',
            '  <filter id="select-shadow-tenant" x="-10%" y="-10%" width="125%" height="125%">',
            '    <feDropShadow dx="0" dy="3" stdDeviation="3.5" flood-color="#1e1b4b" flood-opacity="0.32" />',
            '  </filter>',
            '</defs>',
            # Контур этажа и сетка
            '<rect x="5" y="5" width="590" height="350" rx="10" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2" />',
            '<rect x="5" y="5" width="590" height="350" rx="10" fill="url(#grid-pattern-tenant)" />',
            # Центральный коридор
            '<rect x="15" y="138" width="570" height="84" rx="8" fill="#f1f5f9" stroke="#cbd5e1" stroke-width="1.5" stroke-dasharray="6,4" />',
            # Вход A слева
            '<path d="M 20 180 L 38 180 M 32 174 L 38 180 L 32 186" fill="none" stroke="#64748b" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />',
            '<text x="29" y="166" text-anchor="middle" fill="#64748b" font-size="8.5" font-weight="700" font-family="\'Inter\', sans-serif" letter-spacing="1">ВХОД A</text>',
            # Вход B справа
            '<path d="M 580 180 L 562 180 M 568 174 L 562 180 L 568 186" fill="none" stroke="#64748b" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />',
            '<text x="571" y="166" text-anchor="middle" fill="#64748b" font-size="8.5" font-weight="700" font-family="\'Inter\', sans-serif" letter-spacing="1">ВХОД B</text>',
            # Текстовые метки коридора
            '<text x="155" y="184" text-anchor="middle" fill="#94a3b8" font-size="11" font-weight="600" font-family="\'Inter\', sans-serif" letter-spacing="3">ГАЛЕРЕЯ</text>',
            '<text x="445" y="184" text-anchor="middle" fill="#94a3b8" font-size="11" font-weight="600" font-family="\'Inter\', sans-serif" letter-spacing="3">ГАЛЕРЕЯ</text>',
            # Блок эскалаторов и лифта
            '<rect x="270" y="148" width="60" height="64" rx="6" fill="#ffffff" stroke="#94a3b8" stroke-width="1.5" />',
            '<line x1="300" y1="148" x2="300" y2="212" stroke="#e2e8f0" stroke-width="1.5" />',
            '<path d="M 275 200 L 295 158" stroke="#64748b" stroke-width="1.5" stroke-linecap="round" />',
            '<text x="285" y="208" text-anchor="middle" fill="#64748b" font-size="7" font-weight="700" font-family="\'Inter\', sans-serif">ЭСКАЛ</text>',
            '<rect x="306" y="156" width="18" height="26" rx="2" fill="none" stroke="#64748b" stroke-width="1.2" />',
            '<polygon points="312,165 315,161 318,165" fill="#64748b" />',
            '<polygon points="312,173 315,177 318,173" fill="#64748b" />',
            '<text x="315" y="208" text-anchor="middle" fill="#64748b" font-size="7" font-weight="700" font-family="\'Inter\', sans-serif">ЛИФТ</text>',
        ]

        for s in spaces:
            is_mine = s["id"] == space["id"]
            x, y, w, h = s["x"], s["y"], s["w"], s["h"]
            clip_id = f"clip-tenant-{s['id']}"

            if is_mine:
                fill = "#ede9fe"
                border = "#1e1b4b"
                stroke_width = "2.5"
                accent = "#1e1b4b"
                text_color = "#1e1b4b"
                filter_attr = 'filter="url(#select-shadow-tenant)"'
            else:
                fill = "#f8fafc"
                border = "#cbd5e1"
                stroke_width = "1.5"
                accent = "#64748b"
                text_color = "#64748b"
                filter_attr = ""

            elements.append(f'<clipPath id="{clip_id}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" /></clipPath>')
            elements.append(f'<g clip-path="url(#{clip_id})">')
            elements.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" />')
            elements.append(f'<rect x="{x}" y="{y}" width="4" height="{h}" fill="{accent}" />')
            elements.append("</g>")
            elements.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="none" stroke="{border}" stroke-width="{stroke_width}" {filter_attr} />')

            # Типографическая иерархия
            elements.append(
                f'<text x="{x + 14}" y="{y + 25}" text-anchor="start" fill="{text_color}" font-weight="700" '
                f'font-size="15" font-family="\'Inter\', sans-serif">{s["code"]}</text>'
            )
            elements.append(
                f'<text x="{x + w - 14}" y="{y + 25}" text-anchor="end" fill="#64748b" font-weight="500" '
                f'font-size="12" font-family="\'Inter\', sans-serif" class="tabular-nums">{s["area"]} м²</text>'
            )

            if is_mine:
                elements.append(
                    f'<text x="{x + w // 2}" y="{y + 66}" text-anchor="middle" fill="#1e1b4b" font-weight="700" '
                    f'font-size="13" font-family="\'Inter\', sans-serif">ВАШ ПАВИЛЬОН</text>'
                )
                tenant_label = s["tenant"] or user["display_name"]
                if len(tenant_label) > 18:
                    tenant_label = tenant_label[:16] + "…"
                elements.append(
                    f'<text x="{x + w // 2}" y="{y + 88}" text-anchor="middle" fill="#4338ca" font-weight="600" '
                    f'font-size="11" font-family="\'Inter\', sans-serif">{tenant_label}</text>'
                )
            else:
                s_label = s["tenant"] if s["tenant"] else STATUS_META[s["status"]]["label"]
                if len(s_label) > 18:
                    s_label = s_label[:16] + "…"
                elements.append(
                    f'<text x="{x + w // 2}" y="{y + 68}" text-anchor="middle" fill="#94a3b8" font-weight="500" '
                    f'font-size="12" font-family="\'Inter\', sans-serif">{s_label}</text>'
                )

        return "".join(elements)

    @ui.refreshable
    def space_info_card():
        space = db.get_space_by_id(my_space_id)
        with ui.card().classes("flex-1 p-5 gap-3 bg-white border border-slate-200/90 shadow-sm rounded-xl").props("flat"):
            with ui.row().classes("w-full justify-between items-center"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("store", size="sm").classes("text-indigo-600")
                    ui.label("Расположение на плане этажа").classes("text-lg font-bold text-slate-800")
                ui.button(
                    "Мой договор аренды",
                    icon="description",
                    on_click=lambda sp=space: open_contract_dialog(sp, is_landlord=False),
                ).props("outline dense color=primary")

            ui.interactive_image(
                size=(600, 360),
                content=build_tenant_mini_map(space),
            ).classes("w-full border border-slate-200 rounded-lg bg-slate-50")

            with ui.row().classes("w-full justify-between bg-slate-50 p-3.5 rounded-xl border border-slate-200/80 items-center mt-1"):
                with ui.column().classes("gap-0"):
                    ui.label("Этаж").classes("text-xs text-slate-400 uppercase font-semibold")
                    ui.label(f"{space['floor']} этаж").classes("font-bold text-slate-800 text-sm")
                with ui.column().classes("gap-0"):
                    ui.label("Площадь").classes("text-xs text-slate-400 uppercase font-semibold")
                    ui.label(f"{space['area']} м²").classes("font-bold text-slate-800 text-sm tabular-nums")
                with ui.column().classes("items-end gap-0"):
                    ui.label("Арендная ставка").classes("text-xs text-slate-400 uppercase font-semibold")
                    rent_str = f"{space['price']:,} ₽/мес".replace(",", " ")
                    ui.label(rent_str).classes("font-bold text-indigo-700 text-base tabular-nums")

    def update_tenant_tab_labels():
        my_tickets = db.get_tickets(space_id=my_space_id)
        my_active_cnt = sum(1 for t in my_tickets if t["status"] != "done")
        tenant_tab_tickets.set_label(f"Мои заявки на ремонт ({my_active_cnt})")
        msgs = db.get_messages_for_tenant(my_space_id)
        tenant_tab_messages.set_label(f"Сообщения и связь с УК ({len(msgs)})")

    def poll_tenant_updates():
        current_sig = db.get_sync_signature()
        if current_sig != state["last_sig"]:
            if current_sig[1] != state["last_sig"][1] and current_sig[0] == state["last_sig"][0]:
                ui.notify("Статус вашей заявки обновлен управляющим!", type="info")
            if current_sig[3] > state["last_sig"][3]:
                ui.notify("Новое сообщение или рассылка от администрации ТЦ!", type="info", icon="mail")
            state["last_sig"] = current_sig
            space_info_card.refresh()
            my_tickets_card.refresh()
            tenant_messages_feed.refresh()
            update_tenant_tab_labels()

    ui.timer(2.0, poll_tenant_updates)

    initial_space = db.get_space_by_id(my_space_id)
    mall_contacts = db.get_mall_contacts()

    with ui.column().classes("w-full max-w-6xl mx-auto p-6 gap-6"):
        # Верхний заголовок кабинета арендатора
        with ui.row().classes("w-full justify-between items-center"):
            with ui.column().classes("gap-0.5"):
                ui.label(f"Личный кабинет арендатора • Павильон {initial_space['code']}").classes("text-2xl font-bold text-slate-900 tracking-tight")
                ui.label(f"{initial_space['tenant'] or user['display_name']} • {initial_space['floor']} этаж ТЦ").classes("text-sm text-slate-500 font-medium")
            ui.badge(f"Павильон {initial_space['code']}", color="indigo").props("rounded")

        # Верхняя зона: слева миникарта помещения, справа подача заявки и контакты УК
        with ui.row().classes("w-full gap-6 items-start no-wrap"):
            space_info_card()

            with ui.column().classes("w-96 shrink-0 gap-4"):
                # Форма быстрой подачи заявки
                with ui.card().classes("w-full p-5 gap-3 bg-white border border-slate-200/90 shadow-sm rounded-xl").props("flat"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("build", size="sm").classes("text-indigo-600")
                        ui.label("Заявка в эксплуатацию / ремонт").classes("text-base font-bold text-slate-800")

                    with ui.row().classes("w-full gap-2 no-wrap"):
                        category_select = ui.select(
                            options=TICKET_CATEGORIES,
                            value="plumbing",
                            label="Категория",
                        ).classes("flex-1").props("outlined dense")

                        priority_select = ui.select(
                            options={k: v["label"] for k, v in TICKET_PRIORITIES.items()},
                            value="urgent",
                            label="Срочность",
                        ).classes("w-36").props("outlined dense")

                    problem_input = ui.textarea(
                        label="Что случилось?",
                        placeholder="Например: Протекает труба под раковиной в подсобке.",
                    ).classes("w-full").props("outlined dense rows=2")

                    async def handle_ticket_photo(e: events.UploadEventArguments):
                        p_name, p_path = await save_uploaded_file(e)
                        state["ticket_photo"] = (p_name, p_path)
                        ui.notify(f"Фото «{p_name}» прикреплено к заявке", type="info")

                    ticket_uploader = ui.upload(
                        label="Прикрепить фото поломки (необязательно)",
                        auto_upload=True,
                        on_upload=handle_ticket_photo,
                    ).classes("w-full").props("flat bordered dense")

                    def submit_ticket():
                        if not problem_input.value or not problem_input.value.strip():
                            ui.notify("Опишите проблему перед отправкой", type="warning")
                            return
                        p_name, p_path = state["ticket_photo"] if state["ticket_photo"] else ("", "")
                        db.create_ticket(
                            space_id=my_space_id,
                            category=category_select.value,
                            priority=priority_select.value,
                            description=problem_input.value,
                            photo_name=p_name,
                            photo_path=p_path,
                        )
                        problem_input.value = ""
                        state["ticket_photo"] = None
                        ticket_uploader.reset()
                        state["last_sig"] = db.get_sync_signature()
                        my_tickets_card.refresh()
                        update_tenant_tab_labels()
                        ui.notify("Заявка успешно отправлена управляющему!", type="positive")

                    ui.button("Отправить заявку", icon="send", on_click=submit_ticket).classes("w-full mt-1 text-white font-medium").props("color=primary dense")

                # Карточка контактов администрации ТЦ
                with ui.card().classes("w-full p-4 gap-2 bg-indigo-50/50 border border-indigo-200/80 shadow-sm rounded-xl").props("flat"):
                    ui.label("Контакты администрации ТЦ").classes("text-sm font-bold text-slate-800 mb-0.5")

                    with ui.row().classes("items-start gap-2.5 no-wrap"):
                        ui.icon("person", size="xs").classes("text-indigo-700 mt-1")
                        with ui.column().classes("gap-0"):
                            ui.label("Директор ТЦ").classes("text-[11px] text-slate-500 font-medium")
                            ui.label(mall_contacts["director_info"]).classes("text-xs font-semibold text-slate-800")

                    with ui.row().classes("items-start gap-2.5 no-wrap mt-0.5"):
                        ui.icon("support_agent", size="xs").classes("text-indigo-700 mt-1")
                        with ui.column().classes("gap-0"):
                            ui.label("Диспетчерская служба (24/7)").classes("text-[11px] text-slate-500 font-medium")
                            ui.label(mall_contacts["dispatcher_info"]).classes("text-xs font-semibold text-slate-800")

                    with ui.row().classes("items-start gap-2.5 no-wrap mt-0.5"):
                        ui.icon("mail", size="xs").classes("text-indigo-700 mt-1")
                        with ui.column().classes("gap-0"):
                            ui.label("Электронная почта").classes("text-[11px] text-slate-500 font-medium")
                            ui.label(mall_contacts["email"]).classes("text-xs font-semibold text-indigo-700")

        # Нижний блок: Вкладки со счетчиками (Мои заявки на ремонт / Сообщения и связь с УК)
        with ui.card().classes("w-full p-0 bg-white border border-slate-200/90 shadow-sm rounded-xl overflow-hidden").props("flat"):
            with ui.tabs().classes("w-full border-b border-slate-200 bg-slate-50/70 px-4 text-slate-700") as tenant_tabs:
                tenant_tab_tickets = ui.tab("tickets", label="Мои заявки на ремонт", icon="build")
                tenant_tab_messages = ui.tab("messages", label="Сообщения и связь с УК", icon="forum")

            with ui.tab_panels(tenant_tabs, value=tenant_tab_tickets).classes("w-full p-6 bg-white"):
                # Панель 1: Заявки арендатора
                with ui.tab_panel(tenant_tab_tickets):
                    @ui.refreshable
                    def my_tickets_card():
                        my_tickets = db.get_tickets(space_id=my_space_id)
                        if not my_tickets:
                            render_empty_state("assignment_turned_in", "Заявок на ремонт пока нет", "Если в павильоне возникнет неисправность сантехники, электрики или клининга — создайте заявку в форме выше.")
                            return

                        with ui.column().classes("w-full gap-3"):
                            for t in my_tickets:
                                t_meta = TICKET_META[t["status"]]
                                p_meta = TICKET_PRIORITIES.get(t["priority"], TICKET_PRIORITIES["normal"])
                                cat_label = TICKET_CATEGORIES.get(t["category"], "Общий ремонт")

                                with ui.row().classes("w-full justify-between items-start p-4 border border-slate-200 bg-slate-50/50 rounded-xl gap-3"):
                                    with ui.column().classes("gap-1.5 flex-1"):
                                        with ui.row().classes("items-center gap-2 flex-wrap"):
                                            ui.badge(p_meta["label"], color=p_meta["badge"]).props("dense")
                                            ui.badge(cat_label, color="grey").props("outline dense")
                                            ui.label(f"• {t['created_at']}").classes("text-xs text-slate-400 tabular-nums")
                                        ui.label(t["description"]).classes("font-medium text-slate-800 text-sm mt-0.5")

                                        if t.get("photo_name") and os.path.exists(t.get("photo_path", "")):
                                            ui.button(
                                                f"Фотофиксация: {t['photo_name']}",
                                                icon="photo_camera",
                                                on_click=lambda p=t["photo_path"], n=t["photo_name"]: open_photo_preview(p, n),
                                            ).props("dense flat size=sm color=primary").classes("mt-1")

                                    ui.badge(t_meta["label"], color=t_meta["badge"]).props("dense").classes("shrink-0")

                    my_tickets_card()

                # Панель 2: Сообщения арендатора
                with ui.tab_panel(tenant_tab_messages):
                    with ui.row().classes("w-full gap-8 items-start"):
                        # Форма отправки сообщения управляющему
                        with ui.column().classes("w-96 shrink-0 gap-3 p-4 bg-slate-50 rounded-xl border border-slate-200/90"):
                            ui.label("Написать управляющему ТЦ").classes("text-base font-bold text-slate-800")

                            tenant_msg_input = ui.textarea(
                                label="Текст сообщения",
                                placeholder="Например: Направляем показания счетчиков за текущий месяц или новые реквизиты.",
                            ).classes("w-full").props("outlined dense rows=3")

                            async def handle_tenant_upload(e: events.UploadEventArguments):
                                att_name, att_path = await save_uploaded_file(e)
                                state["upload_file"] = (att_name, att_path)
                                ui.notify(f"Файл «{att_name}» прикреплен", type="info")

                            tenant_uploader = ui.upload(
                                label="Прикрепить файл (показания, акт, скан)",
                                auto_upload=True,
                                on_upload=handle_tenant_upload,
                            ).classes("w-full").props("flat bordered dense")

                            def send_tenant_msg():
                                has_file = state["upload_file"] is not None
                                if (not tenant_msg_input.value or not tenant_msg_input.value.strip()) and not has_file:
                                    ui.notify("Введите текст сообщения или прикрепите файл", type="warning")
                                    return

                                att_name, att_path = state["upload_file"] if has_file else ("", "")
                                db.send_message(
                                    sender_role="tenant",
                                    target_space_id=my_space_id,
                                    body=tenant_msg_input.value or "",
                                    attachment_name=att_name,
                                    attachment_path=att_path,
                                )
                                tenant_msg_input.value = ""
                                state["upload_file"] = None
                                tenant_uploader.reset()
                                state["last_sig"] = db.get_sync_signature()
                                tenant_messages_feed.refresh()
                                update_tenant_tab_labels()
                                ui.notify("Сообщение успешно отправлено арендодателю!", type="positive")

                            ui.button("Отправить сообщение", icon="send", on_click=send_tenant_msg).classes("w-full py-2 text-white font-medium").props("color=primary dense")

                        # Лента сообщений
                        with ui.column().classes("flex-1 gap-3"):
                            ui.label("Входящие рассылки и переписка").classes("text-base font-bold text-slate-800")

                            @ui.refreshable
                            def tenant_messages_feed():
                                msgs = db.get_messages_for_tenant(my_space_id)
                                if not msgs:
                                    render_empty_state("mark_email_unread", "Нет входящих сообщений", "Здесь появятся официальные оповещения, напоминания о показаниях счетчиков и ответы управляющей компании.")
                                    return

                                with ui.column().classes("w-full gap-2.5 max-h-[500px] overflow-y-auto pr-1"):
                                    for m in msgs:
                                        is_from_uk = m["sender_role"] == "landlord"
                                        if m["space_id"] == "ALL":
                                            card_bg = "bg-amber-50/70 border-amber-200"
                                            badge_label = "📢 Общая рассылка УК"
                                            badge_color = "orange"
                                        elif is_from_uk:
                                            card_bg = "bg-indigo-50/60 border-indigo-200"
                                            badge_label = "Управляющая компания ТЦ"
                                            badge_color = "indigo"
                                        else:
                                            card_bg = "bg-slate-100/80 border-slate-200"
                                            badge_label = "Вы (Арендатор)"
                                            badge_color = "grey"

                                        with ui.column().classes(f"w-full p-4 border rounded-xl gap-1.5 {card_bg}"):
                                            with ui.row().classes("w-full justify-between items-center"):
                                                ui.badge(badge_label, color=badge_color).props("dense")
                                                ui.label(m["created_at"]).classes("text-xs text-slate-400 tabular-nums")

                                            if m["body"]:
                                                ui.label(m["body"]).classes("text-sm text-slate-800 whitespace-pre-line leading-relaxed")

                                            if m["attachment_name"] and os.path.exists(m["attachment_path"]):
                                                ui.button(
                                                    f"Скачать файл: {m['attachment_name']}",
                                                    icon="attach_file",
                                                    on_click=lambda p=m["attachment_path"], n=m["attachment_name"]: ui.download(p, n),
                                                ).props("dense flat size=sm color=primary").classes("mt-1")

                            tenant_messages_feed()

        update_tenant_tab_labels()


ui.run(
    title="MallService — Вход и управление ТЦ",
    port=8080,
    storage_secret="mallservice_super_secret_key_2026",
)
