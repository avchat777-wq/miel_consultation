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
        self.assertIn("Выберите удобное время", page.text)
        self.assertEqual({"status": "ok", "service": "miel-consultation"}, health.json())

    @patch("app.main.IntrumLeadClient")
    def test_booking_endpoint_returns_201(self, intrum_client) -> None:
        intrum_client.return_value.submit.return_value = {"customer": 9, "request": 27}
        client = TestClient(app)
        response = client.post(
            "/api/consultation/book",
            json={
                "name": "Анна",
                "phone": "89001234567",
                "meeting_date": "2026-07-30",
                "meeting_time": "15:30",
                "confirmation_method": "call",
                "flow": "slot",
            },
        )
        self.assertEqual(201, response.status_code)
        self.assertTrue(response.json()["request_created"])


if __name__ == "__main__":
    unittest.main()

