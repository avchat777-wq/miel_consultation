"""Standalone MIEL event invitation. PII collection disabled unless explicitly enabled."""
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from html import escape
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="MIEL Event Invite", docs_url=None, redoc_url=None)
NETHOUSE_URL = ("https://events.nethouse.ru/form/173681/"
    "?utm_campaign=den_nedvizhimosti_0711&utm_content=website"
    "&utm_medium=referral&utm_source=favorit")
DB_FILE = Path(os.getenv("EVENT_INVITE_DB", "event_invite/invites.sqlite3"))
COLLECTION_ENABLED = os.getenv("EVENT_INVITE_COLLECTION_ENABLED", "false").lower() == "true"
CONSENT_VERSION = "draft-2026-10-19"
RETENTION_UNTIL = "2026-12-07"
LOCAL_TZ = ZoneInfo("Asia/Barnaul")


def collection_open():
    return COLLECTION_ENABLED and datetime.now(LOCAL_TZ).date() <= date.fromisoformat(RETENTION_UNTIL)


def purge_expired():
    """Delete expired rows when the app is accessed; scheduled cleanup is still required."""
    if DB_FILE.exists():
        with closing(connect()) as db, db:
            db.execute("DELETE FROM invitations WHERE retention_until < ?",
                       (datetime.now(LOCAL_TZ).date().isoformat(),))
            db.commit()



def connect():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DB_FILE), timeout=5)
    connection.execute("""CREATE TABLE IF NOT EXISTS invitations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL, created_at TEXT NOT NULL,
        consent_version TEXT NOT NULL, retention_until TEXT NOT NULL
    )""")
    return connection


@app.get("/health")
def health():
    return {"status": "ok", "collection_enabled": collection_open()}


def page(inner: str):
    return HTMLResponse("""<!doctype html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>День недвижимости — МИЭЛЬ</title><style>
body{margin:0;background:#f6f6f7;font:16px system-ui,Arial,sans-serif;color:#242424}
main{max-width:440px;margin:6vh auto;background:white;padding:28px;
border-radius:16px;box-shadow:0 4px 22px #0001}
h1{color:#960047}label{display:block;margin:15px 0}
input[type=tel]{padding:12px;box-sizing:border-box;width:100%;font-size:18px}
button,a.action{display:block;box-sizing:border-box;border:0;width:100%;text-align:center;
background:#960047;color:#fff;padding:14px;border-radius:10px;font:600 16px system-ui;
text-decoration:none;cursor:pointer}
small{color:#666}.notice{background:#fff5e9;padding:12px;border-radius:8px}
</style></head><body><main><h1>День недвижимости</h1>
<p>Приглашение от агентства недвижимости МИЭЛЬ</p>""" + inner + "</main></body></html>")


@app.get("/invite/", response_class=HTMLResponse)
def invite():
    purge_expired()
    if not collection_open():
        return page('<p class="notice">Тестовая страница: сбор телефонов выключен.</p>'
            '<a class="action" href="' + escape(NETHOUSE_URL, quote=True)
            + '">Перейти к регистрации</a>')
    return page("""<form method="post" action="/invite/register">
<label for="phone">Ваш номер телефона</label>
<input id="phone" name="phone" type="tel" autocomplete="tel" inputmode="tel"
placeholder="+7 (999) 999-99-99" required minlength="10" maxlength="24">
<label><input name="consent" value="yes" type="checkbox" required>
Даю согласие ООО «Фаворит» на обработку телефона для сопровождения приглашения.
<a href="/invite/consent">Текст согласия</a> и
<a href="/invite/privacy">Политика обработки данных</a>.</label>
<button type="submit">Перейти к регистрации</button></form>""")


@app.get("/invite/consent")
def consent():
    return page("""<h2>Согласие (тестовый проект)</h2>
<p>ООО «Фаворит», ИНН 2225204423, ОГРН 1192225027829,
barnaul@miel.ru. Обрабатываемые данные: номер телефона и факт предоставления согласия.
Цель: связь по приглашению на «День недвижимости» 7 ноября 2026 года,
уточнение намерения посетить мероприятие и помощь с регистрацией.
Действия: сбор, запись, хранение, использование, удаление.
Автоматизированная обработка. Срок хранения — до 7 декабря 2026 года
либо до отзыва согласия при отсутствии иного законного основания.
Отозвать согласие можно по адресу barnaul@miel.ru.
Согласие не распространяется на рекламные рассылки и обработку в Nethouse.</p>
<p>Документ требует окончательного утверждения оператором до запуска.</p>""")


@app.get("/invite/privacy")
def privacy():
    return page("""<h2>Политика (тестовый проект)</h2>
<p>Оператор: ООО «Фаворит», ИНН 2225204423, ОГРН 1192225027829.
Обращения: barnaul@miel.ru. Цель и состав данных — как в отдельном согласии.
Телефон хранится до 7 декабря 2026 года либо до отзыва согласия,
если не применяются другие законные основания. Доступ ограничен
уполномоченными сотрудниками. Номер не передаётся автоматически в Nethouse.
Об уточнении, удалении или отзыве согласия можно написать на указанный email.</p>
<p>Полная политика в проекте; требуется утверждение перед публикацией.</p>""")


@app.post("/invite/register")
async def register(request: Request):
    purge_expired()
    if not collection_open():
        return HTMLResponse("Приём заявок выключен", status_code=503)
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/x-www-form-urlencoded":
        return HTMLResponse("Неверный формат формы", status_code=415)
    raw = await request.body()
    if len(raw) > 2048:
        return HTMLResponse("Слишком большой запрос", status_code=413)
    form = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
    phone_values, consent_values = form.get("phone", []), form.get("consent", [])
    if len(phone_values) != 1 or len(consent_values) != 1 or consent_values[0] != "yes":
        return HTMLResponse("Необходимо указать телефон и согласие", status_code=422)
    digits = re.sub(r"\D", "", phone_values[0])
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if not (len(digits) == 11 and digits[0] == "7"):
        return HTMLResponse("Укажите российский номер телефона", status_code=422)
    with closing(connect()) as db, db:
        db.execute("INSERT INTO invitations (phone,created_at,consent_version,retention_until)"
                   " VALUES (?,?,?,?)",
                   ("+" + digits, datetime.now(timezone.utc).isoformat(), CONSENT_VERSION, RETENTION_UNTIL))
        db.commit()
    return RedirectResponse(NETHOUSE_URL, status_code=303)
