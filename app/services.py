from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .models import DeliveryStatus, NotificationDelivery, NotificationTask, TaskStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def calculate_task_status(deliveries: list[NotificationDelivery]) -> TaskStatus:
    if not deliveries:
        return TaskStatus.FAILED

    statuses = {delivery.status for delivery in deliveries}

    if statuses == {DeliveryStatus.SENT}:
        return TaskStatus.COMPLETED

    if DeliveryStatus.PROCESSING in statuses or DeliveryStatus.PENDING in statuses:
        return TaskStatus.PROCESSING

    if DeliveryStatus.SENT in statuses and DeliveryStatus.FAILED in statuses:
        return TaskStatus.PARTIAL

    if statuses == {DeliveryStatus.FAILED}:
        return TaskStatus.FAILED

    return TaskStatus.PROCESSING


def refresh_task_status(db: Session, task_id: UUID) -> None:
    task = db.scalar(select(NotificationTask).where(NotificationTask.id == task_id))
    if not task:
        return

    deliveries = db.scalars(select(NotificationDelivery).where(NotificationDelivery.task_id == task_id)).all()
    new_status = calculate_task_status(deliveries)
    task.status = new_status

    if new_status == TaskStatus.PROCESSING and task.started_at is None:
        task.started_at = utcnow()

    if new_status in {TaskStatus.COMPLETED, TaskStatus.PARTIAL, TaskStatus.FAILED}:
        task.completed_at = task.completed_at or utcnow()
