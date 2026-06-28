import logging

from arq.connections import RedisSettings

from app.config import settings
from app.workers.tasks import run_pipeline

logging.basicConfig(level=logging.INFO)


class WorkerSettings:
    functions = [run_pipeline]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
