import os
from dotenv import load_dotenv

load_dotenv()


class _Settings:
    anthropic_api_key: str = os.environ["ANTHROPIC_API_KEY"]
    adzuna_app_id: str = os.environ["ADZUNA_APP_ID"]
    adzuna_app_key: str = os.environ["ADZUNA_APP_KEY"]
    hunter_api_key: str = os.environ["HUNTER_API_KEY"]
    sendgrid_api_key: str = os.environ["SENDGRID_API_KEY"]
    database_url: str = os.environ["DATABASE_URL"]
    redis_url: str = os.environ["REDIS_URL"]
    user_email: str = os.environ["USER_EMAIL"]
    report_email: str = os.environ.get("REPORT_EMAIL") or os.environ["USER_EMAIL"]


settings = _Settings()
