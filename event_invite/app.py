"""Standalone MIEL event invitation. PII collection disabled unless explicitly enabled."""
import os
import hashlib
import hmac
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone, date, timedelta
from zoneinfo import ZoneInfo
from html import escape
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

app = FastAPI(title="MIEL Event Invite", docs_url=None, redoc_url=None)
NETHOUSE_URL = ("https://events.nethouse.ru/buy_tickets/173681"
    "?utm_source=miel&utm_medium=referral"
    "&utm_campaign=den_nedvizhimosti_0711&utm_content=website")
DB_FILE = Path(os.getenv("EVENT_INVITE_DB", "event_invite/invites.sqlite3"))
COLLECTION_ENABLED = os.getenv("EVENT_INVITE_COLLECTION_ENABLED", "false").lower() == "true"
CONSENT_VERSION = "2026-10-19-v1"
RETENTION_UNTIL = "2026-12-07"
LOCAL_TZ = ZoneInfo("Asia/Barnaul")

AGENTS = {
    "22": "Алексеева Инна",
    "193": "Георгиева Ольга",
    "603": "Гехт Евгений",
    "34": "Гольцова Евгения",
    "40": "Горбунов Александр",
    "7": "Еремин Роман",
    "606": "Ермина Лариса",
    "582": "Ефимов Александр",
    "42": "Золотарева Анастасия",
    "599": "Кандрашина Наталья",
    "30": "Карпочев Игорь",
    "13": "Кириллова Виктория",
    "569": "Климова Елена",
    "596": "Ковылина Екатерина",
    "585": "Козка Лилия",
    "593": "Козырева Дарья",
    "305": "Колесникова Евгения",
    "19": "Коломеец Светлана",
    "88": "Коновалова Анна",
    "586": "Кононов Данил",
    "570": "Михайлин Андрей",
    "99": "Назарова Светлана",
    "592": "Напреенков Илья",
    "590": "Петрова Веорика",
    "36": "Погудина Ирина",
    "52": "Погудина Марина",
    "131": "Подъяпольский Роман",
    "608": "Тимошенко Оксана",
    "129": "Усольцева Александра",
    "591": "Харитонов Никита",
    "21": "Шаргородская Наталья",
    "577": "Шеремет Даниил",
}


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
        consent_version TEXT NOT NULL, retention_until TEXT NOT NULL,
        consent_sha256 TEXT NOT NULL DEFAULT '',
        agent_id TEXT NOT NULL DEFAULT '',
        agent_name TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT ''
    )""")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(invitations)")}
    if "consent_sha256" not in columns:
        connection.execute("ALTER TABLE invitations ADD COLUMN consent_sha256 TEXT NOT NULL DEFAULT ''")
    if "agent_id" not in columns:
        connection.execute("ALTER TABLE invitations ADD COLUMN agent_id TEXT NOT NULL DEFAULT ''")
    if "agent_name" not in columns:
        connection.execute("ALTER TABLE invitations ADD COLUMN agent_name TEXT NOT NULL DEFAULT ''")
    if "source" not in columns:
        connection.execute("ALTER TABLE invitations ADD COLUMN source TEXT NOT NULL DEFAULT ''")
    return connection


@app.get("/health")
def health():
    return {"status": "ok", "collection_enabled": collection_open()}


def page(inner: str):
    return HTMLResponse("""<!doctype html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>День недвижимости — регистрация и билет</title>
<meta name="description" content="Перейдите по ссылке, зарегистрируйтесь и получите билет на мероприятие «День недвижимости».">
<meta property="og:title" content="День недвижимости — регистрация и билет">
<meta property="og:description" content="Перейдите по ссылке, зарегистрируйтесь и получите билет на мероприятие «День недвижимости».">
<meta property="og:type" content="website">
<style>
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


@app.get("/s")
def sms_invite():
    return RedirectResponse("/invite/?source=sms_robot", status_code=302)


@app.get("/invite/", response_class=HTMLResponse)
def invite(request: Request):
    purge_expired()
    agent_id = request.query_params.get("agent_id", "")
    if agent_id not in AGENTS:
        agent_id = ""
    source = request.query_params.get("source", "")
    if source != "sms_robot":
        source = ""
    if not collection_open():
        return page('<p class="notice">Тестовая страница: сбор телефонов выключен.</p>'
            '<a class="action" href="' + escape(NETHOUSE_URL, quote=True)
            + '">Перейти к регистрации</a>')
    agent_field = (
        '<input type="hidden" name="agent_id" value="' + escape(agent_id, quote=True) + '">'
        if agent_id else ""
    )
    source_field = (
        '<input type="hidden" name="source" value="sms_robot">'
        if source == "sms_robot" else ""
    )
    return page("""<form method="post" action="/invite/register">""" + agent_field + source_field + """
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
    return page("""<h2>Согласие на обработку персональных данных</h2>
<p>Я даю согласие ООО «Фаворит» (ИНН 2225204423, ОГРН 1192225027829)
на обработку моего номера телефона в целях приглашения на мероприятие
«День недвижимости», которое состоится 7 ноября 2026 года, уточнения
моего намерения участвовать и оказания помощи в регистрации.</p>
<p>Согласие распространяется на сбор, запись, хранение, использование
и удаление номера телефона с применением средств автоматизации.</p>
<p>Согласие действует до 7 декабря 2026 года включительно и может быть
отозвано ранее путём обращения по электронной почте barnaul@miel.ru.
При отзыве согласия обработка прекращается, а данные удаляются, если
отсутствуют иные законные основания для их обработки.</p>
<p>Настоящее согласие не распространяется на рекламные звонки,
рассылки и предложения услуг недвижимости.</p>
<p>После перехода на сайт организатора мероприятия регистрация
осуществляется самостоятельно. Обработка данных организатором
регулируется его собственными документами.</p>
""")


@app.get("/invite/privacy")
def privacy():
    return page("""<h2>Политика обработки персональных данных посетителей страницы приглашения</h2>
<h3>1. Оператор персональных данных</h3>
<p>Оператором персональных данных является ООО «Фаворит»
(ИНН 2225204423, ОГРН 1192225027829). Контактный адрес
электронной почты: barnaul@miel.ru.</p>
<h3>2. Какие данные обрабатываются</h3>
<p>При заполнении формы приглашения обрабатываются: номер телефона
посетителя; дата и время предоставления согласия; сведения о версии
предоставленного согласия.</p>
<h3>3. Цель обработки</h3>
<p>Данные используются исключительно для приглашения на мероприятие
«День недвижимости» 7 ноября 2026 года, уточнения намерения посетить
мероприятие и оказания помощи в регистрации.</p>
<p>Номер телефона не используется для рекламных звонков, рассылок
и предложений услуг недвижимости на основании данного согласия.</p>
<h3>4. Порядок обработки</h3>
<p>Обработка включает сбор, запись, хранение, использование и удаление
данных с применением средств автоматизации. Доступ к данным
предоставляется только уполномоченным сотрудникам оператора.</p>
<h3>5. Срок хранения</h3>
<p>Данные хранятся до 7 декабря 2026 года включительно, если согласие
не отозвано ранее и отсутствуют иные законные основания для
продолжения обработки. По окончании срока хранения данные подлежат удалению.</p>
<h3>6. Передача данных организатору мероприятия</h3>
<p>После отправки формы посетитель перенаправляется на сайт организатора
мероприятия — Nethouse Events — для самостоятельного завершения регистрации.</p>
<p>Номер телефона из формы МИЭЛЬ автоматически организатору не передаётся.
Обработка сведений, которые посетитель самостоятельно вводит на сайте
организатора, регулируется документами соответствующего оператора.</p>
<h3>7. Права посетителя</h3>
<p>Посетитель вправе запросить сведения об обработке своего номера
телефона, потребовать его уточнения или удаления, а также отозвать
согласие. Обращения направляются по электронной почте barnaul@miel.ru.</p>
<h3>8. Защита персональных данных</h3>
<p>Оператор применяет организационные и технические меры по ограничению
несанкционированного доступа к персональным данным.</p>
""")


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
    agent_values = form.get("agent_id", [])
    source_values = form.get("source", [])
    if len(source_values) > 1:
        return HTMLResponse("Неверный источник приглашения", status_code=422)
    source = source_values[0] if source_values else ""
    if source != "sms_robot":
        source = ""
    if len(agent_values) > 1:
        return HTMLResponse("Неверная ссылка приглашения", status_code=422)
    agent_id = agent_values[0] if agent_values else ""
    if agent_id not in AGENTS:
        agent_id = ""
    agent_name = AGENTS.get(agent_id, "")
    if len(phone_values) != 1 or len(consent_values) != 1 or consent_values[0] != "yes":
        return HTMLResponse("Необходимо указать телефон и согласие", status_code=422)
    digits = re.sub(r"\D", "", phone_values[0])
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if not (len(digits) == 11 and digits[0] == "7"):
        return HTMLResponse("Укажите российский номер телефона", status_code=422)
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=10)).isoformat()
    with closing(connect()) as db, db:
        # Atomically serialize the check and insert across simultaneous requests.
        db.execute("BEGIN IMMEDIATE")
        duplicate = db.execute(
            "SELECT 1 FROM invitations WHERE phone = ? AND created_at >= ? LIMIT 1",
            ("+" + digits, cutoff),
        ).fetchone()
        if not duplicate:
            db.execute(
                "INSERT INTO invitations (phone,created_at,consent_version,retention_until,consent_sha256,agent_id,agent_name,source)"
                " VALUES (?,?,?,?,?,?,?,?)",
                ("+" + digits, now.isoformat(), CONSENT_VERSION, RETENTION_UNTIL,
                 hashlib.sha256(consent().body).hexdigest(), agent_id, agent_name, source),
            )
    return RedirectResponse(NETHOUSE_URL, status_code=303)


@app.get("/invite/admin/contacts")
def admin_contacts(request: Request):
    """Read-only report. Fail closed when no long server-side token is configured."""
    expected = os.getenv("EVENT_INVITE_ADMIN_TOKEN", "")
    if len(expected) < 32:
        return JSONResponse({"detail": "Report disabled"}, status_code=503,
                            headers={"Cache-Control": "no-store"})
    supplied = request.headers.get("X-Invite-Admin-Token", "")
    if not hmac.compare_digest(supplied, expected):
        return JSONResponse({"detail": "Forbidden"}, status_code=403,
                            headers={"Cache-Control": "no-store"})
    purge_expired()
    if not DB_FILE.exists():
        contacts = []
    else:
        with closing(connect()) as db:
            contacts = [
                {
                    "id": row[0],
                    "phone": row[1],
                    "created_at": row[2],
                    "agent_id": row[3] or None,
                    "agent_name": row[4] or None,
                    "source": row[5] or None,
                }
                for row in db.execute(
                    "SELECT id, phone, created_at, agent_id, agent_name, source "
                    "FROM invitations ORDER BY id DESC"
                ).fetchall()
            ]
    return JSONResponse({"count": len(contacts), "contacts": contacts},
                        headers={"Cache-Control": "no-store"})
