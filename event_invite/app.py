"""Isolated event invitation prototype.

This module deliberately does not collect or persist personal data yet.
Run: uvicorn event_invite.app:app --host 127.0.0.1 --port 8070
"""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="MIEL Event Invitation", docs_url=None, redoc_url=None)

NETHOUSE_URL = (
    "https://events.nethouse.ru/form/173681/"
    "?utm_campaign=den_nedvizhimosti_0711"
    "&utm_content=website&utm_medium=referral&utm_source=favorit"
)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "miel-event-invite"}

@app.get("/invite/", response_class=HTMLResponse)
def invite() -> str:
    # No phone field or tracking until the operator's privacy documents
    # and retention policy have been approved.
    return """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>День недвижимости — МИЭЛЬ</title>
<style>
body{margin:0;background:#f5f5f5;font:16px system-ui,Arial,sans-serif;color:#222}
main{max-width:440px;margin:7vh auto;background:white;padding:28px;border-radius:16px;box-shadow:0 4px 22px #0001}
h1{color:#960047;margin-top:0}a{display:block;text-align:center;background:#960047;color:#fff;
padding:14px;border-radius:10px;text-decoration:none;font-weight:600}
small{display:block;margin-top:18px;color:#666}
</style></head><body><main><h1>День недвижимости</h1>
<p>Приглашение от агентства недвижимости МИЭЛЬ.</p>
<p>Для участия заполните форму организатора мероприятия.</p>
<a href=""""+NETHOUSE_URL+"""" rel="noopener noreferrer" target="_blank">Перейти к регистрации</a>
<small>Тестовый макет. Телефон и другие данные здесь не собираются.</small>
</main></body></html>"""
