import os
from nicegui import app, events, ui
import database as db
from ui_common import (
    PAY_REQ_META,
    TICKET_CATEGORIES,
    TICKET_META,
    TICKET_PRIORITIES,
    open_contract_dialog,
    open_payment_history_dialog,
    open_photo_preview,
    render_header,
    save_uploaded_file,
)


def register_tenant_page():
    @ui.page("/tenant")
    def tenant_page():
        user = app.storage.user.get("user")
        if not user:
            ui.navigate.to("/login")
            return
        if user["role"] != "tenant" or not user["space_id"]:
            ui.navigate.to("/")
            return

        ui.colors(primary="#2563eb")
        render_header(user)

        my_space_id = user["space_id"]
        state = {
            "last_sig": db.get_sync_signature(),
            "upload_file": None,
            "ticket_photo": None,
            "pending_receipts": {},  # {request_id: (file_name, file_path)} — черновик до нажатия "Отправить"
        }

        def build_tenant_mini_map(space: dict) -> str:
            spaces = db.get_spaces_by_floor(space["floor"])
            elements = [
                '<rect x="5" y="5" width="590" height="350" rx="10" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2" />',
                '<rect x="15" y="140" width="570" height="80" rx="6" fill="#e2e8f0" stroke="#94a3b8" stroke-dasharray="6,4" />',
                '<text x="300" y="185" text-anchor="middle" fill="#64748b" font-size="14" font-family="sans-serif" letter-spacing="4">ЦЕНТРАЛЬНЫЙ КОРИДОР</text>',
            ]
            for s in spaces:
                is_mine = s["id"] == space["id"]
                fill = "#2563eb" if is_mine else "#cbd5e1"
                stroke = "#0f172a" if is_mine else "#ffffff"
                stroke_width = "3" if is_mine else "1.5"

                elements.append(
                    f'<rect x="{s["x"]}" y="{s["y"]}" width="{s["w"]}" height="{s["h"]}" rx="6" '
                    f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}" />'
                )
                cx = s["x"] + s["w"] // 2
                cy = s["y"] + s["h"] // 2
                text_color = "#ffffff" if is_mine else "#475569"
                elements.append(
                    f'<text x="{cx}" y="{cy}" text-anchor="middle" fill="{text_color}" font-weight="bold" '
                    f'font-size="15" font-family="sans-serif">{s["code"]}</text>'
                )
                if is_mine:
                    elements.append(
                        f'<text x="{cx}" y="{cy + 20}" text-anchor="middle" fill="#dbeafe" '
                        f'font-size="11" font-family="sans-serif">ВАШЕ ПОМЕЩЕНИЕ</text>'
                    )
            return "".join(elements)

        @ui.refreshable
        def space_info_card():
            space = db.get_space_by_id(my_space_id)
            is_paid_now = space.get("payment_status") == "paid"

            with ui.card().classes("flex-1 p-5 gap-3"):
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label("Расположение на плане ТЦ").classes("text-lg font-bold text-slate-700")
                    with ui.row().classes("gap-2"):
                        ui.button(
                            "История оплат",
                            icon="history",
                            on_click=lambda sp=space: open_payment_history_dialog(sp, is_landlord=False),
                        ).props("outline dense color=secondary")
                        ui.button(
                            "Мой договор аренды",
                            icon="description",
                            on_click=lambda sp=space: open_contract_dialog(sp, is_landlord=False),
                        ).props("outline dense color=primary")

                ui.interactive_image(
                    size=(600, 360),
                    content=build_tenant_mini_map(space),
                ).classes("w-full border border-slate-200 rounded bg-white")

                with ui.row().classes("w-full justify-between items-center bg-slate-100 p-3 rounded-lg mt-2 flex-wrap gap-2"):
                    ui.label(f"Этаж: {space['floor']} • {space['area']} м²").classes("font-medium")
                    ui.label(f"Ставка: {space['price']:,} ₽/мес".replace(",", " ")).classes("font-semibold text-blue-700")
                    with ui.row().classes("items-center gap-1.5"):
                        ui.label(f"Оплата ({db.current_month_str()}):").classes("text-xs text-slate-500")
                        ui.badge("Оплачено" if is_paid_now else "Не оплачено", color="green" if is_paid_now else "orange")

        @ui.refreshable
        def tenant_finance_panel():
            space = db.get_space_by_id(my_space_id)
            pay_requests = db.get_payment_requests(space_id=my_space_id)
            readings = db.get_meter_readings(space_id=my_space_id)

            prev_h = float(space.get("prev_hvs") or 0)
            prev_g = float(space.get("prev_gvs") or 0)
            prev_e = float(space.get("prev_elec") or 0)

            with ui.row().classes("w-full gap-6 items-start no-wrap"):
                # ЛЕВАЯ КОЛОНКА: Формы на оплату от УК (с ручным подтверждением отправки)
                with ui.column().classes("flex-1 gap-3"):
                    ui.label("Счета и акты на оплату от УК").classes("text-lg font-bold text-slate-800")

                    if not pay_requests:
                        ui.label("Актов на оплату от управляющей компании пока нет.").classes("text-sm text-slate-400")
                    else:
                        for pr in pay_requests:
                            st = pr["status"]
                            st_meta = PAY_REQ_META.get(st, PAY_REQ_META["awaiting_payment"])
                            is_late_open = st != "closed" and db.is_due_date_passed(pr["due_date"])
                            is_late_closed = st == "closed" and bool(pr["was_overdue"])

                            if is_late_open:
                                card_cls = "border-red-400 bg-red-50/40"
                            elif st == "under_review":
                                card_cls = "border-blue-300 bg-blue-50/40"
                            elif st == "closed":
                                card_cls = "border-emerald-200 bg-emerald-50/30"
                            else:
                                card_cls = "border-slate-200 bg-slate-50"

                            with ui.column().classes(f"w-full p-3.5 border rounded-lg gap-2 {card_cls}"):
                                with ui.row().classes("w-full justify-between items-start gap-2"):
                                    with ui.row().classes("items-center gap-1.5 flex-wrap"):
                                        ui.badge(f"Форма №{pr['id']}", color="grey-8")
                                        ui.label(f"Период {pr['period']}").classes("font-bold text-slate-800")
                                    with ui.row().classes("items-center gap-1 shrink-0"):
                                        if is_late_open:
                                            ui.badge("ПРОСРОЧЕНО", color="red")
                                        elif is_late_closed:
                                            ui.badge("Оплачено с просрочкой", color="orange")
                                        ui.badge(st_meta["label"], color=st_meta["badge"])

                                ui.label(f"{pr['title']} • Сумма: {pr['amount']:,} ₽".replace(",", " ")).classes("text-sm font-semibold text-slate-800")
                                ui.label(f"Срок оплаты до: {pr['due_date']} • Выставлено: {pr['created_at']}").classes("text-xs text-slate-500")

                                with ui.row().classes("w-full gap-2 flex-wrap items-center"):
                                    if pr.get("bill_file_name") and os.path.exists(pr.get("bill_file_path", "")):
                                        ui.button(
                                            f"Скачать акт УК: {pr['bill_file_name']}",
                                            icon="download",
                                            on_click=lambda p=pr["bill_file_path"], n=pr["bill_file_name"]: ui.download(p, n),
                                        ).props("dense outline size=sm color=primary")

                                    if pr.get("receipt_file_name") and os.path.exists(pr.get("receipt_file_path", "")):
                                        ui.button(
                                            f"Отправленная платежка: {pr['receipt_file_name']}",
                                            icon="receipt",
                                            on_click=lambda p=pr["receipt_file_path"], n=pr["receipt_file_name"]: ui.download(p, n),
                                        ).props("dense flat size=sm color=positive")

                                if st != "closed":
                                    comment_inp = ui.input(
                                        label="Комментарий к платежке (необязательно)",
                                        value=pr.get("tenant_comment") or "",
                                        placeholder="Например: Оплачено п/п №128 от 17.11.2026",
                                    ).classes("w-full bg-white").props("dense outlined")

                                    @ui.refreshable
                                    def draft_status_box(req_id=pr["id"]):
                                        draft = state["pending_receipts"].get(req_id)
                                        if draft:
                                            with ui.row().classes("w-full items-center justify-between px-3 py-1.5 bg-amber-50 border border-amber-300 rounded text-xs"):
                                                with ui.row().classes("items-center gap-1.5"):
                                                    ui.icon("attach_file", color="orange")
                                                    ui.label(f"Выбран файл (не отправлен): {draft[0]}").classes("font-medium text-amber-900")
                                                ui.button(
                                                    "Убрать",
                                                    on_click=lambda r=req_id: (
                                                        state["pending_receipts"].pop(r, None),
                                                        draft_status_box.refresh(),
                                                    ),
                                                ).props("dense flat size=xs color=negative")

                                    draft_status_box()

                                    async def on_receipt_select(e: events.UploadEventArguments, req_id=pr["id"], box=draft_status_box):
                                        fname, fpath = await save_uploaded_file(e)
                                        state["pending_receipts"][req_id] = (fname, fpath)
                                        box.refresh()
                                        ui.notify(f"Файл «{fname}» выбран. Нажмите «Отправить платежку в УК».", type="info")

                                    uploader = ui.upload(
                                        label="Выбрать файл платежного поручения (PDF, скан)",
                                        auto_upload=True,
                                        on_upload=on_receipt_select,
                                    ).classes("w-full").props("flat bordered")

                                    def submit_receipt(req_id=pr["id"], c_inp=comment_inp, up=uploader):
                                        draft = state["pending_receipts"].get(req_id)
                                        if not draft:
                                            ui.notify("Сначала выберите файл платежного поручения", type="warning")
                                            return
                                        fname, fpath = draft
                                        db.attach_payment_receipt(
                                            request_id=req_id,
                                            receipt_file_name=fname,
                                            receipt_file_path=fpath,
                                            tenant_comment=c_inp.value or "",
                                        )
                                        state["pending_receipts"].pop(req_id, None)
                                        up.reset()
                                        state["last_sig"] = db.get_sync_signature()
                                        tenant_finance_panel.refresh()
                                        ui.notify("Платежное поручение отправлено на проверку в УК!", type="positive")

                                    ui.button(
                                        "Отправить платежку в УК",
                                        icon="send",
                                        color="primary",
                                        on_click=submit_receipt,
                                    ).classes("w-full")
                                else:
                                    ui.label(f"Подтверждено УК: {pr.get('closed_at') or ''}").classes("text-xs text-emerald-700 font-medium")

                # ПРАВАЯ КОЛОНКА: Подача показаний счетчиков (ХВС, ГВС, Электроэнергия)
                with ui.column().classes("flex-1 gap-3"):
                    ui.label("Подача показаний счетчиков").classes("text-lg font-bold text-slate-800")

                    period_inp = ui.input(
                        label="Расчетный период",
                        value=db.current_month_str(),
                    ).classes("w-full")

                    with ui.row().classes("w-full gap-2 no-wrap"):
                        hvs_inp = ui.number(
                            label=f"ХВС, м³ (прошл: {prev_h})",
                            value=prev_h,
                            min=prev_h,
                            step=0.5,
                        ).classes("flex-1")

                        gvs_inp = ui.number(
                            label=f"ГВС, м³ (прошл: {prev_g})",
                            value=prev_g,
                            min=prev_g,
                            step=0.5,
                        ).classes("flex-1")

                        elec_inp = ui.number(
                            label=f"Свет, кВт·ч (прошл: {prev_e})",
                            value=prev_e,
                            min=prev_e,
                            step=10,
                        ).classes("flex-1")

                    calc_label = ui.label(
                        f"Тарифы: ХВС {db.HVS_TARIFF} ₽ • ГВС {db.GVS_TARIFF} ₽ • Свет {db.ELEC_TARIFF} ₽ → Переменная часть: 0 ₽"
                    ).classes("text-xs font-semibold text-blue-700 bg-blue-50 p-2.5 rounded w-full")

                    def recalc_preview():
                        ch = float(hvs_inp.value or prev_h)
                        cg = float(gvs_inp.value or prev_g)
                        ce = float(elec_inp.value or prev_e)
                        dh = max(0.0, ch - prev_h)
                        dg = max(0.0, cg - prev_g)
                        de = max(0.0, ce - prev_e)
                        cost = round(dh * db.HVS_TARIFF + dg * db.GVS_TARIFF + de * db.ELEC_TARIFF)
                        calc_label.text = (
                            f"Расход: ХВС +{dh:.1f} м³, ГВС +{dg:.1f} м³, Свет +{de:.1f} кВт·ч → "
                            f"Переменная часть аренды: {cost:,} ₽"
                        ).replace(",", " ")

                    hvs_inp.on_value_change(recalc_preview)
                    gvs_inp.on_value_change(recalc_preview)
                    elec_inp.on_value_change(recalc_preview)

                    def send_readings():
                        ok, msg = db.submit_meter_reading(
                            space_id=my_space_id,
                            period=period_inp.value or "",
                            curr_hvs=float(hvs_inp.value or 0),
                            curr_gvs=float(gvs_inp.value or 0),
                            curr_elec=float(elec_inp.value or 0),
                        )
                        if not ok:
                            ui.notify(msg, type="negative")
                            return
                        state["last_sig"] = db.get_sync_signature()
                        tenant_finance_panel.refresh()
                        ui.notify(msg, type="positive")

                    ui.button("Передать показания в УК", icon="speed", on_click=send_readings).classes("w-full")

                    if readings:
                        ui.label("История переданных показаний").classes("text-sm font-bold text-slate-600 mt-2")
                        for r in readings[:5]:
                            is_acc = r["status"] == "accepted"
                            with ui.row().classes("w-full justify-between items-center p-2.5 border rounded-lg bg-slate-50"):
                                with ui.column().classes("gap-0"):
                                    ui.label(f"Период {r['period']} • Переменная часть: {r['total_cost']:,} ₽".replace(",", " ")).classes("text-sm font-medium")
                                    ui.label(f"ХВС: {r['curr_hvs']} | ГВС: {r['curr_gvs']} | Свет: {r['curr_elec']} • {r['created_at']}").classes("text-xs text-slate-400")
                                ui.badge("Принято УК" if is_acc else "На проверке", color="green" if is_acc else "orange")

        @ui.refreshable
        def my_tickets_card():
            my_tickets = db.get_tickets(space_id=my_space_id)
            with ui.column().classes("w-full gap-2"):
                ui.label("Мои заявки на ремонт").classes("text-lg font-bold text-slate-800 mb-1")
                if not my_tickets:
                    ui.label("Вы еще не отправляли заявок.").classes("text-sm text-slate-500")
                else:
                    for t in my_tickets:
                        t_meta = TICKET_META[t["status"]]
                        p_meta = TICKET_PRIORITIES.get(t["priority"], TICKET_PRIORITIES["normal"])
                        cat_label = TICKET_CATEGORIES.get(t["category"], "Общий ремонт")

                        with ui.row().classes("w-full justify-between items-start p-3 border rounded-lg bg-slate-50 gap-2"):
                            with ui.column().classes("gap-1 flex-1"):
                                with ui.row().classes("items-center gap-1.5 flex-wrap"):
                                    ui.badge(p_meta["label"], color=p_meta["badge"])
                                    ui.badge(cat_label, color="grey").props("outline")
                                    ui.label(f"• {t['created_at']}").classes("text-xs text-slate-400")
                                ui.label(t["description"]).classes("font-medium text-slate-800")

                                if t.get("photo_name") and os.path.exists(t.get("photo_path", "")):
                                    ui.button(
                                        f"Фото: {t['photo_name']}",
                                        icon="photo_camera",
                                        on_click=lambda p=t["photo_path"], n=t["photo_name"]: open_photo_preview(p, n),
                                    ).props("dense flat size=sm color=primary")

                            ui.badge(t_meta["label"], color=t_meta["badge"]).classes("shrink-0")

        @ui.refreshable
        def tenant_messages_feed():
            msgs = db.get_messages_for_tenant(my_space_id)
            if not msgs:
                ui.label("Сообщений и рассылок от управляющей компании пока нет.").classes("text-sm text-slate-400")
                return

            with ui.column().classes("w-full gap-2 max-h-80 overflow-y-auto pr-1"):
                for m in msgs:
                    is_from_uk = m["sender_role"] == "landlord"
                    if m["space_id"] == "ALL":
                        card_bg = "bg-amber-50/80 border-amber-200"
                        badge_label = "📢 Общая рассылка УК"
                        badge_color = "orange"
                    elif is_from_uk:
                        card_bg = "bg-blue-50/70 border-blue-200"
                        badge_label = "Управляющая компания ТЦ"
                        badge_color = "primary"
                    else:
                        card_bg = "bg-slate-100 border-slate-200"
                        badge_label = "Вы (Арендатор)"
                        badge_color = "grey"

                    with ui.column().classes(f"w-full p-3 border rounded-lg gap-1 {card_bg}"):
                        with ui.row().classes("w-full justify-between items-center"):
                            ui.badge(badge_label, color=badge_color)
                            ui.label(m["created_at"]).classes("text-xs text-slate-400")

                        if m["body"]:
                            ui.label(m["body"]).classes("text-sm text-slate-800 whitespace-pre-line")

                        if m["attachment_name"] and os.path.exists(m["attachment_path"]):
                            ui.button(
                                f"Скачать: {m['attachment_name']}",
                                icon="attach_file",
                                on_click=lambda p=m["attachment_path"], n=m["attachment_name"]: ui.download(p, n),
                            ).props("dense flat size=sm color=primary")

        def poll_tenant_updates():
            current_sig = db.get_sync_signature()
            if current_sig != state["last_sig"]:
                if current_sig[1] != state["last_sig"][1] and current_sig[0] == state["last_sig"][0]:
                    ui.notify("Статус вашей заявки обновлен управляющим!", type="info")
                if current_sig[3] > state["last_sig"][3]:
                    ui.notify("Новое сообщение или рассылка от администрации ТЦ!", type="info", icon="mail")
                if current_sig[8] != state["last_sig"][8]:
                    ui.notify("Обновлена форма на оплату от управляющей компании!", type="info", icon="receipt_long")
                state["last_sig"] = current_sig
                space_info_card.refresh()
                my_tickets_card.refresh()
                tenant_messages_feed.refresh()
                # Не сбрасываем панель финансов, если пользователь сейчас держит неприкрепленный черновик
                if not state["pending_receipts"]:
                    tenant_finance_panel.refresh()

        ui.timer(2.0, poll_tenant_updates)

        initial_space = db.get_space_by_id(my_space_id)
        mall_contacts = db.get_mall_contacts()

        with ui.column().classes("w-full max-w-6xl mx-auto p-6 gap-6"):
            with ui.column().classes("gap-0"):
                ui.label(f"Личный кабинет арендатора • Павильон {initial_space['code']}").classes("text-2xl font-bold text-slate-800")
                ui.label(initial_space["tenant"] or user["display_name"]).classes("text-slate-500")

            with ui.row().classes("w-full gap-6 items-start no-wrap"):
                space_info_card()

                with ui.column().classes("w-96 shrink-0 gap-4"):
                    with ui.card().classes("w-full p-5 gap-3"):
                        ui.label("Заявка в эксплуатацию / ремонт").classes("text-lg font-bold text-slate-800")

                        with ui.row().classes("w-full gap-2 no-wrap"):
                            category_select = ui.select(
                                options=TICKET_CATEGORIES,
                                value="plumbing",
                                label="Категория",
                            ).classes("flex-1")

                            priority_select = ui.select(
                                options={k: v["label"] for k, v in TICKET_PRIORITIES.items()},
                                value="urgent",
                                label="Срочность",
                            ).classes("w-36")

                        problem_input = ui.textarea(
                            label="Что случилось?",
                            placeholder="Например: Протекает труба под раковиной в подсобке.",
                        ).classes("w-full").props("rows=2")

                        async def handle_ticket_photo(e: events.UploadEventArguments):
                            p_name, p_path = await save_uploaded_file(e)
                            state["ticket_photo"] = (p_name, p_path)
                            ui.notify(f"Фото «{p_name}» прикреплено к заявке", type="info")

                        ticket_uploader = ui.upload(
                            label="Прикрепить фото поломки (необязательно)",
                            auto_upload=True,
                            on_upload=handle_ticket_photo,
                        ).classes("w-full").props("flat bordered")

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
                            ui.notify("Заявка отправлена арендодателю!", type="positive")

                        ui.button("Отправить заявку", icon="send", on_click=submit_ticket).classes("w-full mt-1")

                    with ui.card().classes("w-full p-5 gap-2 bg-blue-50/60 border border-blue-200"):
                        ui.label("Контакты администрации ТЦ").classes("text-base font-bold text-slate-800 mb-1")

                        with ui.row().classes("items-start gap-2 no-wrap"):
                            ui.icon("person", size="sm").classes("text-blue-700 mt-0.5")
                            with ui.column().classes("gap-0"):
                                ui.label("Директор ТЦ").classes("text-xs text-slate-500")
                                ui.label(mall_contacts["director_info"]).classes("text-sm font-medium text-slate-800")

                        with ui.row().classes("items-start gap-2 no-wrap mt-1"):
                            ui.icon("support_agent", size="sm").classes("text-blue-700 mt-0.5")
                            with ui.column().classes("gap-0"):
                                ui.label("Диспетчерская служба").classes("text-xs text-slate-500")
                                ui.label(mall_contacts["dispatcher_info"]).classes("text-sm font-medium text-slate-800")

                        with ui.row().classes("items-start gap-2 no-wrap mt-1"):
                            ui.icon("mail", size="sm").classes("text-blue-700 mt-0.5")
                            with ui.column().classes("gap-0"):
                                ui.label("Электронная почта").classes("text-xs text-slate-500")
                                ui.label(mall_contacts["email"]).classes("text-sm font-medium text-blue-700")

            # Нижний блок арендатора
            with ui.card().classes("w-full p-5"):
                with ui.tabs().classes("w-full text-slate-700") as t_tabs:
                    t_tab_fin = ui.tab("Формы на оплату и счетчики", icon="payments")
                    t_tab_tickets = ui.tab("Мои заявки на ремонт", icon="build")
                    t_tab_msgs = ui.tab("Связь с арендодателем и рассылки", icon="mail")

                with ui.tab_panels(t_tabs, value=t_tab_fin).classes("w-full mt-3"):
                    with ui.tab_panel(t_tab_fin).classes("p-0"):
                        tenant_finance_panel()

                    with ui.tab_panel(t_tab_tickets).classes("p-0"):
                        my_tickets_card()

                    with ui.tab_panel(t_tab_msgs).classes("p-0"):
                        with ui.row().classes("w-full gap-6 items-start no-wrap"):
                            with ui.column().classes("w-96 shrink-0 gap-3"):
                                ui.label("Написать управляющему").classes("text-lg font-bold text-slate-800")

                                tenant_msg_input = ui.textarea(
                                    label="Сообщение в УК",
                                    placeholder="Например: Запрос на согласование ночного ввоза товара или обновление реквизитов.",
                                ).classes("w-full").props("rows=3")

                                async def handle_tenant_upload(e: events.UploadEventArguments):
                                    att_name, att_path = await save_uploaded_file(e)
                                    state["upload_file"] = (att_name, att_path)
                                    ui.notify(f"Файл «{att_name}» прикреплен", type="info")

                                tenant_uploader = ui.upload(
                                    label="Прикрепить файл",
                                    auto_upload=True,
                                    on_upload=handle_tenant_upload,
                                ).classes("w-full").props("flat bordered")

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
                                    ui.notify("Сообщение отправлено арендодателю!", type="positive")

                                ui.button("Отправить сообщение", icon="mail", on_click=send_tenant_msg).classes("w-full")

                            with ui.column().classes("flex-1 gap-2"):
                                ui.label("Входящие рассылки и переписка").classes("text-lg font-bold text-slate-800")
                                tenant_messages_feed()