import base64

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    Disposition,
    FileContent,
    FileName,
    FileType,
    Mail,
)

from app.config import settings


def send_email(
    to: str,
    subject: str,
    body: str,
    xlsx_bytes: bytes | None = None,
    xlsx_filename: str = "report.xlsx",
) -> None:
    message = Mail(
        from_email=settings.user_email,
        to_emails=to,
        subject=subject,
        plain_text_content=body,
    )

    if xlsx_bytes:
        message.attachment = Attachment(
            FileContent(base64.b64encode(xlsx_bytes).decode()),
            FileName(xlsx_filename),
            FileType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            Disposition("attachment"),
        )

    SendGridAPIClient(settings.sendgrid_api_key).send(message)
