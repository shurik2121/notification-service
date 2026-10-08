from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import DeliveryStatus, NotificationType, TaskStatus


class SMSCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4096)
    phone_numbers: list[str] = Field(min_length=1, max_length=1000)

    @field_validator("phone_numbers")
    @classmethod
    def validate_phone_numbers(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            number = value.strip()
            if not number.startswith("+") or not number[1:].isdigit():
                raise ValueError(f"Invalid phone number: {value}")
            if not 8 <= len(number[1:]) <= 15:
                raise ValueError(f"Phone number must contain 8-15 digits: {value}")
            cleaned.append(number)
        # `dict.fromkeys()` guarantee the original order when `set()` is not
        return list(dict.fromkeys(cleaned))


class TaskAccepted(BaseModel):
    task_id: UUID
    status: TaskStatus


class DeliveryResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    destination: str
    status: DeliveryStatus
    attempts: int
    provider_message_id: str | None = None
    last_error: str | None = None
    next_attempt_at: datetime | None = None
    sent_at: datetime | None = None


class TaskResult(BaseModel):
    task_id: UUID
    type: NotificationType
    status: TaskStatus
    message: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    deliveries: list[DeliveryResult]
