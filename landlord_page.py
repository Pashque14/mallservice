import os
from datetime import datetime, timedelta
from nicegui import app, events, ui
import database as db
from ui_common import (
    PAYMENT_META,
    PAY_REQ_META,
    STATUS_META,
    TICKET_CATEGORIES,
    TICKET_META,
    TICKET_PRIORITIES,
    open_contract_dialog,
    open_payment_history_dialog,
    open_photo_preview,
    render_header,
    save_uploaded_file,
)


def register_landlord_page():
    @ui.page("/")
    def landlord_page():
        user = app.storage.user.get("user")
        if not user:
            ui.navigate.to("/login")
            return
        if user["role"] != "landlord":
            ui.navigate.to("/tenant")
            return

        ui.colors(primary="#2563eb")
        render_header(user)

        state = {
            "floor": 1,
            "selected_id": None,
            "last_sig": db.get_sync_signature(),
            "upload_file": None,
            "bill_file": None,
        }

        def build_floor_svg(floor: int) -> str:
            spaces = db.get_spaces_by_floor(floor)
            alert_spaces = db.get_active_ticket_alerts()
            overdue_spaces = db.get_overdue_space_ids()

            elements = [
                '<rect x="5" y="5" width="590" height="350" rx="10" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2" />',
                '<rect x="15" y="140" width="570" height="80" rx="6" fill="#e2e8f0" stroke="#94a3b8" stroke-dasharray="6,4" />',
                '<text x="300" y="185" text-anchor="middle" fill="#64748b" font-size="14" font-family="sans-serif" letter-spacing="4">ЦЕНТРАЛЬНЫЙ КОРИДОР</text>',
            ]

            for s in spaces:
                is_selected = s["id"] == state["selected_id"]
                alert_priority = alert_spaces.get(s["id"])
                is_overdue = s["status"] != "free" and s["id"] in overdue_spaces
                fill = STATUS_META[s["status"]]["fill"]
                stroke = "#0f172a" if is_selected else "#ffffff"
                stroke_width = "4" if is_selected else "2"

                elements.append(
                    f'<rect x="{s["x"]}" y="{s["y"]}" width="{s["w"]}" height="{s["h"]}" rx="6" '
                    f'fill="{fill}" fill-opacity="0.9" stroke="{stroke}" stroke-width="{stroke_width}" />'
                )

                cx = s["x"] + s["w"] // 2
                cy = s["y"] + s["h"] // 2

                elements.append(
                    f'<text x="{cx}" y="{cy - 14}" text-anchor="middle" fill="#ffffff" font-weight="bold" '
                    f'font-size="16" font-family="sans-serif">{s["code"]}</text>'
                )
                elements.append(
                    f'<text x="{cx}" y="{cy + 6}" text-anchor="middle" fill="#ffffff" '
                    f'font-size="12" font-family="sans-serif">{s["area"]} м²</text>'
                )

                tenant_label = s["tenant"] if s["tenant"] else STATUS_META[s["status"]]["label"]
                if len(tenant_label) > 18:
                    tenant_label = tenant_label[:16] + "…"
                elements.append(
                    f'<text x="{cx}" y="{cy + 26}" text-anchor="middle" fill="#f1f5f9" '
                    f'font-size="11" font-family="sans-serif">{tenant_label}</text>'
                )

                if alert_priority:
                    bx, by = s["x"] + s["w"] - 18, s["y"] + 18
                    is_urgent = alert_priority == "urgent"
                    badge_fill = "#dc2626" if is_urgent else "#facc15"
                    badge_stroke = "#ffffff" if is_urgent else "#0f172a"
                    text_fill = "#ffffff" if is_urgent else "#0f172a"
                    elements.append(f'<circle cx="{bx}" cy="{by}" r="11" fill="{badge_fill}" stroke="{badge_stroke}" stroke-width="2" />')
                    elements.append(
                        f'<text x="{bx}" y="{by + 4}" text-anchor="middle" fill="{text_fill}" font-weight="bold" '
                        f'font-size="13" font-family="sans-serif">!</text>'
                    )

                if is_overdue:
                    px, py = s["x"] + 18, s["y"] + 18
                    elements.append(f'<circle cx="{px}" cy="{py}" r="11" fill="#1e1b4b" stroke="#ffffff" stroke-width="1.5" />')
                    elements.append(
                        f'<text x="{px}" y="{py + 4}" text-anchor="middle" fill="#fde047" font-weight="bold" '
                        f'font-size="12" font-family="sans-serif">₽</text>'
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

        def refresh_all(update_inspector: bool = False):
            state["last_sig"] = db.get_sync_signature()
            map_view.content = build_floor_svg(state["floor"])
            floor_buttons.refresh()
            stats_bar.refresh()
            tickets_panel.refresh()
            messages_feed.refresh()
            finance_panel.refresh()
            if update_inspector:
                inspector_panel.refresh()

        def poll_updates():
            current_sig = db.get_sync_signature()
            if current_sig != state["last_sig"]:
                if current_sig[0] > state["last_sig"][0]:
                    ui.notify("Поступила новая заявка на ремонт!", type="warning", icon="build")
                if current_sig[3] > state["last_sig"][3]:
                    ui.notify("Новое сообщение в чате с арендаторами!", type="info", icon="mail")
                if current_sig[5] != state["last_sig"][5]:
                    ui.notify("Поступили новые показания счетчиков!", type="info", icon="speed")
                if current_sig[8] != state["last_sig"][8]:
                    ui.notify("Арендатор отправил платежку по форме оплаты!", type="positive", icon="receipt_long")
                refresh_all(update_inspector=False)

        ui.timer(2.0, poll_updates)

        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-5"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("Карта площадей и управление ТЦ").classes("text-2xl font-bold text-slate-800")

                @ui.refreshable
                def floor_buttons():
                    with ui.button_group():
                        for f in (1, 2):
                            btn = ui.button(f"{f} этаж", on_click=lambda fl=f: on_floor_change(fl))
                            if state["floor"] != f:
                                btn.props("outline")

                floor_buttons()

            @ui.refreshable
            def stats_bar():
                spaces = db.get_spaces_by_floor(state["floor"])
                free_cnt = sum(1 for s in spaces if s["status"] == "free")
                res_cnt = sum(1 for s in spaces if s["status"] == "reserved")
                occ_cnt = sum(1 for s in spaces if s["status"] == "occupied")
                total_income = sum(s["price"] for s in spaces if s["status"] == "occupied")
                paid_income = sum(s["price"] for s in spaces if s["status"] == "occupied" and s.get("payment_status") == "paid")

                with ui.row().classes("gap-4 items-center text-sm bg-slate-100 p-3 rounded-lg w-full flex-wrap"):
                    ui.label(f"Этаж {state['floor']}").classes("font-bold text-base mr-2")
                    ui.badge(f"Свободно: {free_cnt}", color="green")
                    ui.badge(f"Бронь: {res_cnt}", color="orange")
                    ui.badge(f"Занято: {occ_cnt}", color="red")
                    ui.space()
                    ui.label(
                        f"Оплачено за {db.current_month_str()}: {paid_income:,} из {total_income:,} ₽".replace(",", " ")
                    ).classes("font-semibold text-base text-slate-800")

            stats_bar()

            with ui.row().classes("w-full gap-6 items-start no-wrap"):
                with ui.card().classes("flex-1 p-3 bg-slate-50"):
                    map_view = ui.interactive_image(
                        size=(600, 360),
                        content=build_floor_svg(state["floor"]),
                        on_mouse=on_map_mouse,
                        events=["click"],
                    ).classes("w-full border border-slate-300 rounded bg-white cursor-pointer")

                @ui.refreshable
                def inspector_panel():
                    with ui.card().classes("w-96 shrink-0 p-5"):
                        sid = state["selected_id"]
                        if not sid:
                            ui.label("Карточка помещения").classes("text-lg font-bold text-slate-700")
                            ui.label("Нажмите на любой павильон на схеме слева, чтобы посмотреть параметры, договор, статус оплаты или изменить данные.").classes("text-sm text-slate-500 mt-2")
                            return

                        space = db.get_space_by_id(sid)
                        meta = STATUS_META[space["status"]]
                        is_free = space["status"] == "free"

                        with ui.row().classes("w-full justify-between items-center"):
                            ui.label(f"Павильон {space['code']}").classes("text-xl font-bold")
                            ui.badge(meta["label"], color=meta["badge"])

                        ui.label(f"Этаж: {space['floor']} • Площадь: {space['area']} м²").classes("text-sm text-slate-500 mb-2")

                        if is_free:
                            ui.button(
                                "Шаблон договора аренды",
                                icon="description",
                                on_click=lambda sp=space: open_contract_dialog(sp, is_landlord=True),
                            ).classes("w-full mb-2").props("outline color=secondary")
                        else:
                            has_file = bool(space.get("contract_file_name"))
                            c_num = space.get("contract_number") or "Без номера"
                            btn_label = f"Договор ({c_num})" if not has_file else f"Договор ({c_num}) • Файл"
                            with ui.row().classes("w-full gap-2 mb-2 no-wrap"):
                                ui.button(
                                    btn_label,
                                    icon="folder_shared",
                                    on_click=lambda sp=space: open_contract_dialog(
                                        sp, is_landlord=True, on_saved=lambda: refresh_all(update_inspector=True)
                                    ),
                                ).classes("flex-1").props("outline color=primary")

                                ui.button(
                                    "История",
                                    icon="history",
                                    on_click=lambda sp=space: open_payment_history_dialog(
                                        sp, is_landlord=True, on_updated=lambda: refresh_all(update_inspector=True)
                                    ),
                                ).props("outline color=secondary")

                        ui.separator()

                        status_select = ui.select(
                            options={k: v["label"] for k, v in STATUS_META.items()},
                            value=space["status"],
                            label="Статус помещения",
                        ).classes("w-full mt-2")

                        tenant_input = ui.input(
                            label="Арендатор / Бренд",
                            value=space["tenant"] or "",
                            placeholder="Например: Кофейня",
                        ).classes("w-full")

                        with ui.row().classes("w-full gap-2 no-wrap"):
                            price_input = ui.number(
                                label="Ставка (₽/мес)",
                                value=space["price"],
                                step=5000,
                            ).classes("flex-1")

                            cur_pay = space.get("payment_status") if space.get("payment_status") in PAYMENT_META else "unpaid"
                            pay_select = ui.select(
                                options={k: v["label"] for k, v in PAYMENT_META.items()},
                                value=cur_pay,
                                label=f"Оплата ({db.current_month_str()})",
                            ).classes("w-40")

                        ui.label("Контакты руководства точки").classes("text-xs font-bold uppercase tracking-wider text-slate-500 mt-3")

                        point_dir_input = ui.input(
                            label="Директор точки",
                            value=space["point_director"] or "",
                            placeholder="ФИО, телефон",
                        ).classes("w-full")

                        area_dir_input = ui.input(
                            label="Вышестоящий директор (если есть)",
                            value=space["area_director"] or "",
                            placeholder="ФИО, телефон (необязательно)",
                        ).classes("w-full")

                        ui.label("Служебная информация (видит только УК)").classes("text-xs font-bold uppercase tracking-wider text-amber-700 mt-3")

                        notes_input = ui.textarea(
                            label="Внутренние заметки арендодателя",
                            value=space["internal_notes"] or "",
                            placeholder="История переговоров, скидки, технические особенности точки...",
                        ).classes("w-full bg-amber-50/50").props("rows=2")

                        def save_changes():
                            db.update_space(
                                space_id=sid,
                                status=status_select.value,
                                tenant=tenant_input.value,
                                price=int(price_input.value or 0),
                                point_director=point_dir_input.value,
                                area_director=area_dir_input.value,
                                internal_notes=notes_input.value,
                                payment_status=pay_select.value,
                            )
                            ui.notify(f"Павильон {space['code']} обновлен", type="positive")
                            refresh_all(update_inspector=True)

                        ui.button("Сохранить изменения", on_click=save_changes).classes("w-full mt-3")

                inspector_panel()

            # Нижний блок: 3 вкладки
            with ui.card().classes("w-full p-5"):
                with ui.tabs().classes("w-full text-slate-700") as tabs:
                    tab_fin = ui.tab("Оплата, формы счетов и счетчики", icon="payments")
                    tab_tickets = ui.tab("Заявки на ремонт", icon="build")
                    tab_msgs = ui.tab("Сообщения и рассылки", icon="mail")

                with ui.tab_panels(tabs, value=tab_fin).classes("w-full mt-3"):
                    # --- ВКЛАДКА 1: ФОРМЫ НА ОПЛАТУ, СВОДКА МЕСЯЦА И СЧЕТЧИКИ ---
                    with ui.tab_panel(tab_fin).classes("p-0"):
                        @ui.refreshable
                        def finance_panel():
                            all_spaces = [s for s in db.get_all_spaces() if s["status"] != "free"]
                            pay_requests = db.get_payment_requests()
                            readings = db.get_meter_readings()

                            review_cnt = sum(1 for pr in pay_requests if pr["status"] == "under_review")
                            overdue_cnt = sum(1 for pr in pay_requests if pr["status"] != "closed" and db.is_due_date_passed(pr["due_date"]))

                            with ui.row().classes("w-full gap-6 items-start no-wrap"):
                                # ЛЕВАЯ КОЛОНКА: Создание формы на оплату + Лента форм
                                with ui.column().classes("flex-1 gap-4"):
                                    ui.label("Выставить акт / счет на оплату (создать форму)").classes("text-lg font-bold text-slate-800")

                                    space_opts = {s["id"]: f"Павильон {s['code']} — {s['tenant']}" for s in all_spaces}
                                    first_sid = next(iter(space_opts), None)
                                    default_amount = next((s["price"] for s in all_spaces if s["id"] == first_sid), 0)
                                    default_due = (datetime.now() + timedelta(days=5)).strftime("%d.%m.%Y")

                                    with ui.row().classes("w-full gap-2 no-wrap"):
                                        req_space_sel = ui.select(options=space_opts, value=first_sid, label="Арендатор").classes("flex-1")
                                        req_period_inp = ui.input(label="Период (ММ.ГГГГ)", value=db.current_month_str()).classes("w-36")

                                    with ui.row().classes("w-full gap-2 no-wrap"):
                                        req_amount_inp = ui.number(label="Сумма к оплате (₽)", value=default_amount, step=1000).classes("flex-1")
                                        req_due_inp = ui.input(
                                            label="Срок оплаты (ДД.ММ.ГГГГ)",
                                            value=default_due,
                                            placeholder="Например: 25.11.2026",
                                        ).classes("w-44")

                                    def on_req_space_change():
                                        sp = db.get_space_by_id(req_space_sel.value) if req_space_sel.value else None
                                        if sp:
                                            req_amount_inp.value = sp["price"]

                                    req_space_sel.on_value_change(on_req_space_change)

                                    req_title_inp = ui.input(
                                        label="Назначение платежа / название акта",
                                        placeholder="Например: Акт на оплату аренды и коммунальных услуг (Ноябрь 2026)",
                                    ).classes("w-full")

                                    async def on_bill_upload(e: events.UploadEventArguments):
                                        fname, fpath = await save_uploaded_file(e)
                                        state["bill_file"] = (fname, fpath)
                                        ui.notify(f"Акт на оплату «{fname}» прикреплен", type="info")

                                    bill_uploader = ui.upload(
                                        label="Прикрепить акт / счет на оплату (PDF, Excel, скан)",
                                        auto_upload=True,
                                        on_upload=on_bill_upload,
                                    ).classes("w-full").props("flat bordered")

                                    def create_bill_form():
                                        if not req_space_sel.value:
                                            ui.notify("Выберите арендатора", type="warning")
                                            return
                                        fname, fpath = state["bill_file"] if state["bill_file"] else ("", "")
                                        db.create_payment_request(
                                            space_id=req_space_sel.value,
                                            period=req_period_inp.value or db.current_month_str(),
                                            title=req_title_inp.value or f"Акт на оплату за {req_period_inp.value or db.current_month_str()}",
                                            amount=int(req_amount_inp.value or 0),
                                            due_date=req_due_inp.value or default_due,
                                            bill_file_name=fname,
                                            bill_file_path=fpath,
                                        )
                                        req_title_inp.value = ""
                                        state["bill_file"] = None
                                        bill_uploader.reset()
                                        refresh_all(update_inspector=True)
                                        ui.notify("Форма на оплату создана и отправлена арендатору!", type="positive")

                                    ui.button("Создать форму на оплату", icon="post_add", on_click=create_bill_form).classes("w-full")

                                    ui.separator()

                                    with ui.row().classes("items-center gap-2"):
                                        ui.label("Формы на оплату (реестр)").classes("text-lg font-bold text-slate-800")
                                        if review_cnt:
                                            ui.badge(f"На проверке: {review_cnt}", color="blue")
                                        if overdue_cnt:
                                            ui.badge(f"Просрочено: {overdue_cnt}", color="red")

                                    if not pay_requests:
                                        ui.label("Форм на оплату пока нет.").classes("text-sm text-slate-400")
                                    else:
                                        with ui.column().classes("w-full gap-2.5 max-h-[460px] overflow-y-auto pr-1"):
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

                                                with ui.column().classes(f"w-full p-3 border rounded-lg gap-2 {card_cls}"):
                                                    with ui.row().classes("w-full justify-between items-start gap-2"):
                                                        with ui.row().classes("items-center gap-1.5 flex-wrap"):
                                                            ui.badge(f"№{pr['id']}", color="grey-8")
                                                            ui.badge(f"Павильон {pr['space_code']}", color="primary")
                                                            ui.label(pr["tenant_name"]).classes("font-semibold text-slate-800")
                                                            ui.label(f"• Период {pr['period']}").classes("text-xs text-slate-500")

                                                        with ui.row().classes("items-center gap-1 shrink-0"):
                                                            if is_late_open:
                                                                ui.badge("ПРОСРОЧЕНО", color="red")
                                                            elif is_late_closed:
                                                                ui.badge("Закрыто с просрочкой", color="orange")
                                                            ui.badge(st_meta["label"], color=st_meta["badge"])

                                                    ui.label(
                                                        f"{pr['title']} — {pr['amount']:,} ₽ • Срок оплаты до: {pr['due_date']}".replace(",", " ")
                                                    ).classes("text-sm text-slate-800 font-medium")

                                                    with ui.row().classes("w-full gap-2 flex-wrap items-center"):
                                                        if pr.get("bill_file_name") and os.path.exists(pr.get("bill_file_path", "")):
                                                            ui.button(
                                                                f"Акт УК: {pr['bill_file_name']}",
                                                                icon="description",
                                                                on_click=lambda p=pr["bill_file_path"], n=pr["bill_file_name"]: ui.download(p, n),
                                                            ).props("dense outline size=sm color=primary")

                                                        if pr.get("receipt_file_name") and os.path.exists(pr.get("receipt_file_path", "")):
                                                            ui.button(
                                                                f"Платежка арендатора: {pr['receipt_file_name']}",
                                                                icon="receipt",
                                                                on_click=lambda p=pr["receipt_file_path"], n=pr["receipt_file_name"]: ui.download(p, n),
                                                            ).props("dense size=sm color=positive")
                                                        elif st != "closed":
                                                            ui.label("Платежное поручение еще не отправлено арендатором").classes("text-xs text-slate-400 italic")

                                                    if pr.get("tenant_comment"):
                                                        ui.label(f"Комментарий арендатора: «{pr['tenant_comment']}»").classes("text-xs text-slate-600 bg-white/80 p-2 rounded border")

                                                    if st != "closed":
                                                        with ui.row().classes("w-full justify-end gap-2 pt-1"):
                                                            if st == "under_review":
                                                                ui.button(
                                                                    "Вернуть на доработку",
                                                                    color="warning",
                                                                    on_click=lambda rid=pr["id"]: (
                                                                        db.return_payment_request_to_tenant(rid),
                                                                        refresh_all(),
                                                                        ui.notify("Форма возвращена арендатору", type="warning"),
                                                                    ),
                                                                ).props("dense outline size=sm")

                                                            ui.button(
                                                                "Подтвердить и закрыть форму",
                                                                icon="check_circle",
                                                                color="positive",
                                                                on_click=lambda rid=pr["id"]: (
                                                                    db.close_payment_request(rid),
                                                                    refresh_all(update_inspector=True),
                                                                    ui.notify("Оплата подтверждена, форма закрыта!", type="positive"),
                                                                ),
                                                            ).props("dense size=sm")
                                                    else:
                                                        ui.label(f"Закрыто: {pr.get('closed_at') or ''}").classes("text-xs text-slate-400")

                                # ПРАВАЯ КОЛОНКА: Сводка по текущему месяцу + Счетчики
                                with ui.column().classes("flex-1 gap-4"):
                                    ui.label(f"Статус оплаты арендаторов ({db.current_month_str()})").classes("text-lg font-bold text-slate-800")

                                    for s in all_spaces:
                                        is_paid_now = s.get("payment_status") == "paid"
                                        unpaid_ov, paid_ov = db.get_payment_history_stats(s["id"])

                                        with ui.row().classes("w-full items-center justify-between p-2.5 border border-slate-200 rounded-lg gap-2 bg-slate-50/70"):
                                            with ui.column().classes("gap-0"):
                                                with ui.row().classes("items-center gap-2"):
                                                    ui.badge(f"{s['code']}", color="primary")
                                                    ui.label(s["tenant"] or "Без названия").classes("font-semibold text-sm text-slate-800")
                                                ui.label(f"Ставка: {s['price']:,} ₽/мес".replace(",", " ")).classes("text-xs text-slate-500")

                                            with ui.row().classes("items-center gap-1.5 shrink-0"):
                                                ui.badge(
                                                    "Оплачено" if is_paid_now else "Не оплачено",
                                                    color="green" if is_paid_now else "orange",
                                                )

                                                hist_color = "negative" if unpaid_ov > 0 else ("warning" if paid_ov > 0 else "primary")
                                                hist_label = f"История ({unpaid_ov + paid_ov})" if (unpaid_ov + paid_ov) > 0 else "История"
                                                ui.button(
                                                    hist_label,
                                                    icon="history",
                                                    color=hist_color,
                                                    on_click=lambda sp=s: open_payment_history_dialog(
                                                        sp, is_landlord=True, on_updated=lambda: refresh_all(update_inspector=True)
                                                    ),
                                                ).props("dense outline size=sm")

                                    ui.separator()
                                    ui.label(
                                        f"Показания счетчиков (ХВС: {db.HVS_TARIFF} ₽, ГВС: {db.GVS_TARIFF} ₽, Свет: {db.ELEC_TARIFF} ₽)"
                                    ).classes("text-base font-bold text-slate-800")

                                    if not readings:
                                        ui.label("Показания счетчиков за текущий период еще не передавались.").classes("text-sm text-slate-500")
                                    else:
                                        for r in readings:
                                            is_accepted = r["status"] == "accepted"
                                            h_diff = round(r["curr_hvs"] - r["prev_hvs"], 2)
                                            g_diff = round(r["curr_gvs"] - r["prev_gvs"], 2)
                                            e_diff = round(r["curr_elec"] - r["prev_elec"], 2)

                                            with ui.row().classes("w-full items-center justify-between p-3 border rounded-lg bg-slate-50 gap-2"):
                                                with ui.column().classes("gap-0.5"):
                                                    with ui.row().classes("items-center gap-2"):
                                                        ui.badge(f"{r['space_code']}", color="primary")
                                                        ui.label(f"{r['tenant_name']} • {r['period']}").classes("font-semibold text-sm text-slate-800")
                                                    ui.label(
                                                        f"ХВС: {r['prev_hvs']}→{r['curr_hvs']} (+{h_diff}) | "
                                                        f"ГВС: {r['prev_gvs']}→{r['curr_gvs']} (+{g_diff}) | "
                                                        f"Свет: {r['prev_elec']}→{r['curr_elec']} (+{e_diff})"
                                                    ).classes("text-xs text-slate-600")
                                                    ui.label(f"Переменная часть: {r['total_cost']:,} ₽".replace(",", " ")).classes("text-sm font-bold text-blue-700")

                                                with ui.column().classes("items-end gap-1 shrink-0"):
                                                    ui.badge("Принято" if is_accepted else "На проверке", color="green" if is_accepted else "orange")
                                                    if not is_accepted:
                                                        ui.button(
                                                            "Принять в расчет",
                                                            color="positive",
                                                            on_click=lambda rid=r["id"]: (db.accept_meter_reading(rid), refresh_all()),
                                                        ).props("dense size=sm")

                        finance_panel()

                    # --- ВКЛАДКА 2: ЗАЯВКИ НА РЕМОНТ ---
                    with ui.tab_panel(tab_tickets).classes("p-0"):
                        @ui.refreshable
                        def tickets_panel():
                            tickets = db.get_tickets()
                            active_cnt = sum(1 for t in tickets if t["status"] != "done")
                            urgent_cnt = sum(1 for t in tickets if t["status"] != "done" and t["priority"] == "urgent")

                            with ui.column().classes("w-full gap-3"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.label("Заявки на ремонт и обслуживание").classes("text-lg font-bold text-slate-800")
                                    if active_cnt:
                                        ui.badge(f"Активных: {active_cnt}", color="orange")
                                    if urgent_cnt:
                                        ui.badge(f"Аварийных: {urgent_cnt}", color="red")

                                if not tickets:
                                    ui.label("Заявок от арендаторов пока нет.").classes("text-slate-500 text-sm")
                                    return

                                for t in tickets:
                                    t_meta = TICKET_META[t["status"]]
                                    p_meta = TICKET_PRIORITIES.get(t["priority"], TICKET_PRIORITIES["normal"])
                                    cat_label = TICKET_CATEGORIES.get(t["category"], "Общий ремонт")
                                    space_info = db.get_space_by_id(t["space_id"]) or {}
                                    p_dir = space_info.get("point_director", "")
                                    a_dir = space_info.get("area_director", "")

                                    is_urgent_active = t["priority"] == "urgent" and t["status"] != "done"
                                    card_border = "border-red-400 bg-red-50/40" if is_urgent_active else "border-slate-200 bg-slate-50"

                                    with ui.row().classes(f"w-full items-start justify-between p-3 border rounded-lg gap-3 {card_border}"):
                                        with ui.column().classes("gap-1 flex-1"):
                                            with ui.row().classes("items-center gap-1.5 flex-wrap"):
                                                ui.badge(f"Павильон {t['space_code']}", color="primary")
                                                ui.badge(p_meta["label"], color=p_meta["badge"])
                                                ui.badge(cat_label, color="grey").props("outline")
                                                ui.label(t["tenant"]).classes("font-semibold text-slate-800 ml-1")
                                                ui.label(f"• {t['created_at']}").classes("text-xs text-slate-400")

                                            ui.label(t["description"]).classes("text-sm text-slate-800 mt-0.5")

                                            if t.get("photo_name") and os.path.exists(t.get("photo_path", "")):
                                                ui.button(
                                                    f"Фото: {t['photo_name']}",
                                                    icon="photo_camera",
                                                    on_click=lambda p=t["photo_path"], n=t["photo_name"]: open_photo_preview(p, n),
                                                ).props("dense flat size=sm color=primary")

                                            if p_dir or a_dir:
                                                contact_parts = []
                                                if p_dir:
                                                    contact_parts.append(f"Директор точки: {p_dir}")
                                                if a_dir:
                                                    contact_parts.append(f"Вышестоящий: {a_dir}")
                                                ui.label(" • ".join(contact_parts)).classes("text-xs text-slate-500 mt-0.5")

                                        with ui.column().classes("items-end gap-1.5 shrink-0"):
                                            ui.badge(t_meta["label"], color=t_meta["badge"])
                                            with ui.row().classes("gap-1"):
                                                if t["status"] == "new":
                                                    ui.button(
                                                        "В работу",
                                                        on_click=lambda tid=t["id"]: (db.update_ticket_status(tid, "in_progress"), refresh_all()),
                                                    ).props("dense outline size=sm")
                                                if t["status"] != "done":
                                                    ui.button(
                                                        "Закрыть",
                                                        color="positive",
                                                        on_click=lambda tid=t["id"]: (db.update_ticket_status(tid, "done"), refresh_all()),
                                                    ).props("dense size=sm")

                        tickets_panel()

                    # --- ВКЛАДКА 3: СООБЩЕНИЯ И РАССЫЛКИ ---
                    with ui.tab_panel(tab_msgs).classes("p-0"):
                        with ui.row().classes("w-full gap-6 items-start no-wrap"):
                            with ui.column().classes("w-96 shrink-0 gap-3"):
                                ui.label("Новое сообщение / рассылка").classes("text-lg font-bold text-slate-800")

                                recipient_options = {"ALL": "📢 Всем арендаторам (Общая рассылка)"}
                                for s in db.get_all_spaces():
                                    label = f"Павильон {s['code']} — {s['tenant']}" if s["tenant"] else f"Павильон {s['code']} (свободен)"
                                    recipient_options[s["id"]] = label

                                target_select = ui.select(
                                    options=recipient_options,
                                    value="ALL",
                                    label="Кому отправить",
                                ).classes("w-full")

                                msg_input = ui.textarea(
                                    label="Текст сообщения",
                                    placeholder="Например: Просим направить показания счетчиков до 25 числа.",
                                ).classes("w-full").props("rows=3")

                                async def handle_upload(e: events.UploadEventArguments):
                                    att_name, att_path = await save_uploaded_file(e)
                                    state["upload_file"] = (att_name, att_path)
                                    ui.notify(f"Файл «{att_name}» прикреплен", type="info")

                                uploader = ui.upload(
                                    label="Прикрепить файл",
                                    auto_upload=True,
                                    on_upload=handle_upload,
                                ).classes("w-full").props("flat bordered")

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
                                    ui.notify("Сообщение отправлено!", type="positive")

                                ui.button("Отправить сообщение", icon="send", on_click=send_landlord_msg).classes("w-full")

                            with ui.column().classes("flex-1 gap-2"):
                                ui.label("История переписки и рассылок").classes("text-lg font-bold text-slate-800")

                                @ui.refreshable
                                def messages_feed():
                                    msgs = db.get_messages_for_landlord()
                                    if not msgs:
                                        ui.label("Сообщений пока нет.").classes("text-sm text-slate-400")
                                        return

                                    with ui.column().classes("w-full gap-2 max-h-96 overflow-y-auto pr-1"):
                                        for m in msgs:
                                            is_from_uk = m["sender_role"] == "landlord"
                                            card_bg = "bg-blue-50/70 border-blue-200" if is_from_uk else "bg-emerald-50/70 border-emerald-200"

                                            with ui.column().classes(f"w-full p-3 border rounded-lg gap-1 {card_bg}"):
                                                with ui.row().classes("w-full justify-between items-center"):
                                                    if is_from_uk:
                                                        badge_text = "📢 Всем арендаторам" if m["space_id"] == "ALL" else f"УК → Павильон {m['space_code']}"
                                                        ui.badge(badge_text, color="primary")
                                                    else:
                                                        ui.badge(f"От: Павильон {m['space_code']} ({m['tenant_name']})", color="green")
                                                    ui.label(m["created_at"]).classes("text-xs text-slate-400")

                                                if m["body"]:
                                                    ui.label(m["body"]).classes("text-sm text-slate-800 whitespace-pre-line")

                                                if m["attachment_name"] and os.path.exists(m["attachment_path"]):
                                                    ui.button(
                                                        f"Скачать: {m['attachment_name']}",
                                                        icon="attach_file",
                                                        on_click=lambda p=m["attachment_path"], n=m["attachment_name"]: ui.download(p, n),
                                                    ).props("dense flat size=sm color=primary")

                                messages_feed()