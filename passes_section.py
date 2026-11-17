import os
from datetime import datetime, timedelta
from nicegui import events, ui
import database as db
from ui_common import (
    INSPECTION_CAT_META,
    INSPECTION_STATUS_META,
    PASS_STATUS_META,
    PASS_TYPE_META,
    open_photo_preview,
    save_uploaded_file,
)


def render_landlord_passes_and_inspections(state: dict, refresh_all):
    """Раздел управления электронными пропусками и журналом проверок УК"""
    passes = db.get_access_passes()
    inspections = db.get_inspections()

    pending_passes = [p for p in passes if p["status"] == "pending"]
    open_inspections = [i for i in inspections if i["status"] != "resolved"]
    overdue_inspections = [i for i in open_inspections if db.is_due_date_passed(i["deadline"])]

    with ui.column().classes("w-full gap-4"):
        with ui.tabs().classes("w-full border-b text-slate-700") as subtabs:
            tab_p = ui.tab(f"Пропуска ({len(pending_passes)} на согласовании)", icon="badge")
            tab_i = ui.tab(f"Предписания ПБ/СЭС ({len(open_inspections)} активных)", icon="policy")

        with ui.tab_panels(subtabs, value=tab_p).classes("w-full p-0 mt-2"):
            # --- ВКЛАДКА: ПРОПУСКА ---
            with ui.tab_panel(tab_p).classes("p-0"):
                with ui.row().classes("w-full justify-between items-center mb-3"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label("Реестр электронных пропусков на ввоз/вывоз и ночные работы").classes("text-lg font-bold text-slate-800")
                        if pending_passes:
                            ui.badge(f"Требуют решения: {len(pending_passes)}", color="orange")
                    ui.badge(f"Всего заявок: {len(passes)}", color="grey")

                if not passes:
                    ui.label("Заявок на пропуска пока нет.").classes("text-sm text-slate-400 py-4")
                else:
                    with ui.column().classes("w-full gap-3 max-h-[600px] overflow-y-auto pr-1"):
                        for p in passes:
                            st = p["status"]
                            st_meta = PASS_STATUS_META.get(st, PASS_STATUS_META["pending"])
                            p_type = PASS_TYPE_META.get(p["pass_type"], {"label": p["pass_type"], "icon": "badge", "badge": "grey"})

                            card_border = (
                                "border-amber-300 bg-amber-50/40"
                                if st == "pending"
                                else ("border-emerald-200 bg-emerald-50/30" if st == "approved" else "border-slate-200 bg-slate-50")
                            )

                            with ui.column().classes(f"w-full p-4 border rounded-xl gap-2 {card_border}"):
                                with ui.row().classes("w-full justify-between items-start gap-2"):
                                    with ui.row().classes("items-center gap-2 flex-wrap"):
                                        ui.badge(f"№ {p['id']}", color="grey-8")
                                        ui.badge(f"Павильон {p['space_code']}", color="primary")
                                        ui.label(p["tenant_name"]).classes("font-bold text-slate-800")
                                        ui.badge(p_type["label"], color=p_type["badge"]).props("outline")
                                        ui.label(f"• Подано: {p['created_at']}").classes("text-xs text-slate-400")
                                    ui.badge(st_meta["label"], color=st_meta["badge"])

                                with ui.row().classes("w-full gap-4 text-sm text-slate-700 bg-white/70 p-2.5 rounded-lg border flex-wrap"):
                                    ui.label(f"📅 Дата: {p['work_date']}").classes("font-semibold")
                                    ui.label(f"⏰ Окно: {p['time_window']}").classes("font-semibold")
                                    if p["vehicle_info"]:
                                        ui.label(f"🚗 Авто: {p['vehicle_info']}")

                                ui.label(f"Сотрудники/подрядчики: {p['workers_list']}").classes("text-xs text-slate-600")
                                if p["description"]:
                                    ui.label(f"Цель работ / груз: {p['description']}").classes("text-sm text-slate-800")

                                if p.get("uk_comment"):
                                    ui.label(f"Комментарий УК: {p['uk_comment']}").classes("text-xs text-indigo-700 font-medium")

                                if st == "pending":
                                    with ui.row().classes("w-full gap-2 items-center mt-2 pt-2 border-t"):
                                        comment_inp = ui.input(
                                            placeholder="Укажите ворота/дебаркадер или причину отказа...",
                                            value="Дебаркадер №2 (разгрузочная зона)",
                                        ).classes("flex-1").props("outlined dense")

                                        ui.button(
                                            "Одобрить пропуск",
                                            icon="check_circle",
                                            color="positive",
                                            on_click=lambda pid=p["id"], ci=comment_inp: (
                                                db.update_access_pass_status(pid, "approved", ci.value),
                                                refresh_all(),
                                                ui.notify(f"Пропуск №{pid} одобрен", type="positive"),
                                            ),
                                        ).props("dense size=sm")

                                        ui.button(
                                            "Отклонить",
                                            icon="cancel",
                                            color="negative",
                                            on_click=lambda pid=p["id"], ci=comment_inp: (
                                                db.update_access_pass_status(pid, "rejected", ci.value or "Отклонено службой безопасности"),
                                                refresh_all(),
                                                ui.notify(f"Пропуск №{pid} отклонен", type="warning"),
                                            ),
                                        ).props("dense outline size=sm")

            # --- ВКЛАДКА: ПРЕДПИСАНИЯ ПБ И СЭС ---
            with ui.tab_panel(tab_i).classes("p-0"):
                with ui.row().classes("w-full gap-6 items-start no-wrap"):
                    # Левая колонка: Форма выписки предписания
                    with ui.column().classes("w-96 shrink-0 gap-3 p-4 bg-slate-50 border rounded-xl"):
                        ui.label("Выписать предписание арендатору").classes("text-base font-bold text-slate-800")

                        all_spaces = [s for s in db.get_all_spaces() if s["status"] != "free"]
                        sp_opts = {s["id"]: f"Павильон {s['code']} — {s['tenant']}" for s in all_spaces}
                        first_sid = next(iter(sp_opts), None)

                        insp_space_sel = ui.select(options=sp_opts, value=first_sid, label="Павильон").classes("w-full").props("outlined dense")
                        cat_opts = {k: v["label"] for k, v in INSPECTION_CAT_META.items()}
                        insp_cat_sel = ui.select(options=cat_opts, value="fire_safety", label="Категория проверки").classes("w-full").props("outlined dense")

                        insp_title_inp = ui.textarea(
                            label="Суть предписания / замечания",
                            placeholder="Например: Освободить доступ к пожарному гидранту / убрать упаковочную тару.",
                        ).classes("w-full").props("outlined dense rows=2")

                        default_deadline = (datetime.now() + timedelta(days=5)).strftime("%d.%m.%Y")
                        insp_deadline_inp = ui.input(
                            label="Срок устранения (ДД.ММ.ГГГГ)",
                            value=default_deadline,
                        ).classes("w-full").props("outlined dense")

                        insp_photo_draft = {"data": None}

                        async def on_insp_photo_upload(e: events.UploadEventArguments):
                            fname, fpath = await save_uploaded_file(e)
                            insp_photo_draft["data"] = (fname, fpath)
                            ui.notify(f"Фото нарушения «{fname}» загружено", type="info")

                        insp_uploader = ui.upload(
                            label="Фото нарушения (опционально)",
                            auto_upload=True,
                            on_upload=on_insp_photo_upload,
                        ).classes("w-full").props("flat bordered dense")

                        def issue_inspection():
                            if not insp_title_inp.value or not insp_title_inp.value.strip():
                                ui.notify("Опишите суть предписания", type="warning")
                                return
                            p_name, p_path = insp_photo_draft["data"] if insp_photo_draft["data"] else ("", "")
                            db.create_inspection(
                                space_id=insp_space_sel.value,
                                category=insp_cat_sel.value,
                                title=insp_title_inp.value.strip(),
                                deadline=insp_deadline_inp.value or default_deadline,
                                uk_photo_name=p_name,
                                uk_photo_path=p_path,
                            )
                            insp_title_inp.value = ""
                            insp_photo_draft["data"] = None
                            insp_uploader.reset()
                            refresh_all()
                            ui.notify("Предписание выписано и отправлено арендатору!", type="positive")

                        ui.button("Выписать предписание", icon="send", on_click=issue_inspection).classes("w-full py-2").props("color=primary")

                    # Правая колонка: Реестр предписаний
                    with ui.column().classes("flex-1 gap-3"):
                        with ui.row().classes("w-full justify-between items-center"):
                            ui.label("Журнал выписанных предписаний").classes("text-base font-bold text-slate-800")
                            with ui.row().classes("gap-1.5"):
                                if overdue_inspections:
                                    ui.badge(f"Просрочено: {len(overdue_inspections)}", color="red")
                                if open_inspections:
                                    ui.badge(f"В работе: {len(open_inspections)}", color="orange")

                        if not inspections:
                            ui.label("Предписаний нет. Нарушений требований ПБ и СЭС не зафиксировано.").classes("text-sm text-slate-400 py-3")
                        else:
                            with ui.column().classes("w-full gap-3 max-h-[550px] overflow-y-auto pr-1"):
                                for insp in inspections:
                                    st = insp["status"]
                                    st_meta = INSPECTION_STATUS_META.get(st, INSPECTION_STATUS_META["open"])
                                    cat_meta = INSPECTION_CAT_META.get(insp["category"], {"label": insp["category"], "badge": "grey"})
                                    is_overdue = st != "resolved" and db.is_due_date_passed(insp["deadline"])

                                    card_cls = (
                                        "border-red-300 bg-red-50/40"
                                        if is_overdue
                                        else ("border-blue-300 bg-blue-50/40" if st == "review" else "border-slate-200 bg-slate-50")
                                    )

                                    with ui.column().classes(f"w-full p-4 border rounded-xl gap-2 {card_cls}"):
                                        with ui.row().classes("w-full justify-between items-start gap-2"):
                                            with ui.row().classes("items-center gap-2 flex-wrap"):
                                                ui.badge(f"Предписание №{insp['id']}", color="grey-8")
                                                ui.badge(f"Павильон {insp['space_code']}", color="primary")
                                                ui.badge(cat_meta["label"], color=cat_meta["badge"])
                                                ui.label(insp["tenant_name"]).classes("font-bold text-slate-800")
                                                ui.label(f"• Срок: {insp['deadline']}").classes("text-xs font-semibold text-slate-600")

                                            with ui.row().classes("items-center gap-1.5 shrink-0"):
                                                if is_overdue:
                                                    ui.badge("ПРОСРОЧЕНО", color="red")
                                                ui.badge(st_meta["label"], color=st_meta["badge"])

                                        ui.label(insp["title"]).classes("text-sm text-slate-800 font-medium")

                                        with ui.row().classes("w-full gap-2 items-center flex-wrap"):
                                            if insp.get("uk_photo_name") and os.path.exists(insp.get("uk_photo_path", "")):
                                                ui.button(
                                                    f"Фото нарушения: {insp['uk_photo_name']}",
                                                    icon="photo_camera",
                                                    on_click=lambda p=insp["uk_photo_path"], n=insp["uk_photo_name"]: open_photo_preview(p, n),
                                                ).props("dense outline size=sm color=primary")

                                            if insp.get("tenant_photo_name") and os.path.exists(insp.get("tenant_photo_path", "")):
                                                ui.button(
                                                    f"Фото отчета: {insp['tenant_photo_name']}",
                                                    icon="task_alt",
                                                    on_click=lambda p=insp["tenant_photo_path"], n=insp["tenant_photo_name"]: open_photo_preview(p, n),
                                                ).props("dense size=sm color=positive")

                                        if insp.get("tenant_report"):
                                            with ui.row().classes("w-full p-2 bg-emerald-50 rounded border border-emerald-200 text-xs text-emerald-900"):
                                                ui.label(f"Отчет арендатора: {insp['tenant_report']}")

                                        if st != "resolved":
                                            with ui.row().classes("w-full justify-end mt-1"):
                                                ui.button(
                                                    "Закрыть предписание (Нарушение устранено)",
                                                    icon="check_circle",
                                                    color="positive",
                                                    on_click=lambda iid=insp["id"]: (
                                                        db.resolve_inspection(iid),
                                                        refresh_all(),
                                                        ui.notify(f"Предписание №{iid} успешно закрыто", type="positive"),
                                                    ),
                                                ).props("dense size=sm")


def render_tenant_passes_and_inspections(my_space_id: str, state: dict, refresh_all):
    """Раздел электронных пропусков и устранения предписаний со стороны арендатора"""
    my_passes = db.get_access_passes(space_id=my_space_id)
    my_inspections = db.get_inspections(space_id=my_space_id)

    pending_insp = [i for i in my_inspections if i["status"] != "resolved"]

    with ui.column().classes("w-full gap-4"):
        with ui.tabs().classes("w-full border-b text-slate-700") as t_subtabs:
            tab_p = ui.tab("Мои пропуска на ввоз и работы", icon="badge")
            tab_i = ui.tab(f"Предписания ПБ/СЭС ({len(pending_insp)} активных)", icon="policy")

        with ui.tab_panels(t_subtabs, value=tab_p).classes("w-full p-0 mt-2"):
            # --- ВКЛАДКА 1: МОИ ПРОПУСКА ---
            with ui.tab_panel(tab_p).classes("p-0"):
                with ui.row().classes("w-full gap-6 items-start no-wrap"):
                    # Форма подачи заявки на пропуск
                    with ui.column().classes("w-96 shrink-0 gap-3 p-4 bg-slate-50 border rounded-xl"):
                        ui.label("Подать заявку на электронный пропуск").classes("text-base font-bold text-slate-800")

                        p_type_opts = {k: v["label"] for k, v in PASS_TYPE_META.items()}
                        pass_type_sel = ui.select(options=p_type_opts, value="cargo_in", label="Тип пропуска").classes("w-full").props("outlined dense")

                        default_date = (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")
                        pass_date_inp = ui.input(label="Дата проведения (ДД.ММ.ГГГГ)", value=default_date).classes("w-full").props("outlined dense")
                        pass_time_inp = ui.input(label="Временное окно", value="22:00 - 02:00", placeholder="Например: 22:00 - 02:00").classes("w-full").props("outlined dense")

                        pass_vehicle_inp = ui.input(
                            label="Автомобиль (марка, госномер)",
                            placeholder="Например: Газель В 123 АР 196",
                        ).classes("w-full").props("outlined dense")

                        pass_workers_inp = ui.textarea(
                            label="Список сотрудников / подрядчиков",
                            placeholder="ФИО ответственного, контактный телефон, состав бригады...",
                        ).classes("w-full").props("outlined dense rows=2")

                        pass_desc_inp = ui.textarea(
                            label="Цель работ / перечень груза",
                            placeholder="Например: Завоз новой партии торгового оборудования.",
                        ).classes("w-full").props("outlined dense rows=2")

                        def submit_pass():
                            if not pass_workers_inp.value or not pass_workers_inp.value.strip():
                                ui.notify("Укажите ответственных сотрудников или подрядчиков", type="warning")
                                return
                            db.create_access_pass(
                                space_id=my_space_id,
                                pass_type=pass_type_sel.value,
                                work_date=pass_date_inp.value or default_date,
                                time_window=pass_time_inp.value or "22:00 - 02:00",
                                vehicle_info=pass_vehicle_inp.value or "",
                                workers_list=pass_workers_inp.value.strip(),
                                description=pass_desc_inp.value or "",
                            )
                            pass_workers_inp.value = ""
                            pass_desc_inp.value = ""
                            refresh_all()
                            ui.notify("Заявка на пропуск отправлена в службу безопасности ТЦ!", type="positive")

                        ui.button("Подать заявку на пропуск", icon="send", on_click=submit_pass).classes("w-full py-2").props("color=primary")

                    # Список пропусков арендатора
                    with ui.column().classes("flex-1 gap-3"):
                        ui.label("Мои электронные пропуска").classes("text-base font-bold text-slate-800")

                        if not my_passes:
                            ui.label("У вас пока нет оформленных пропусков. Оформите заявку в форме слева.").classes("text-sm text-slate-400 py-3")
                        else:
                            with ui.column().classes("w-full gap-3 max-h-[550px] overflow-y-auto pr-1"):
                                for p in my_passes:
                                    st = p["status"]
                                    st_meta = PASS_STATUS_META.get(st, PASS_STATUS_META["pending"])
                                    p_type = PASS_TYPE_META.get(p["pass_type"], {"label": p["pass_type"], "icon": "badge", "badge": "grey"})

                                    if st == "approved":
                                        # Выделенная плашка электронного пропуска для охраны
                                        with ui.column().classes("w-full p-4 border-2 border-emerald-500 bg-emerald-50/50 rounded-xl gap-2 shadow-sm"):
                                            with ui.row().classes("w-full justify-between items-center"):
                                                with ui.row().classes("items-center gap-2"):
                                                    ui.icon("verified", size="md").classes("text-emerald-600")
                                                    with ui.column().classes("gap-0"):
                                                        ui.label(f"ЭЛЕКТРОННЫЙ ПРОПУСК № {p['id']} АКТИВЕН").classes("text-base font-black text-emerald-900 tracking-wide")
                                                        ui.label("Предъявите на КПП охраны ТЦ").classes("text-xs text-emerald-700")
                                                ui.badge(p_type["label"], color=p_type["badge"])

                                            with ui.row().classes("w-full gap-4 text-xs font-semibold text-emerald-950 bg-white/80 p-2.5 rounded-lg border border-emerald-200"):
                                                ui.label(f"📅 Дата: {p['work_date']}")
                                                ui.label(f"⏰ Окно: {p['time_window']}")
                                                if p["vehicle_info"]:
                                                    ui.label(f"🚗 {p['vehicle_info']}")

                                            ui.label(f"Состав бригады: {p['workers_list']}").classes("text-xs text-slate-700")
                                            if p.get("uk_comment"):
                                                with ui.row().classes("items-center gap-1.5 p-2 bg-emerald-100 rounded text-xs font-medium text-emerald-900"):
                                                    ui.icon("info", size="xs")
                                                    ui.label(f"Указания СБ ТЦ: {p['uk_comment']}")
                                    else:
                                        card_border = "border-amber-300 bg-amber-50/30" if st == "pending" else "border-red-200 bg-red-50/30"
                                        with ui.column().classes(f"w-full p-3.5 border rounded-xl gap-1.5 {card_border}"):
                                            with ui.row().classes("w-full justify-between items-center"):
                                                with ui.row().classes("items-center gap-2"):
                                                    ui.badge(f"Заявка № {p['id']}", color="grey-8")
                                                    ui.badge(p_type["label"], color=p_type["badge"]).props("outline")
                                                    ui.label(f"Дата: {p['work_date']} ({p['time_window']})").classes("text-xs text-slate-600")
                                                ui.badge(st_meta["label"], color=st_meta["badge"])

                                            ui.label(f"Бригада: {p['workers_list']}").classes("text-xs text-slate-600")
                                            if p.get("uk_comment"):
                                                ui.label(f"Ответ СБ: {p['uk_comment']}").classes("text-xs text-red-700")

            # --- ВКЛАДКА 2: ПРЕДПИСАНИЯ ПБ И СЭС ДЛЯ АРЕНДАТОРА ---
            with ui.tab_panel(tab_i).classes("p-0"):
                ui.label("Предписания и требования проверок безопасности").classes("text-base font-bold text-slate-800 mb-2")

                if not my_inspections:
                    ui.label("Замечаний и открытых предписаний по вашему павильону нет. Все нормы соблюдены.").classes("text-sm text-slate-500 py-3")
                else:
                    with ui.column().classes("w-full gap-4 max-h-[550px] overflow-y-auto pr-1"):
                        for insp in my_inspections:
                            st = insp["status"]
                            st_meta = INSPECTION_STATUS_META.get(st, INSPECTION_STATUS_META["open"])
                            cat_meta = INSPECTION_CAT_META.get(insp["category"], {"label": insp["category"], "badge": "grey"})
                            is_overdue = st != "resolved" and db.is_due_date_passed(insp["deadline"])

                            card_cls = (
                                "border-red-300 bg-red-50/40"
                                if is_overdue
                                else ("border-blue-300 bg-blue-50/40" if st == "review" else "border-slate-200 bg-slate-50")
                            )

                            with ui.column().classes(f"w-full p-4 border rounded-xl gap-2 {card_cls}"):
                                with ui.row().classes("w-full justify-between items-center"):
                                    with ui.row().classes("items-center gap-2"):
                                        ui.badge(cat_meta["label"], color=cat_meta["badge"])
                                        ui.label(f"Срок устранения до: {insp['deadline']}").classes("text-xs font-bold text-slate-700")
                                    with ui.row().classes("items-center gap-1"):
                                        if is_overdue:
                                            ui.badge("ПРОСРОЧЕНО", color="red")
                                        ui.badge(st_meta["label"], color=st_meta["badge"])

                                ui.label(insp["title"]).classes("text-sm text-slate-800 font-semibold")

                                if insp.get("uk_photo_name") and os.path.exists(insp.get("uk_photo_path", "")):
                                    ui.button(
                                        f"Фото нарушения от УК: {insp['uk_photo_name']}",
                                        icon="photo_camera",
                                        on_click=lambda p=insp["uk_photo_path"], n=insp["uk_photo_name"]: open_photo_preview(p, n),
                                    ).props("dense outline size=sm color=primary")

                                if st == "open":
                                    # Форма отправки отчета об устранении с паттерном Черновик -> Отправить
                                    insp_state_key = f"insp_draft_{insp['id']}"
                                    if insp_state_key not in state:
                                        state[insp_state_key] = {"photo": None}

                                    with ui.column().classes("w-full gap-2 p-3 bg-white rounded-lg border mt-2"):
                                        ui.label("Отчет об устранении нарушения").classes("text-xs font-bold uppercase text-slate-600")
                                        rep_inp = ui.input(placeholder="Опишите, что было сделано...").classes("w-full").props("outlined dense")

                                        @ui.refreshable
                                        def insp_draft_box(iid=insp["id"], key=insp_state_key):
                                            cur = state[key]["photo"]
                                            if cur:
                                                with ui.row().classes("items-center gap-2 text-xs text-emerald-700 font-medium"):
                                                    ui.icon("check_circle", size="xs")
                                                    ui.label(f"Фото прикреплено: {cur[0]}")
                                            else:
                                                ui.label("Фото-подтверждение еще не прикреплено.").classes("text-xs text-slate-400")

                                        insp_draft_box()

                                        async def on_tenant_insp_photo(e: events.UploadEventArguments, key=insp_state_key):
                                            fname, fpath = await save_uploaded_file(e)
                                            state[key]["photo"] = (fname, fpath)
                                            insp_draft_box.refresh()
                                            ui.notify(f"Фото «{fname}» прикреплено", type="info")

                                        ui.upload(
                                            label="Прикрепить фото устранения",
                                            auto_upload=True,
                                            on_upload=on_tenant_insp_photo,
                                        ).classes("w-full").props("flat bordered dense")

                                        def send_insp_report(iid=insp["id"], key=insp_state_key, ri=rep_inp):
                                            cur = state[key]["photo"]
                                            p_name, p_path = cur if cur else ("", "")
                                            if not ri.value and not p_name:
                                                ui.notify("Опишите выполненные работы или приложите фото", type="warning")
                                                return
                                            db.submit_inspection_report(iid, ri.value or "Нарушение устранено", p_name, p_path)
                                            state.pop(key, None)
                                            refresh_all()
                                            ui.notify("Отчет об устранении отправлен на проверку в УК!", type="positive")

                                        ui.button(
                                            "Отправить отчет об устранении",
                                            icon="task_alt",
                                            color="positive",
                                            on_click=send_insp_report,
                                        ).classes("w-full mt-1").props("dense")
                                else:
                                    if insp.get("tenant_report"):
                                        ui.label(f"Ваш отчет: {insp['tenant_report']}").classes("text-xs text-slate-700")
                                    if insp.get("tenant_photo_name") and os.path.exists(insp.get("tenant_photo_path", "")):
                                        ui.button(
                                            f"Ваше фото: {insp['tenant_photo_name']}",
                                            icon="task_alt",
                                            on_click=lambda p=insp["tenant_photo_path"], n=insp["tenant_photo_name"]: open_photo_preview(p, n),
                                        ).props("dense flat size=sm color=primary")
