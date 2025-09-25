"""
Celery worker configuration for document processing
"""
from celery import Celery
from settings import settings

# Create Celery app
celery_app = Celery(
    "document_processor",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["celery_tasks"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

if __name__ == "__main__":
    celery_app.start()