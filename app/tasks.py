import logging
from datetime import timedelta
from uuid import UUID

from celery import Task
from sqlalchemy import select, update

from .celery_app import celery_app
from .config import settings
from .db import SessionLocal
from .models import DeliveryStatus, NotificationDelivery, OutboxEvent, OutboxStatus
from .provider import NotificationProvider, ProviderError
from .services import refresh_task_status, utcnow

logger = logging.getLogger(__name__)


class BaseTask(Task):
    autoretry_for = ()


@celery_app.task(bind=True, base=BaseTask, name="notification.process_delivery")
def process_delivery(self: BaseTask, delivery_id: str) -> None:
    delivery_uuid = UUID(delivery_id)
    now = utcnow()

    with SessionLocal() as db:
        delivery = db.scalar(
            select(NotificationDelivery)
            .where(NotificationDelivery.id == delivery_uuid)
            .with_for_update(skip_locked=False)
        )
        if not delivery:
            logger.warning("Delivery %s not found", delivery_id)
            return

        if delivery.status == DeliveryStatus.SENT:
            return

        if delivery.status != DeliveryStatus.PENDING:
            return

        if delivery.next_attempt_at and delivery.next_attempt_at > now:
            return

        delivery.status = DeliveryStatus.PROCESSING
        delivery.attempts += 1
        delivery.processing_started_at = now
        db.commit()

        task = delivery.task
        try:
            provider = NotificationProvider()
            result = provider.send_sms(task.message, delivery.destination)

            delivery.status = DeliveryStatus.SENT
            delivery.provider_message_id = extract_provider_id(result)
            delivery.last_error = None
            delivery.next_attempt_at = None
            delivery.sent_at = utcnow()
            delivery.processing_started_at = None

            refresh_task_status(db, delivery.task_id)
            db.commit()

        except ProviderError as exc:
            _handle_provider_failure(db, delivery, exc)

        except Exception as exc:
            logger.exception("Unexpected delivery failure %s", delivery_id)
            _handle_provider_failure(db, delivery, ProviderError(str(exc), transient=True))


def _handle_provider_failure(db, delivery: NotificationDelivery, exc: ProviderError) -> None:
    now = utcnow()
    delivery.last_error = str(exc)[:4000]
    delivery.processing_started_at = None

    if exc.transient and delivery.attempts < settings.max_delivery_retries:
        delay = settings.retry_backoff_base_seconds * (2 ** (delivery.attempts - 1))
        delivery.status = DeliveryStatus.PENDING
        delivery.next_attempt_at = now + timedelta(seconds=delay)

        db.add(
            OutboxEvent(
                aggregate_id=delivery.task_id,
                delivery_id=delivery.id,
                event_type="delivery.retry",
                payload={"delivery_id": str(delivery.id)},
                status=OutboxStatus.PENDING,
                available_at=delivery.next_attempt_at,
            )
        )
    else:
        delivery.status = DeliveryStatus.FAILED
        delivery.next_attempt_at = None

    refresh_task_status(db, delivery.task_id)
    db.commit()


def extract_provider_id(result) -> str | None:
    if result is None:
        return None
    if isinstance(result, str):
        return result[:255]
    if isinstance(result, dict):
        value = result.get("message_id") or result.get("id")
        return str(value)[:255] if value else None
    return None


@celery_app.task(name="notification.reap_stale_deliveries")
def reap_stale_deliveries() -> int:
    now = utcnow()
    cutoff = now - timedelta(seconds=settings.processing_timeout_seconds)

    with SessionLocal() as db:
        stale = db.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.status == DeliveryStatus.PROCESSING,
                NotificationDelivery.processing_started_at < cutoff,
            )
            .with_for_update(skip_locked=True)
        ).all()

        for delivery in stale:
            delivery.status = DeliveryStatus.PENDING
            delivery.next_attempt_at = now
            delivery.processing_started_at = None
            delivery.last_error = "Recovered stale PROCESSING delivery"
            db.add(
                OutboxEvent(
                    aggregate_id=delivery.task_id,
                    delivery_id=delivery.id,
                    event_type="delivery.requeue",
                    payload={"delivery_id": str(delivery.id)},
                    status=OutboxStatus.PENDING,
                    available_at=now,
                )
            )

        db.commit()
        return len(stale)


@celery_app.task(name="notification.publish_outbox")
def publish_outbox() -> int:
    from .outbox import publish_pending_outbox
    return publish_pending_outbox()
