# MIEL Consultation

Независимый FastAPI-сервис для записи на персональную консультацию по QR-коду.
Не импортирует и не использует Intrum Call Collector.

## Возможности

- `GET /consultation` — mobile-first страница записи;
- `POST /api/consultation/book` — валидация и создание контакта + заявки в Intrum;
- `GET /health` — healthcheck контейнера;
- отдельный API-ключ Intrum только на сервере;
- UTM-метки, основной и индивидуальный сценарии, honeypot и rate limit;
- Dockerfile и Docker Compose для самостоятельного деплоя.

## Настройка

```powershell
Copy-Item .env.example .env
```

Обязательные значения в `.env`:

```env
INTRUM_LEADS_API_KEY=отдельный-ключ-с-правами-на-контакты-и-заявки
INTRUM_REQUEST_TYPE_ID=идентификатор-типа-заявки
```

Опционально укажите ответственного, тип контакта и прямые ссылки Telegram/MAX.
Официальный логотип нужно положить в макет перед производственным запуском: текущий
блок намеренно является заглушкой и не имитирует фирменный знак.

## Локальный запуск

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Открыть: `http://127.0.0.1:8000/consultation`.

Тесты:

```powershell
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

## Docker

```powershell
docker compose up -d --build
docker compose ps
```

## Запрос API

```json
{
  "name": "Анна",
  "phone": "+7 900 123-45-67",
  "meeting_date": "2026-07-30",
  "meeting_time": "15:30",
  "confirmation_method": "messenger",
  "flow": "slot",
  "utm_source": "qr",
  "utm_medium": "offline",
  "utm_campaign": "business_women_event"
}
```

Intrum получает технический `source=online_form`; бизнес-источник, дата, время и
UTM сохраняются в названии заявки.
