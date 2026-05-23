from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable, TypeVar

from app.config import get_settings

F = TypeVar("F", bound=Callable[..., Any])


class InlineCeleryApp:
    def task(self, *args: Any, **kwargs: Any) -> Callable[[F], F]:
        bind = bool(kwargs.get("bind"))

        def decorator(func: F) -> F:
            if not bind:
                return func

            class InlineBoundTask:
                name = kwargs.get("name") or getattr(func, "__name__", "inline_task")

                def __init__(self) -> None:
                    self.request = SimpleNamespace(retries=0)

                def retry(self, exc: Exception | None = None, countdown: int | None = None, max_retries: int | None = None):
                    self.request.retries += 1
                    if exc is not None:
                        raise exc
                    raise RuntimeError("Inline task retry requested without exception")

                def run(self, *run_args: Any, **run_kwargs: Any):
                    return func(self, *run_args, **run_kwargs)

                def __call__(self, *call_args: Any, **call_kwargs: Any):
                    return self.run(*call_args, **call_kwargs)

            return InlineBoundTask()  # type: ignore[return-value]

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
