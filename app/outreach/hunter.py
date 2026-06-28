import httpx

from app.config import settings

_RECRUITER_DEPARTMENTS = {"hr", "talent", "recruitment", "people", "hiring"}
_RECRUITER_KEYWORDS = {"recruiter", "talent", "hr", "hiring", "people", "acquisition"}


def _is_recruiter(email_entry: dict) -> bool:
    dept = (email_entry.get("department") or "").lower()
    position = (email_entry.get("position") or "").lower()
    return (
        dept in _RECRUITER_DEPARTMENTS
        or any(kw in position for kw in _RECRUITER_KEYWORDS)
    )


async def find_recruiter_email(company: str) -> str | None:
    """Return the best recruiter email for a company, or None if not found."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.hunter.io/v2/domain-search",
            params={"company": company, "api_key": settings.hunter_api_key, "limit": 10},
            timeout=15.0,
        )

    if resp.status_code != 200:
        return None

    emails = resp.json().get("data", {}).get("emails", [])
    if not emails:
        return None

    # Prefer HR/recruiter role, fall back to first available
    for entry in emails:
        if _is_recruiter(entry):
            return entry["value"]
    return emails[0]["value"]
