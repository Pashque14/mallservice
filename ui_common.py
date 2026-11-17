import os
import time
from nicegui import app, events, ui
import database as db

STATUS_META = {
    "free": {"label": "Свободно", "fill": "#4caf50", "badge": "green"},
    "reserved": {"label": "Бронь", "fill": "#ff9800", "badge": "orange"},
    "occupied": {"label": "Занято", "fill": "#ef5350", "badge": "red"},
}

PAYMENT_META = {
    "paid": {"label": "Оплачено", "badge": "green"},
    "unpaid": {"label": "Не оплачено", "badge": "orange"},
}

PAY_REQ_META = {
    "awaiting_payment": {"label": "Ожидает платежку", "badge": "orange"},
    "under_review": {"label": "Платежка на проверке", "badge": "blue"},
    "closed": {"label": "Оплачено и закрыто", "badge": "green"},
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

DOC_TYPES = {
    "invoice": "Счет на оплату",
    "act": "Акт / УПД",
    "payment_order": "Платежное поручение",
}

PASS_TYPE_META = {
    "cargo_in": {"label": "Ввоз товара", "icon": "move_to_inbox", "badge": "indigo"},
    "cargo_out": {"label": "Вывоз товара", "icon": "outbox", "badge": "purple"},
    "night_work": {"label": "Ночные / монтажные работы", "icon": "nightlight", "badge": "deep-orange"},
}

PASS_STATUS_META = {
    "pending": {"label": "На согласовании", "badge": "orange"},
    "approved": {"label": "Одобрено (Пропуск выдан)", "badge": "green"},
    "rejected": {"label": "Отклонено", "badge": "red"},
}

INSPECTION_CAT_META = {
    "fire_safety": {"label": "Пожарная безопасность", "icon": "local_fire_department", "badge": "red"},
    "sanitary": {"label": "СЭС / чистота", "icon": "cleaning_services", "badge": "teal"},
    "hvac_tech": {"label": "Вентиляция / инженерия", "icon": "hvac", "badge": "blue"},
}

INSPECTION_STATUS_META = {
    "open": {"label": "Выписано предписание", "badge": "orange"},
    "review": {"label": "Отчет на проверке", "badge": "blue"},
    "resolved": {"label": "Устранено", "badge": "green"},
}

PROMO_TYPE_META = {
    "signage": {"label": "Вывеска / оформление витрины", "icon": "storefront", "badge": "indigo"},
    "promo_zone": {"label": "Промо-стойка в галерее", "icon": "assistant_direction", "badge": "purple"},
    "sale_event": {"label": "Акция / распродажа", "icon": "local_offer", "badge": "amber"},
}

MARKETING_STATUS_META = {
    "pending": {"label": "На согласовании", "badge": "orange"},
    "approved": {"label": "Согласовано", "badge": "green"},
    "revision": {"label": "Требуются правки", "badge": "red"},
}

TURNOVER_STATUS_META = {
    "submitted": {"label": "На проверке", "badge": "orange"},
    "accepted": {"label": "Принято УК", "badge": "green"},
}


def logout():
    app.storage.user.clear()
    ui.navigate.to("/login")


async def save_uploaded_file(e: events.UploadEventArguments) -> tuple[str, str]:
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


def render_header(user: dict):
    role_label = "Арендодатель" if user["role"] == "landlord" else "Арендатор"
    with ui.row().classes("w-full bg-slate-900 text-white px-6 py-3 items-center justify-between"):
        with ui.row().classes("items-center gap-3"):
            ui.label("MallService").classes("font-bold text-lg tracking-wide")
            ui.badge(role_label, color="primary")
            ui.badge("LIVE", color="green").props("outline").tooltip("Автообновление каждые 2 сек")

        with ui.row().classes("items-center gap-4"):
            ui.label(user["display_name"]).classes("text-sm text-slate-300")
            ui.button("Выйти", icon="logout", on_click=logout).props("flat color=white dense")


def open_photo_preview(photo_path: str, photo_name: str):
    with ui.dialog() as dialog, ui.card().classes("max-w-2xl w-full p-4 gap-3"):
        with ui.row().classes("w-full justify-between items-center"):
            ui.label(f"Фото: {photo_name}").classes("font-bold text-slate-800")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")

        ext = os.path.splitext(photo_name)[1].lower()
        if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            ui.image(photo_path).classes("w-full rounded border")
        else:
            ui.label("Предпросмотр доступен только для изображений. Вы можете скачать файл:").classes("text-sm text-slate-600")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Скачать файл", icon="download", on_click=lambda: ui.download(photo_path, photo_name)).props("outline")
            ui.button("Закрыть", on_click=dialog.close)
    dialog.open()


def open_payment_history_dialog(space: dict, is_landlord: bool, on_updated=None):
    """Всплывающее окно с помесячной историей оплат и отметками о просрочке"""
    with ui.dialog() as dialog, ui.card().classes("max-w-2xl w-full p-6 gap-4"):
        with ui.row().classes("w-full justify-between items-center"):
            with ui.column().classes("gap-0"):
                ui.label(f"История платежей и просрочек • Павильон {space['code']}").classes("text-xl font-bold text-slate-800")
                ui.label(f"{space['tenant'] or 'Арендатор не указан'} • Ставка {space['price']:,} ₽/мес".replace(",", " ")).classes("text-xs text-slate-500")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")

        ui.separator()

        @ui.refreshable
        def history_list():
            records = db.get_rent_payments(space["id"])
            unpaid_ov, paid_ov = db.get_payment_history_stats(space["id"])

            with ui.row().classes("w-full gap-2 items-center bg-slate-50 p-3 rounded-lg border flex-wrap"):
                ui.badge(f"Всего месяцев в истории: {len(records)}", color="primary")
                ui.badge(f"Оплачено с просрочкой: {paid_ov}", color="orange" if paid_ov else "grey")
                ui.badge(f"Неоплаченных просрочек: {unpaid_ov}", color="red" if unpaid_ov else "green")

            if not records:
                ui.label("Помесячная история платежей пока не заполнена.").classes("text-sm text-slate-500 py-2")
            else:
                with ui.column().classes("w-full gap-2 max-h-72 overflow-y-auto pr-1"):
                    for rec in records:
                        is_paid = bool(rec["is_paid"])
                        was_ov = bool(rec["was_overdue"])

                        if is_paid and not was_ov:
                            st_label = "Оплачено вовремя"
                            st_color = "green"
                            row_bg = "bg-emerald-50/40 border-emerald-200"
                        elif is_paid and was_ov:
                            st_label = "Оплачено с просрочкой"
                            st_color = "orange"
                            row_bg = "bg-amber-50/60 border-amber-300"
                        elif not is_paid and was_ov:
                            st_label = "Не оплачено (просрочка)"
                            st_color = "red"
                            row_bg = "bg-red-50/60 border-red-300"
                        else:
                            st_label = "Не оплачено (в срок)"
                            st_color = "grey"
                            row_bg = "bg-slate-50 border-slate-200"

                        with ui.row().classes(f"w-full items-center justify-between p-3 border rounded-lg gap-2 {row_bg}"):
                            with ui.column().classes("gap-0.5"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.label(f"Период: {rec['period']}").classes("font-bold text-slate-800")
                                    ui.label(f"• {rec['amount']:,} ₽".replace(",", " ")).classes("text-sm font-medium text-slate-700")
                                details = []
                                if is_paid and rec.get("paid_date"):
                                    details.append(f"Дата оплаты: {rec['paid_date']}")
                                if rec.get("note"):
                                    details.append(rec["note"])
                                if details:
                                    ui.label(" • ".join(details)).classes("text-xs text-slate-500")

                            with ui.row().classes("items-center gap-1.5 shrink-0"):
                                ui.badge(st_label, color=st_color)
                                if is_landlord:
                                    if not is_paid:
                                        ui.button(
                                            "Вовремя",
                                            color="positive",
                                            on_click=lambda r=rec: (
                                                db.save_rent_payment_record(space["id"], r["period"], r["amount"], True, False, "", r["note"]),
                                                history_list.refresh(),
                                                on_updated() if on_updated else None,
                                            ),
                                        ).props("dense size=sm").tooltip("Зачесть оплату вовремя")
                                        ui.button(
                                            "С просрочкой",
                                            color="warning",
                                            on_click=lambda r=rec: (
                                                db.save_rent_payment_record(space["id"], r["period"], r["amount"], True, True, "", r["note"] or "Оплачено с просрочкой"),
                                                history_list.refresh(),
                                                on_updated() if on_updated else None,
                                            ),
                                        ).props("dense size=sm").tooltip("Зачесть оплату, но зафиксировать просрочку")
                                        if not was_ov:
                                            ui.button(
                                                "Долг",
                                                color="negative",
                                                on_click=lambda r=rec: (
                                                    db.save_rent_payment_record(space["id"], r["period"], r["amount"], False, True, "", r["note"] or "Просрочка платежа"),
                                                    history_list.refresh(),
                                                    on_updated() if on_updated else None,
                                                ),
                                            ).props("dense outline size=sm")
                                    else:
                                        ui.button(
                                            "Сменить флаг просрочки",
                                            on_click=lambda r=rec: (
                                                db.save_rent_payment_record(space["id"], r["period"], r["amount"], True, not bool(r["was_overdue"]), r["paid_date"], r["note"]),
                                                history_list.refresh(),
                                                on_updated() if on_updated else None,
                                            ),
                                        ).props("dense flat size=sm color=primary")

        history_list()

        if is_landlord:
            ui.separator()
            ui.label("Добавить / обновить запись за месяц").classes("text-sm font-bold text-slate-700")
            with ui.row().classes("w-full gap-2 items-center no-wrap"):
                p_inp = ui.input(label="Месяц (ММ.ГГГГ)", value=db.current_month_str()).classes("w-36")
                st_sel = ui.select(
                    options={
                        "paid_ok": "Оплачено вовремя",
                        "paid_late": "Оплачено с просрочкой",
                        "unpaid_late": "Не оплачено (просрочка)",
                        "unpaid_ok": "Не оплачено",
                    },
                    value="paid_late",
                    label="Статус месяца",
                ).classes("flex-1")
                note_inp = ui.input(label="Примечание", placeholder="Например: задержка 5 дней").classes("flex-1")

            def add_history_entry():
                val = st_sel.value
                is_p = val in {"paid_ok", "paid_late"}
                was_o = val in {"paid_late", "unpaid_late"}
                db.save_rent_payment_record(
                    space_id=space["id"],
                    period=p_inp.value or db.current_month_str(),
                    amount=space["price"],
                    is_paid=is_p,
                    was_overdue=was_o,
                    note=note_inp.value or "",
                )
                note_inp.value = ""
                history_list.refresh()
                if on_updated:
                    on_updated()
                ui.notify("Запись в истории платежей сохранена", type="positive")

            with ui.row().classes("w-full justify-between items-center mt-1"):
                ui.button("Сохранить в историю", icon="add_task", on_click=add_history_entry)
                ui.button("Закрыть", on_click=dialog.close).props("flat")
        else:
            with ui.row().classes("w-full justify-end mt-1"):
                ui.button("Закрыть", on_click=dialog.close)

    dialog.open()


def open_contract_dialog(space: dict, is_landlord: bool, on_saved=None):
    is_free = space["status"] == "free"

    with ui.dialog() as dialog, ui.card().classes("max-w-2xl w-full p-6 gap-4"):
        with ui.row().classes("w-full justify-between items-center"):
            title = (
                f"Шаблон договора аренды • Павильон {space['code']}"
                if is_free
                else f"Договор аренды • Павильон {space['code']}"
            )
            ui.label(title).classes("text-xl font-bold text-slate-800")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")

        ui.separator()

        if is_free:
            ui.label("Помещение сейчас свободно. Ниже представлен типовой шаблон договора с подставленными параметрами павильона:").classes("text-sm text-slate-600")

            template_preview = (
                f"ТИПОВОЙ ДОГОВОР АРЕНДЫ НЕЖИЛОГО ПОМЕЩЕНИЯ № ___/2026\n\n"
                f"Объект аренды: Павильон {space['code']}, {space['floor']} этаж ТЦ\n"
                f"Общая площадь помещения: {space['area']} м²\n"
                f"Базовая арендная ставка: {space['price']:,} ₽/мес (вкл. НДС / УСН)\n"
                f"-------------------------------------------------------------------\n"
                f"1. Арендодатель передает, а Арендатор принимает во временное владение и пользование "
                f"указанное нежилое помещение для осуществления коммерческой деятельности.\n"
                f"2. Оплата производится ежемесячно авансом не позднее 5-го числа расчетного месяца.\n"
                f"3. Коммунальные платежи (ХВС, ГВС, электроэнергия) оплачиваются отдельно по приборам учета.\n"
                f"4. Передача помещения оформляется Актом приема-передачи в день подписания договора."
            ).replace(",", " ")

            ui.textarea(value=template_preview).classes("w-full font-mono text-xs bg-slate-50").props("readonly rows=12 outlined")

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                if os.path.exists(db.TEMPLATE_CONTRACT_PATH):
                    ui.button(
                        "Скачать файл шаблона (.txt)",
                        icon="download",
                        on_click=lambda: ui.download(db.TEMPLATE_CONTRACT_PATH, f"Шаблон_договора_{space['code']}.txt"),
                    ).props("outline")
                ui.button("Закрыть", on_click=dialog.close)

        else:
            uploaded_contract = {"data": None}

            with ui.row().classes("w-full gap-4 bg-slate-50 p-3 rounded-lg border"):
                ui.label(f"Арендатор: {space['tenant'] or 'Не указан'}").classes("font-semibold text-slate-800")
                ui.space()
                ui.label(f"{space['area']} м² • {space['price']:,} ₽/мес".replace(",", " ")).classes("text-sm text-slate-600")

            if is_landlord:
                num_input = ui.input(
                    label="Номер договора",
                    value=space.get("contract_number") or "",
                    placeholder="Например: № 01-А/2026",
                ).classes("w-full")

                end_input = ui.input(
                    label="Срок действия договора (до)",
                    value=space.get("contract_end_date") or "",
                    placeholder="Например: 31.12.2026",
                ).classes("w-full")

                @ui.refreshable
                def current_file_box():
                    fname = space.get("contract_file_name") or ""
                    fpath = space.get("contract_file_path") or ""
                    if uploaded_contract["data"]:
                        ui.badge(f"Новый файл готов к сохранению: {uploaded_contract['data'][0]}", color="green")
                    elif fname and os.path.exists(fpath):
                        with ui.row().classes("w-full items-center justify-between p-2.5 bg-blue-50 border border-blue-200 rounded"):
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("description", color="primary")
                                ui.label(fname).classes("text-sm font-medium text-slate-800")
                            ui.button(
                                "Скачать договор",
                                icon="download",
                                on_click=lambda: ui.download(fpath, fname),
                            ).props("dense flat color=primary")
                    else:
                        ui.label("Скан/файл договора еще не загружен.").classes("text-xs text-slate-400")

                current_file_box()

                async def on_contract_upload(e: events.UploadEventArguments):
                    c_name, c_path = await save_uploaded_file(e)
                    uploaded_contract["data"] = (c_name, c_path)
                    current_file_box.refresh()
                    ui.notify(f"Файл договора «{c_name}» загружен", type="info")

                ui.upload(
                    label="Загрузить новый файл договора (PDF, DOCX, скан)",
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
                    ui.button("Отмена", on_click=dialog.close).props("flat")
                    ui.button("Сохранить договор", icon="save", on_click=save_contract)

            else:
                c_num = space.get("contract_number") or "Не указан"
                c_end = space.get("contract_end_date") or "Не указан"
                fname = space.get("contract_file_name") or ""
                fpath = space.get("contract_file_path") or ""

                with ui.column().classes("w-full gap-2 p-3 border rounded-lg"):
                    ui.label(f"Номер договора: {c_num}").classes("font-medium text-slate-800")
                    ui.label(f"Действует до: {c_end}").classes("text-sm text-slate-600")

                if fname and os.path.exists(fpath):
                    with ui.row().classes("w-full items-center justify-between p-3 bg-blue-50 border border-blue-200 rounded-lg"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("description", color="primary")
                            ui.label(fname).classes("text-sm font-medium text-slate-800")
                        ui.button(
                            "Скачать скан договора",
                            icon="download",
                            on_click=lambda: ui.download(fpath, fname),
                        ).props("dense color=primary")
                else:
                    ui.label("Электронная копия договора еще не прикреплена управляющей компанией.").classes("text-sm text-slate-500")

                with ui.row().classes("w-full justify-end mt-2"):
                    ui.button("Закрыть", on_click=dialog.close)

    dialog.open()