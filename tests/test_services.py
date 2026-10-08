from types import SimpleNamespace

from app.models import DeliveryStatus, TaskStatus
from app.services import calculate_task_status


def d(status):
    return SimpleNamespace(status=status)


def test_all_sent_is_completed():
    assert calculate_task_status([d(DeliveryStatus.SENT), d(DeliveryStatus.SENT)]) == TaskStatus.COMPLETED


def test_pending_is_processing():
    assert calculate_task_status([d(DeliveryStatus.SENT), d(DeliveryStatus.PENDING)]) == TaskStatus.PROCESSING


def test_sent_and_failed_is_partial():
    assert calculate_task_status([d(DeliveryStatus.SENT), d(DeliveryStatus.FAILED)]) == TaskStatus.PARTIAL


def test_all_failed_is_failed():
    assert calculate_task_status([d(DeliveryStatus.FAILED), d(DeliveryStatus.FAILED)]) == TaskStatus.FAILED
