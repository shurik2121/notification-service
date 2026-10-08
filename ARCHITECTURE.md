# HLD / Design Notes

## 1. Functional requirements

1. Accept notification tasks.
2. SMS task contains a message and a list of phone numbers.
3. Process asynchronously.
4. Use the assumed ThirdParty package for the actual send.
5. Expose task and per-recipient results.

## 2. Non-functional goals

- Durable task acceptance.
- Horizontal API/worker scaling.
- At-least-once processing.
- Per-recipient result visibility.
- Retry of transient provider failures.
- Idempotent client retries.
- Recovery from worker crashes.

## 3. Main components

### API service

FastAPI validates requests and opens a DB transaction. It does not call the notification provider.

### PostgreSQL

Source of truth for task state, delivery state, and the transactional outbox.

### Outbox dispatcher

Reads unpublished outbox records with `FOR UPDATE SKIP LOCKED`, sends a Celery message, then marks the outbox row as published. If it crashes after enqueue and before commit, the same event can be published again. This is expected and safe.

### Workers

Consume delivery IDs. Each delivery is claimed with a short transaction before doing the remote provider call. The remote call is never made while a DB transaction is open.

### Reaper

Requeues stale deliveries that remained in `PROCESSING` after a worker crash.

## 4. Scaling model

API can scale independently from workers.

For N recipients, the API creates N `notification_deliveries` and N outbox events. Each delivery becomes an independent queue job. This provides much better parallelism than having one worker loop through a large recipient list.

## 5. Concurrency

`SELECT ... FOR UPDATE SKIP LOCKED` ensures two workers do not simultaneously claim the same pending delivery.

`UNIQUE(idempotency_key)` makes client retries safe at the task level.

`UNIQUE(task_id, destination)` prevents duplicate recipients in one task.

## 6. Failure scenarios

### API crashes before DB commit

Nothing exists; the client retries.

### API crashes after DB commit

Outbox rows remain pending and will be published by the dispatcher.

### Dispatcher crashes after publishing

The outbox transaction rolls back and the same message may be published again. Worker state prevents duplicate sends for already completed deliveries.

### Provider returns a transient error

Delivery goes back to PENDING and a retry outbox event is scheduled.

### Provider returns a permanent error

Delivery becomes FAILED.

### Worker crashes while sending

Delivery can remain PROCESSING. The reaper detects stale processing and requeues it.

### Provider succeeds but the response is lost

The service may retry and send twice. Provider idempotency support is needed to eliminate this ambiguity.

## 7. Extension to email and Slack

The DB model is channel-neutral. A future email task can use:

`subject`, `message`, `address`

and a Slack task can use:

`message`, `channel`, `color`

The provider adapter already contains wrappers for all three ThirdParty APIs.
