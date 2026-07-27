import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ConsultationBooking(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=10, max_length=24)
    meeting_date: date | None = None
    meeting_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    confirmation_method: Literal["call", "messenger"] = "call"
    flow: Literal["slot", "individual"] = "slot"
    website: str = Field(default="", max_length=100)
    utm_source: str | None = Field(default=None, max_length=40)
    utm_medium: str | None = Field(default=None, max_length=40)
    utm_campaign: str | None = Field(default=None, max_length=80)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not re.fullmatch(r"[A-Za-zА-Яа-яЁё\- ]+", cleaned):
            raise ValueError("Укажите имя буквами")
        return cleaned

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value)
        if len(digits) == 11 and digits[0] in "78":
            return "+7" + digits[1:]
        if len(digits) == 10:
            return "+7" + digits
        raise ValueError("Укажите российский номер телефона")

    @model_validator(mode="after")
    def validate_flow(self) -> "ConsultationBooking":
        if self.website:
            raise ValueError("Некорректная отправка")
        if self.flow == "slot" and (not self.meeting_date or not self.meeting_time):
            raise ValueError("Выберите дату и время")
        if self.flow == "individual":
            self.meeting_date = None
            self.meeting_time = None
        return self


class BookingAccepted(BaseModel):
    status: Literal["accepted"] = "accepted"
    request_created: bool = True
    meeting_date: date | None = None
    meeting_time: str | None = None
    flow: Literal["slot", "individual"]

