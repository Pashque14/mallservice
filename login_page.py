from nicegui import app, ui
import database as db


def register_login_page():
    @ui.page("/login")
    def login_page():
        ui.colors(primary="#2563eb")

        current_user = app.storage.user.get("user")
        if current_user:
            ui.navigate.to("/" if current_user["role"] == "landlord" else "/tenant")
            return

        with ui.column().classes("w-full min-h-screen items-center justify-center bg-slate-100 p-4"):
            with ui.card().classes("w-full max-w-sm p-6 gap-4 shadow-md"):
                ui.label("Вход в MallService").classes("text-2xl font-bold text-slate-800 text-center w-full")
                ui.label("Введите логин и пароль из файла credentials.txt").classes("text-xs text-slate-500 text-center w-full -mt-2")

                username_input = ui.input("Логин").classes("w-full").props("outlined")
                password_input = ui.input("Пароль", password=True, password_toggle_button=True).classes("w-full").props("outlined")

                def try_login():
                    user = db.authenticate_user(username_input.value or "", password_input.value or "")
                    if not user:
                        ui.notify("Неверный логин или пароль", type="negative")
                        return

                    app.storage.user["user"] = user
                    ui.notify(f"Добро пожаловать, {user['display_name']}!", type="positive")
                    ui.navigate.to("/" if user["role"] == "landlord" else "/tenant")

                password_input.on("keydown.enter", try_login)
                ui.button("Войти", on_click=try_login).classes("w-full mt-2")