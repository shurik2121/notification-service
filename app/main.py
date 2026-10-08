from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .db import Base, engine, get_db
from .models import DeliveryStatus, NotificationDelivery, NotificationTask, NotificationType, OutboxEvent, OutboxStatus, TaskStatus
from .schemas import DeliveryResult, SMSCreate, TaskAccepted, TaskResult
from .services import refresh_task_status, utcnow

app = FastAPI(title="Notification Service", version="1.0.0")

db_connection = Annotated[Session, Depends(get_db)]

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/tasks/sms", response_model=TaskAccepted, status_code=status.HTTP_202_ACCEPTED)
def add_sms_task(
    request: SMSCreate,
    db: db_connection,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TaskAccepted:
    if idempotency_key: # prevent from duplications
        existing = db.scalar(select(NotificationTask).where(NotificationTask.idempotency_key == idempotency_key))
        if existing:
            return TaskAccepted(task_id=existing.id, status=existing.status)

    task = NotificationTask(
        type=NotificationType.SMS,
        message=request.message,
        status=TaskStatus.PENDING,
        idempotency_key=idempotency_key,
    )

    now = utcnow()
    task.deliveries = [
        NotificationDelivery(destination=phone, status=DeliveryStatus.PENDING, next_attempt_at=now)
        for phone in request.phone_numbers
    ]

    db.add(task)
    db.flush()

    for delivery in task.deliveries:
        db.add(
            OutboxEvent(
                aggregate_id=task.id,
                delivery_id=delivery.id,
                event_type="delivery.created",
                payload={"delivery_id": str(delivery.id)},
                status=OutboxStatus.PENDING,
                available_at=now,
            )
        )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = db.scalar(select(NotificationTask).where(NotificationTask.idempotency_key == idempotency_key))
            if existing:
                return TaskAccepted(task_id=existing.id, status=existing.status)
        raise HTTPException(status_code=409, detail="Task conflicts with an existing idempotency key")

    return TaskAccepted(task_id=task.id, status=task.status)


@app.get("/api/v1/tasks/{task_id}", response_model=TaskResult)
def get_task(task_id: UUID, db: db_connection) -> TaskResult:
    task = db.scalar(
        select(NotificationTask)
        .options(selectinload(NotificationTask.deliveries))
        .where(NotificationTask.id == task_id)
    )

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskResult(
        task_id=task.id,
        type=task.type,
        status=task.status,
        message=task.message,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        deliveries=[DeliveryResult.model_validate(d) for d in task.deliveries],
    )

