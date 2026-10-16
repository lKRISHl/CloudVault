"""Private maintenance queues. PostgreSQL records remain the source of truth."""

from celery import Celery

from app.core.config import settings

celery_app = Celery("cloudvault", broker=settings.REDIS_URL, include=["app.jobs.tasks"])
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    task_ignore_result=True,
    task_store_errors_even_if_ignored=False,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=150,
    task_time_limit=180,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 600, "global_keyprefix": "cloudvault:"},
    worker_enable_remote_control=False,
    worker_send_task_events=False,
    worker_max_tasks_per_child=100,
    worker_max_memory_per_child=131072,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    task_routes={
        "cloudvault.maintenance.scans": {"queue": "scans"},
        "cloudvault.maintenance.email": {"queue": "email"},
        "cloudvault.maintenance.storage": {"queue": "storage"},
        "cloudvault.maintenance.previews": {"queue": "previews"},
    },
    beat_schedule={
        "scans": {
            "task": "cloudvault.maintenance.scans",
            "schedule": 5.0,
            "options": {"expires": 10, "queue": "scans"},
        },
        "previews": {
            "task": "cloudvault.maintenance.previews",
            "schedule": 5.0,
            "options": {"expires": 10, "queue": "previews"},
        },
        "email": {
            "task": "cloudvault.maintenance.email",
            "schedule": 2.0,
            "options": {"expires": 10, "queue": "email"},
        },
        "storage": {
            "task": "cloudvault.maintenance.storage",
            "schedule": float(settings.UPLOAD_CLEANUP_INTERVAL_SECONDS),
            "options": {
                "expires": settings.UPLOAD_CLEANUP_INTERVAL_SECONDS * 2,
                "queue": "storage",
            },
        },
    },
    timezone="UTC",
    enable_utc=True,
)
