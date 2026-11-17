from nicegui import ui
import database as db
from landlord_page import register_landlord_page
from login_page import register_login_page
from tenant_page import register_tenant_page

db.init_db()

register_login_page()
register_landlord_page()
register_tenant_page()

ui.run(
    title="MallService — Вход и управление ТЦ",
    port=8080,
    storage_secret="mallservice_super_secret_key_2026",
)