import html
import json
import logging

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.intrum import DEFAULT_UTM, IntrumConfigurationError, IntrumLeadClient, IntrumResponseError
from app.rate_limit import RateLimiter
from app.schemas import BookingAccepted, ConsultationBooking


settings = get_settings()
app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["null"],
    allow_origin_regex=r"^https?://(?:localhost|127\.0\.0\.1)(?::\d+)?$",
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
logger = logging.getLogger(__name__)
rate_limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "miel-consultation"}


@app.get("/consultation", response_class=HTMLResponse)
def consultation_page(request: Request) -> HTMLResponse:
    campaign = {
        key: request.query_params.get(key, default)
        for key, default in DEFAULT_UTM.items()
    }
    frontend_config = {
        "campaign": campaign,
        "public_base_url": settings.public_base_url,
        "location": settings.consultation_location,
        "telegram_url": settings.telegram_url,
        "max_url": settings.max_url,
    }
    page = (settings.static_dir / "consultation.html").read_text(encoding="utf-8")
    page = page.replace(
        "__FRONTEND_CONFIG__",
        html.escape(json.dumps(frontend_config, ensure_ascii=False)),
    )
    return HTMLResponse(page)


@app.post("/api/consultation/book", response_model=BookingAccepted, status_code=201)
def book_consultation(booking: ConsultationBooking, request: Request) -> BookingAccepted:
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client_ip):
        raise HTTPException(status_code=429, detail="Слишком много попыток. Повторите через несколько минут.")
    try:
        IntrumLeadClient(settings).submit(booking)
    except IntrumConfigurationError as exc:
        logger.error("Intrum lead integration is not configured: %s", exc)
        raise HTTPException(status_code=503, detail="Запись скоро станет доступна. Выберите связь в мессенджере.") from exc
    except (IntrumResponseError, requests.RequestException, ValueError) as exc:
        logger.exception("Could not create Intrum consultation request")
        raise HTTPException(status_code=502, detail="Не удалось передать запись. Пожалуйста, попробуйте ещё раз.") from exc
    return BookingAccepted(
        meeting_date=booking.meeting_date,
        meeting_time=booking.meeting_time,
        flow=booking.flow,
    )
