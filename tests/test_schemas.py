import pytest
from pydantic import ValidationError

from app.schemas import SMSCreate


def test_sms_request_deduplicates_numbers() -> None:
    request = SMSCreate(message="hello", phone_numbers=["+972501111111", "+972501111111"])
    assert request.phone_numbers == ["+972501111111"]


def test_sms_request_rejects_invalid_number() -> None:
    with pytest.raises(ValidationError):
        SMSCreate(message="hello", phone_numbers=["050-1234567"])
