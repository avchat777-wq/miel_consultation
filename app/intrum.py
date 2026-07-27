from typing import Any

import requests

from app.config import Settings
from app.schemas import ConsultationBooking


DEFAULT_UTM = {
    "utm_source": "qr",
    "utm_medium": "offline",
    "utm_campaign": "business_women_event",
}


def php_form_encode(value: object, prefix: str = "") -> dict[str, str]:
    """Encode nested values like PHP_QUERY_RFC1738 for Intrum API v2."""
    result: dict[str, str] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{prefix}[{key}]" if prefix else str(key)
            result.update(php_form_encode(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.update(php_form_encode(item, f"{prefix}[{index}]"))
    elif value is not None:
        result[prefix] = "1" if value is True else "0" if value is False else str(value)
    return result


class IntrumConfigurationError(RuntimeError):
    pass


class IntrumResponseError(RuntimeError):
    pass


class IntrumLeadClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        if not settings.intrum_leads_api_key:
            raise IntrumConfigurationError("INTRUM_LEADS_API_KEY is not configured")
        if not settings.intrum_request_type_id:
            raise IntrumConfigurationError("INTRUM_REQUEST_TYPE_ID is not configured")
        self.url = f"{settings.normalized_intrum_base_url}/sharedapi/applications/addCustomer"
        self.api_key = settings.intrum_leads_api_key
        self.request_type_id = settings.intrum_request_type_id
        self.employee_id = settings.intrum_employee_id
        self.marktype_id = settings.intrum_contact_marktype_id
        self.timeout = settings.intrum_timeout_seconds
        self.source_label = settings.consultation_source
        self.timezone = settings.consultation_timezone
        self.session = session or requests.Session()

    def submit(self, booking: ConsultationBooking) -> dict[str, Any]:
        meeting = (
            f"{booking.meeting_date.isoformat()} {booking.meeting_time} {self.timezone}"
            if booking.flow == "slot"
            else "индивидуальное согласование времени"
        )
        confirmation = "мессенджер" if booking.confirmation_method == "messenger" else "звонок"
        utm = {
            "utm_source": booking.utm_source or DEFAULT_UTM["utm_source"],
            "utm_medium": booking.utm_medium or DEFAULT_UTM["utm_medium"],
            "utm_campaign": booking.utm_campaign or DEFAULT_UTM["utm_campaign"],
        }
        customer: dict[str, Any] = {
            "name": booking.name,
            "surname": "",
            "secondname": "",
            "phone": [{"phone": booking.phone, "comment": "персональное приглашение"}],
        }
        if self.marktype_id:
            customer["marktype"] = self.marktype_id
        request_data: dict[str, Any] = {
            "request_type": self.request_type_id,
            "source": "online_form",
            "status": "mustbeprocessed",
            "request_name": (
                f"Персональная консультация | {self.source_label} | {meeting} | "
                f"подтверждение: {confirmation} | "
                f"utm: {utm['utm_source']}/{utm['utm_medium']}/{utm['utm_campaign']}"
            ),
        }
        if self.employee_id:
            request_data["employee_id"] = self.employee_id
        payload = {
            "apikey": self.api_key,
            "params": {"customer": customer, "request": request_data},
        }
        response = self.session.post(
            self.url,
            data=php_form_encode(payload),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or result.get("status") != "success":
            message = result.get("message", "UNKNOWN_RESPONSE") if isinstance(result, dict) else "UNKNOWN_RESPONSE"
            raise IntrumResponseError(f"Intrum API error: {message}")
        data = result.get("data", result)
        if not isinstance(data, dict) or not (data.get("request") or data.get("id")):
            raise IntrumResponseError("Intrum did not return a request id")
        return data

