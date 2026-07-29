import os
import unittest
from datetime import date
from unittest.mock import Mock, patch

os.environ.setdefault("INTRUM_LEADS_API_KEY", "test-lead-key")
os.environ.setdefault("INTRUM_REQUEST_TYPE_ID", "12")
os.environ.setdefault("RATE_LIMIT_REQUESTS", "100")

from fastapi.testclient import TestClient

from app.config import Settings
from app.intrum import IntrumLeadClient, php_form_encode
from app.main import app
from app.schemas import ConsultationBooking


class MielConsultationTests(unittest.TestCase):
    def test_php_form_encode_supports_intrum_arrays(self) -> None:
        encoded = php_form_encode({"params": {"customer": {"phone": [{"phone": "+79001234567"}]}}})
        self.assertEqual("+79001234567", encoded["params[customer][phone][0][phone]"])

    def test_phone_is_normalized(self) -> None:
        booking = ConsultationBooking(
            name="Анна",
            phone="8 900 123-45-67",
            meeting_date=date(2026, 7, 30),
            meeting_time="15:30",
        )
        self.assertEqual("+79001234567", booking.phone)

    def test_slot_requires_date_and_time(self) -> None:
        with self.assertRaises(ValueError):
            ConsultationBooking(name="Анна", phone="89001234567")

    def test_intrum_add_customer_payload(self) -> None:
        session = Mock()
        session.post.return_value.json.return_value = {
            "status": "success",
            "data": {"customer": 9, "request": 27},
        }
        settings = Settings(
            _env_file=None,
            intrum_leads_api_key="lead-key",
            intrum_request_type_id=12,
            intrum_employee_id=62,
            intrum_contact_marktype_id=4,
        )
        booking = ConsultationBooking(
            name="Анна",
            phone="89001234567",
            meeting_date=date(2026, 7, 30),
            meeting_time="15:30",
            confirmation_method="messenger",
        )

        result = IntrumLeadClient(settings, session=session).submit(booking)

        self.assertEqual(27, result["request"])
        sent = session.post.call_args.kwargs["data"]
        self.assertEqual("+79001234567", sent["params[customer][phone][0][phone]"])
        self.assertEqual("12", sent["params[request][request_type]"])
        self.assertEqual("mustbeprocessed", sent["params[request][status]"])
        self.assertIn("QR_мероприятие_женщины_бизнес", sent["params[request][request_name]"])

    def test_page_and_health_are_available(self) -> None:
        client = TestClient(app)
        page = client.get("/consultation?utm_source=qr")
        health = client.get("/health")
        self.assertEqual(200, page.status_code)
        self.assertIn("Выберите удобное время встречи", page.text)
        self.assertIn("Персональное приглашение", page.text)
        self.assertIn('src="data:image/png;base64,', page.text)
        self.assertIn("Стратегическая консультация", page.text)
        self.assertIn("Для участниц женского бизнес-клуба", page.text)
        self.assertIn("«ICONA» Марины Плагиной", page.text)
        self.assertIn("с экспертом рынка недвижимости ГК «МИЭЛЬ»", page.text)
        self.assertIn("сохранение капитала и защиту интересов семьи", page.text)
        self.assertIn("Ваше время:", page.text)
        self.assertIn("const bookingEndpoint=", page.text)
        self.assertIn("Не удалось связаться с сервисом записи", page.text)
        self.assertIn("Введите корректный номер телефона", page.text)
        self.assertIn("Проверьте имя", page.text)
        self.assertNotIn("throw new Error(result.detail", page.text)
        self.assertIn("Подтвердить встречу", page.text)
        self.assertIn("Не хотите оставлять телефон?", page.text)
        self.assertIn('href="https://t.me/Vikki_brn"', page.text)
        self.assertIn('rel="noopener noreferrer"', page.text)
        self.assertEqual(1, page.text.count('href="https://t.me/Vikki_brn"'))
        self.assertNotIn("МЕСТО ДЛЯ ОФИЦИАЛЬНОГО ЛОГОТИПА", page.text)
        self.assertNotIn("Забронировать встречу", page.text)
        self.assertNotIn("Выберите удобное время для личной встречи", page.text)
        self.assertIn("iso:'2026-08-04'", page.text)
        self.assertIn("iso:'2026-08-07'", page.text)
        self.assertEqual(4, page.text.count("iso:'2026-08-"))
        self.assertNotIn("iso:'2026-07-30'", page.text)
        self.assertIn('id="success-close"', page.text)
        self.assertIn("Запрос отправлен", page.text)
        self.assertIn("calendarAdd.hidden=!isSlot", page.text)
        self.assertIn("setTimeout(closeSuccess,750)", page.text)
        self.assertIn("successDialog.addEventListener('close',resetBookingState)", page.text)
        self.assertIn("individualForm.querySelector", page.text)
        self.assertIn("disabled=false", page.text)
        self.assertEqual({"status": "ok", "service": "miel-consultation"}, health.json())

    def test_invalid_phone_returns_structured_validation_error(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/api/consultation/book",
            json={
                "name": "Анна",
                "phone": "22222",
                "meeting_date": "2026-08-04",
                "meeting_time": "12:00",
                "confirmation_method": "call",
                "flow": "slot",
            },
        )
        self.assertEqual(422, response.status_code)
        detail = response.json()["detail"]
        self.assertTrue(any(error["loc"][-1] == "phone" for error in detail))

    def test_booking_endpoint_allows_local_preview_preflight(self) -> None:
        client = TestClient(app)
        for origin in ("null", "http://127.0.0.1:5500", "http://localhost:5173"):
            with self.subTest(origin=origin):
                response = client.options(
                    "/api/consultation/book",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type",
                    },
                )
                self.assertEqual(200, response.status_code)
                self.assertEqual(
                    origin,
                    response.headers["access-control-allow-origin"],
                )

    def test_booking_endpoint_rejects_external_preflight(self) -> None:
        client = TestClient(app)
        response = client.options(
            "/api/consultation/book",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(400, response.status_code)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_static_assets_are_mounted(self) -> None:
        client = TestClient(app)
        response = client.get("/static/images/.gitkeep")
        self.assertEqual(200, response.status_code)

    @patch("app.main.IntrumLeadClient")
    def test_booking_endpoint_returns_201(self, intrum_client) -> None:
        intrum_client.return_value.submit.return_value = {"customer": 9, "request": 27}
        client = TestClient(app)
        response = client.post(
            "/api/consultation/book",
            json={
                "name": "Анна",
                "phone": "89001234567",
                "meeting_date": "2026-08-04",
                "meeting_time": "15:30",
                "confirmation_method": "call",
                "flow": "slot",
            },
        )
        self.assertEqual(201, response.status_code)
        self.assertTrue(response.json()["request_created"])
        booking = intrum_client.return_value.submit.call_args.args[0]
        self.assertEqual(date(2026, 8, 4), booking.meeting_date)

    @patch("app.main.IntrumLeadClient")
    def test_second_slot_does_not_reuse_previous_date(self, intrum_client) -> None:
        intrum_client.return_value.submit.return_value = {"customer": 10, "request": 28}
        client = TestClient(app)
        response = client.post(
            "/api/consultation/book",
            json={
                "name": "Марина",
                "phone": "89005556677",
                "meeting_date": "2026-08-07",
                "meeting_time": "16:00",
                "confirmation_method": "messenger",
                "flow": "slot",
            },
        )
        self.assertEqual(201, response.status_code)
        booking = intrum_client.return_value.submit.call_args.args[0]
        self.assertEqual(date(2026, 8, 7), booking.meeting_date)
        self.assertEqual("16:00", booking.meeting_time)

    @patch("app.main.IntrumLeadClient")
    def test_individual_flow_does_not_require_slot(self, intrum_client) -> None:
        intrum_client.return_value.submit.return_value = {"customer": 11, "request": 29}
        client = TestClient(app)
        response = client.post(
            "/api/consultation/book",
            json={
                "name": "Ольга",
                "phone": "89001112233",
                "confirmation_method": "call",
                "flow": "individual",
            },
        )
        self.assertEqual(201, response.status_code)
        booking = intrum_client.return_value.submit.call_args.args[0]
        self.assertIsNone(booking.meeting_date)
        self.assertIsNone(booking.meeting_time)


if __name__ == "__main__":
    unittest.main()
