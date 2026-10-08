import logging
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    def __init__(self, message: str, transient: bool = True):
        super().__init__(message)
        self.transient = transient


class NotificationProvider:
    def __init__(self) -> None:
        if settings.use_fake_provider:
            self._send_sms = self._fake_sms
            self._send_email = self._fake_email
            self._send_slack = self._fake_slack
        else:
            try:
                from ThirdParty import send_email, send_slack, send_sms  # type: ignore
            except ImportError as exc:
                raise RuntimeError(
                    "USE_FAKE_PROVIDER=false but ThirdParty package is not installed"
                ) from exc
            self._send_sms = send_sms
            self._send_email = send_email
            self._send_slack = send_slack

    def send_sms(self, message: str, phone_number: str) -> Any:
        return self._safe_call(self._send_sms, message, phone_number)

    def send_email(self, subject: str, body: str, address: str) -> Any:
        return self._safe_call(self._send_email, subject, body, address)

    def send_slack(self, message: str, channel: str, color: str) -> Any:
        return self._safe_call(self._send_slack, message, channel, color)

    @staticmethod
    def _safe_call(fn, *args) -> Any:
        try:
            return fn(*args)
        except ProviderError:
            raise
        except TimeoutError as exc:
            raise ProviderError(str(exc), transient=True) from exc
        except ConnectionError as exc:
            raise ProviderError(str(exc), transient=True) from exc
        except ValueError as exc:
            raise ProviderError(str(exc), transient=False) from exc
        except Exception as exc:
            # Conservative default for an unknown provider exception.
            raise ProviderError(str(exc), transient=True) from exc

    @staticmethod
    def _fake_sms(message: str, number: str) -> dict[str, str]:
        logger.info("FAKE SMS -> %s: %s", number, message)
        return {"message_id": f"fake-sms-{number[-4:]}"}

    @staticmethod
    def _fake_email(subject: str, body: str, address: str) -> dict[str, str]:
        logger.info("FAKE EMAIL -> %s: %s", address, subject)
        return {"message_id": f"fake-email-{address}"}

    @staticmethod
    def _fake_slack(message: str, channel: str, color: str) -> dict[str, str]:
        logger.info("FAKE SLACK -> #%s [%s]: %s", channel, color, message)
        return {"message_id": f"fake-slack-{channel}"}
