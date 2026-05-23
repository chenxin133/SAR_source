from __future__ import annotations

from typing import Any, Callable, TypeVar

from app.config import get_settings

F = TypeVar("F", bound=Callable[..., Any])


class InlineCeleryApp:
    def task(self, *args: Any, **kwargs: Any) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            return func

        return decorator

    def send_task(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Celery is disabled when TASK_EXECUTION_MODE=inline")


def create_celery() -> Any:
    settings = get_settings()
    if settings.task_execution_mode.strip().lower() == "inline":
        return InlineCeleryApp()

    from celery import Celery

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
