"""Celery application configuration."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "code_analyzer",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.indexing_tasks",
        "app.tasks.llm_tasks",
    ],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=settings.celery_concurrency,
    # Result settings
    result_expires=3600,  # 1 hour
)
