import os
from nicegui import events, ui
import database as db
from ui_common import (
    MARKETING_STATUS_META,
    PROMO_TYPE_META,
    TURNOVER_STATUS_META,
    open_photo_preview,
    save_uploaded_file,
)


def render_landlord_marketing_and_turnovers(state: dict, refresh_all):
    """Раздел маркетинга, согласования вывесок/акций и контроля товарооборота УК"""
    marketing_reqs = db.get_marketing_requests()
    turnovers = db.get_turnovers()

    pending_promos = [m for m in marketing_reqs if m["status"] == "pending"]
    submitted_to = [t for t in turnovers if t["status"] == "submitted"]

    with ui.column().classes("w-full gap-4"):
        with ui.tabs().classes("w-full border-b text-slate-700") as subtabs:
            tab_m = ui.tab(f"Акции и вывески ({len(pending_promos)} на согласовании)", icon="campaign")
            tab_t = ui.tab(f"Товарооборот и % с выручки ({len(submitted_to)} на проверке)", icon="point_of_sale")

        with ui.tab_panels(subtabs, value=tab_m).classes("w-full p-0 mt-2"):
            # --- ВКЛАДКА 1: СОГЛАСОВАНИЕ АКЦИЙ И ВЫВЕСОК ---
            with ui.tab_panel(tab_m).classes("p-0"):
                with ui.row().classes("w-full justify-between items-center mb-3"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label("Заявки арендаторов на вывески, промо-стойки и распродажи").classes("text-lg font-bold text-slate-800")
                        if pending_promos:
                            ui.badge(f"Требуют решения: {len(pending_promos)}", color="orange")
                    ui.badge(f"Всего заявок: {len(marketing_reqs)}", color="grey")

                if not marketing_reqs:
                    ui.label("Заявок на маркетинговые активности пока нет.").classes("text-sm text-slate-400 py-4")
                else:
                    with ui.column().classes("w-full gap-3 max-h-[600px] overflow-y-auto pr-1"):
                        for m in marketing_reqs:
                            st = m["status"]
                            st_meta = MARKETING_STATUS_META.get(st, MARKETING_STATUS_META["pending"])
                            p_type = PROMO_TYPE_META.get(m["promo_type"], {"label": m["promo_type"], "badge": "grey"})

                            card_border = (
                                "border-amber-300 bg-amber-50/40"
                                if st == "pending"
                                else ("border-emerald-200 bg-emerald-50/30" if st == "approved" else "border-red-200 bg-red-50/30")
                            )

                            with ui.column().classes(f"w-full p-4 border rounded-xl gap-2 {card_border}"):
                                with ui.row().classes("w-full justify-between items-start gap-2"):
                                    with ui.row().classes("items-center gap-2 flex-wrap"):
                                        ui.badge(f"№ {m['id']}", color="grey-8")
                                        ui.badge(f"Павильон {m['space_code']}", color="primary")
                                        ui.label(m["tenant_name"]).classes("font-bold text-slate-800")
                                        ui.badge(p_type["label"], color=p_type["badge"])
                                        ui.label(f"• Период: {m['date_range']}").classes("text-xs font-semibold text-slate-600")

                                    ui.badge(st_meta["label"], color=st_meta["badge"])

                                ui.label(m["title"]).classes("text-sm text-slate-900 font-bold")
                                ui.label(m["description"]).classes("text-sm text-slate-700")

                                if m.get("mockup_file_name") and os.path.exists(m.get("mockup_file_path", "")):
                                    ext = os.path.splitext(m["mockup_file_name"])[1].lower()
                                    with ui.row().classes("items-center gap-2 mt-1"):
                                        if ext in {".png", ".jpg", ".jpeg", ".webp"}:
                                            ui.button(
                                                f"Макет: {m['mockup_file_name']}",
                                                icon="visibility",
                                                on_click=lambda p=m["mockup_file_path"], n=m["mockup_file_name"]: open_photo_preview(p, n),
                                            ).props("dense outline size=sm color=primary")
                                        ui.button(
                                            "Скачать макет",
                                            icon="download",
                                            on_click=lambda p=m["mockup_file_path"], n=m["mockup_file_name"]: ui.download(p, n),
                                        ).props("dense flat size=sm color=primary")

                                if m.get("uk_feedback"):
                                    ui.label(f"Ответ УК: {m['uk_feedback']}").classes("text-xs text-indigo-800 font-medium")

                                if st in {"pending", "revision"}:
                                    with ui.row().classes("w-full gap-2 items-center mt-2 pt-2 border-t"):
                                        feedback_inp = ui.input(
                                            placeholder="Комментарий маркетолога ТЦ...",
                                            value="Согласовано с отделом маркетинга ТЦ",
                                        ).classes("flex-1").props("outlined dense")

                                        ui.button(
                                            "Согласовать",
                                            icon="check_circle",
                                            color="positive",
                                            on_click=lambda mid=m["id"], fi=feedback_inp: (
                                                db.update_marketing_status(mid, "approved", fi.value),
                                                refresh_all(),
                                                ui.notify(f"Акция №{mid} согласована", type="positive"),
                                            ),
                                        ).props("dense size=sm")

                                        ui.button(
                                            "На доработку",
                                            icon="edit",
                                            color="warning",
                                            on_click=lambda mid=m["id"], fi=feedback_inp: (
                                                db.update_marketing_status(mid, "revision", fi.value or "Требуются правки макета"),
                                                refresh_all(),
                                                ui.notify(f"Заявка №{mid} отправлена на доработку", type="warning"),
                                            ),
                                        ).props("dense outline size=sm")

            # --- ВКЛАДКА 2: ТОВАРООБОРОТ И % ОТ ВЫРУЧКИ ---
            with ui.tab_panel(tab_t).classes("p-0"):
                total_rev = sum(t["reported_revenue"] for t in turnovers)
                total_fees = sum(t["calculated_fee"] for t in turnovers)

                with ui.row().classes("w-full gap-4 items-center bg-indigo-50/60 p-4 rounded-xl border border-indigo-200 mb-4 flex-wrap"):
                    with ui.column().classes("gap-0"):
                        ui.label("Суммарная выручка по отчетам").classes("text-xs text-slate-500 uppercase font-semibold")
                        ui.label(f"{total_rev:,} ₽".replace(",", " ")).classes("text-xl font-bold text-slate-900")
                    with ui.column().classes("gap-0 ml-4"):
                        ui.label("Начислено арендных % с оборота").classes("text-xs text-slate-500 uppercase font-semibold")
                        ui.label(f"{total_fees:,} ₽".replace(",", " ")).classes("text-xl font-bold text-indigo-700")

                with ui.row().classes("w-full justify-between items-center mb-2"):
                    ui.label("Реестр отчетов по товарообороту (Z-отчеты / ОФД)").classes("text-base font-bold text-slate-800")
                    if submitted_to:
                        ui.badge(f"Ожидают подтверждения: {len(submitted_to)}", color="orange")

                if not turnovers:
                    ui.label("Отчетов по товарообороту пока нет.").classes("text-sm text-slate-400 py-3")
                else:
                    with ui.column().classes("w-full gap-3 max-h-[500px] overflow-y-auto pr-1"):
                        for t in turnovers:
                            st = t["status"]
                            st_meta = TURNOVER_STATUS_META.get(st, TURNOVER_STATUS_META["submitted"])
                            card_border = "border-amber-300 bg-amber-50/30" if st == "submitted" else "border-emerald-200 bg-emerald-50/30"

                            with ui.row().classes(f"w-full items-center justify-between p-3.5 border rounded-xl gap-3 {card_border}"):
                                with ui.column().classes("gap-1 flex-1"):
                                    with ui.row().classes("items-center gap-2 flex-wrap"):
                                        ui.badge(f"Павильон {t['space_code']}", color="primary")
                                        ui.label(t["tenant_name"]).classes("font-bold text-slate-800")
                                        ui.label(f"• Период: {t['period']}").classes("text-xs font-semibold text-slate-600")
                                        ui.label(f"• Передано: {t['created_at']}").classes("text-xs text-slate-400")

                                    with ui.row().classes("items-center gap-4 mt-1 text-sm"):
                                        ui.label(f"Кассовая выручка: {t['reported_revenue']:,} ₽".replace(",", " ")).classes("font-semibold text-slate-800")
                                        ui.label(f"Переменный платеж ({t['calculated_fee']:,} ₽)".replace(",", " ")).classes("font-bold text-indigo-700")

                                    if t.get("report_file_name") and os.path.exists(t.get("report_file_path", "")):
                                        ui.button(
                                            f"Справка ОФД: {t['report_file_name']}",
                                            icon="receipt_long",
                                            on_click=lambda p=t["report_file_path"], n=t["report_file_name"]: ui.download(p, n),
                                        ).props("dense outline size=sm color=primary").classes("mt-1")

                                with ui.row().classes("items-center gap-2 shrink-0"):
                                    ui.badge(st_meta["label"], color=st_meta["badge"])
                                    if st == "submitted":
                                        ui.button(
                                            "Принять отчет",
                                            icon="check",
                                            color="positive",
                                            on_click=lambda tid=t["id"]: (
                                                db.update_turnover_status(tid, "accepted"),
                                                refresh_all(),
                                                ui.notify(f"Отчет №{tid} принят", type="positive"),
                                            ),
                                        ).props("dense size=sm")


def render_tenant_marketing(my_space_id: str, state: dict, refresh_all):
    """Раздел согласования акций и вывесок со стороны арендатора"""
    my_promos = db.get_marketing_requests(space_id=my_space_id)

    with ui.row().classes("w-full gap-6 items-start no-wrap"):
        # Левая колонка: Форма подачи заявки на согласование
        with ui.column().classes("w-96 shrink-0 gap-3 p-4 bg-slate-50 border rounded-xl"):
            ui.label("Заявка на вывеску / акцию").classes("text-base font-bold text-slate-800")

            promo_opts = {k: v["label"] for k, v in PROMO_TYPE_META.items()}
            promo_type_sel = ui.select(options=promo_opts, value="sale_event", label="Тип активности").classes("w-full").props("outlined dense")

            promo_title_inp = ui.input(
                label="Название акции / вывески",
                placeholder="Например: Сезонная распродажа -30%",
            ).classes("w-full").props("outlined dense")

            promo_dates_inp = ui.input(
                label="Сроки проведения",
                placeholder="Например: 25.11.2026 - 30.11.2026",
            ).classes("w-full").props("outlined dense")

            promo_desc_inp = ui.textarea(
                label="Описание активности и мест размещения",
                placeholder="Где будут постеры, стойка, требования к электричеству...",
            ).classes("w-full").props("outlined dense rows=2")

            mockup_draft = {"data": None}

            @ui.refreshable
            def mockup_draft_box():
                if mockup_draft["data"]:
                    with ui.row().classes("items-center gap-2 text-xs text-emerald-700 font-medium"):
                        ui.icon("check_circle", size="xs")
                        ui.label(f"Макет прикреплен: {mockup_draft['data'][0]}")
                else:
                    ui.label("Файл макета пока не прикреплен.").classes("text-xs text-slate-400")

            mockup_draft_box()

            async def on_mockup_upload(e: events.UploadEventArguments):
                fname, fpath = await save_uploaded_file(e)
                mockup_draft["data"] = (fname, fpath)
                mockup_draft_box.refresh()
                ui.notify(f"Макет «{fname}» загружен", type="info")

            ui.upload(
                label="Прикрепить макет баннера / вывески",
                auto_upload=True,
                on_upload=on_mockup_upload,
            ).classes("w-full").props("flat bordered dense")

            def submit_promo():
                if not promo_title_inp.value or not promo_title_inp.value.strip():
                    ui.notify("Укажите название маркетинговой активности", type="warning")
                    return
                m_name, m_path = mockup_draft["data"] if mockup_draft["data"] else ("", "")
                db.create_marketing_request(
                    space_id=my_space_id,
                    promo_type=promo_type_sel.value,
                    title=promo_title_inp.value.strip(),
                    date_range=promo_dates_inp.value or "По согласованию",
                    description=promo_desc_inp.value or "",
                    mockup_file_name=m_name,
                    mockup_file_path=m_path,
                )
                promo_title_inp.value = ""
                promo_desc_inp.value = ""
                mockup_draft["data"] = None
                refresh_all()
                ui.notify("Заявка отправлена на согласование в отдел маркетинга ТЦ!", type="positive")

            ui.button("Отправить на согласование", icon="send", on_click=submit_promo).classes("w-full py-2").props("color=primary")

        # Правая колонка: Список поданных заявок
        with ui.column().classes("flex-1 gap-3"):
            ui.label("История согласований").classes("text-base font-bold text-slate-800")

            if not my_promos:
                ui.label("Вы пока не отправляли заявок на согласование акций или вывесок.").classes("text-sm text-slate-400 py-3")
            else:
                with ui.column().classes("w-full gap-3 max-h-[550px] overflow-y-auto pr-1"):
                    for m in my_promos:
                        st = m["status"]
                        st_meta = MARKETING_STATUS_META.get(st, MARKETING_STATUS_META["pending"])
                        p_type = PROMO_TYPE_META.get(m["promo_type"], {"label": m["promo_type"], "badge": "grey"})

                        card_border = (
                            "border-amber-300 bg-amber-50/30"
                            if st == "pending"
                            else ("border-emerald-200 bg-emerald-50/30" if st == "approved" else "border-red-200 bg-red-50/30")
                        )

                        with ui.column().classes(f"w-full p-4 border rounded-xl gap-2 {card_border}"):
                            with ui.row().classes("w-full justify-between items-center"):
                                with ui.row().classes("items-center gap-2 flex-wrap"):
                                    ui.badge(f"№ {m['id']}", color="grey-8")
                                    ui.badge(p_type["label"], color=p_type["badge"])
                                    ui.label(f"Сроки: {m['date_range']}").classes("text-xs font-semibold text-slate-700")
                                ui.badge(st_meta["label"], color=st_meta["badge"])

                            ui.label(m["title"]).classes("text-sm font-bold text-slate-800")
                            if m["description"]:
                                ui.label(m["description"]).classes("text-xs text-slate-600")

                            if m.get("mockup_file_name") and os.path.exists(m.get("mockup_file_path", "")):
                                ui.button(
                                    f"Макет: {m['mockup_file_name']}",
                                    icon="download",
                                    on_click=lambda p=m["mockup_file_path"], n=m["mockup_file_name"]: ui.download(p, n),
                                ).props("dense outline size=sm color=primary")

                            if m.get("uk_feedback"):
                                with ui.row().classes("w-full p-2.5 rounded border text-xs font-medium bg-white/80 border-slate-200"):
                                    ui.label(f"Ответ администрации ТЦ: {m['uk_feedback']}")


def render_tenant_turnover_card(my_space_id: str, state: dict, refresh_all):
    """Карточка отчета по товарообороту для арендатора с договором % от выручки"""
    space = db.get_space_by_id(my_space_id)
    t_percent = float(space.get("turnover_percent") or 0.0)
    if t_percent <= 0:
        return

    my_turnovers = db.get_turnovers(space_id=my_space_id)

    with ui.card().classes("w-full p-5 gap-3 border border-indigo-200 bg-indigo-50/40 rounded-xl"):
        with ui.row().classes("w-full justify-between items-center"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("point_of_sale", size="sm").classes("text-indigo-600")
                ui.label(f"Отчет по товарообороту ({t_percent}% по договору)").classes("text-base font-bold text-slate-800")
            ui.badge(f"{t_percent}% от выручки", color="indigo").props("rounded")

        with ui.row().classes("w-full gap-3 items-center flex-wrap"):
            to_period_inp = ui.input(label="Период (ММ.ГГГГ)", value=db.current_month_str()).classes("w-36").props("outlined dense")
            to_rev_inp = ui.number(label="Кассовая выручка за месяц (₽)", value=1500000, step=50000).classes("w-64").props("outlined dense")

            calc_badge = ui.badge(f"Переменная часть: {round(1500000 * t_percent / 100):,} ₽", color="green").props("dense")

            def on_rev_change():
                val = float(to_rev_inp.value or 0)
                fee = round(val * t_percent / 100)
                calc_badge.text = f"Переменная часть: {fee:,} ₽".replace(",", " ")

            to_rev_inp.on_value_change(on_rev_change)

        to_draft = {"data": None}

        @ui.refreshable
        def to_draft_box():
            if to_draft["data"]:
                with ui.row().classes("items-center gap-2 text-xs text-emerald-700 font-medium"):
                    ui.icon("check_circle", size="xs")
                    ui.label(f"Справка ОФД прикреплена: {to_draft['data'][0]}")
            else:
                ui.label("Скан Z-отчета / выписка ОФД пока не прикреплена.").classes("text-xs text-slate-400")

        to_draft_box()

        async def on_to_upload(e: events.UploadEventArguments):
            fname, fpath = await save_uploaded_file(e)
            to_draft["data"] = (fname, fpath)
            to_draft_box.refresh()
            ui.notify(f"Файл «{fname}» прикреплен", type="info")

        ui.upload(
            label="Прикрепить скан Z-отчета или выгрузку ОФД",
            auto_upload=True,
            on_upload=on_to_upload,
        ).classes("w-full").props("flat bordered dense")

        def submit_to():
            val = int(to_rev_inp.value or 0)
            if val <= 0:
                ui.notify("Введите сумму выручки", type="warning")
                return
            f_name, f_path = to_draft["data"] if to_draft["data"] else ("", "")
            db.submit_turnover_report(
                space_id=my_space_id,
                period=to_period_inp.value or db.current_month_str(),
                reported_revenue=val,
                report_file_name=f_name,
                report_file_path=f_path,
            )
            to_draft["data"] = None
            refresh_all()
            ui.notify("Отчет по товарообороту отправлен на проверку в УК!", type="positive")

        ui.button("Отправить отчет по выручке", icon="send", on_click=submit_to).classes("w-full py-1.5").props("color=primary dense")

        if my_turnovers:
            ui.separator().classes("my-1")
            ui.label("История переданных отчетов по выручке").classes("text-xs font-bold uppercase text-slate-500")
            with ui.column().classes("w-full gap-2 max-h-40 overflow-y-auto pr-1"):
                for t in my_turnovers[:5]:
                    is_acc = t["status"] == "accepted"
                    with ui.row().classes("w-full justify-between items-center p-2.5 bg-white rounded border text-xs"):
                        ui.label(f"{t['period']}: выручка {t['reported_revenue']:,} ₽ → платеж {t['calculated_fee']:,} ₽".replace(",", " ")).classes("font-medium")
                        ui.badge("Принято УК" if is_acc else "На проверке", color="green" if is_acc else "orange").props("dense")
