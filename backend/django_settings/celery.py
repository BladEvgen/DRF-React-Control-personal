from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_settings.settings')

app = Celery('django_settings')

app.conf.update(
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/0',
    broker_connection_retry_on_startup=True,  # Повторное подключение при старте
    task_soft_time_limit=600,  # Ограничение времени выполнения задачи (10 минут)
    task_time_limit=660,  # Жёсткое ограничение времени выполнения задачи (11 минут)
    worker_max_memory_per_child=1024000,  # Ограничение памяти для воркера (1 GB)
)

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()
