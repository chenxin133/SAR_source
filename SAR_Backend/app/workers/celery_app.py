from __future__ import annotations

from celery import Celery

from app.config import get_settings


def create_celery() -> Celery:
    settings = get_settings()
    app = Celery("sar", broker=settings.redis_url, backend=settings.redis_url, include=["app.workers.tasks"])
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_track_started=True,
        task_time_limit=settings.task_time_limit_seconds,
        task_soft_time_limit=max(1, settings.task_time_limit_seconds - 10),
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = create_celery()

