import asyncio
import logging

import httpx

log = logging.getLogger(__name__)

from app.config import settings

_REMOTE_COUNTRY = "gb"  # largest Adzuna dataset for remote roles


async def _fetch_page(query: str, location: str | None, country_code: str, page: int) -> list[dict]:
    params = {
        "app_id": settings.adzuna_app_id,
        "app_key": settings.adzuna_app_key,
        "results_per_page": 20,
        "what": query,
        "content-type": "application/json",
    }
    if location:
        params["where"] = location

    base = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search"
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base}/{page}", params=params, timeout=30.0)

    if resp.status_code == 429:
        log.warning("Adzuna rate limit hit for %s page %d — skipping", country_code, page)
        return []

    resp.raise_for_status()

    return [
        {
            "adzuna_id": str(job["id"]),
            "title": job["title"],
            "company": job.get("company", {}).get("display_name", "Unknown"),
            "location": job["location"]["display_name"],
            "description": job["description"],
            "url": job["redirect_url"],
            "salary_min": job.get("salary_min"),
            "salary_max": job.get("salary_max"),
            "category": job.get("category", {}).get("label"),
        }
        for job in resp.json().get("results", [])
    ]


async def generate_candidates(profile: dict, page: int = 1) -> list[dict]:
    locations: list[str] = profile.get("locations") or []
    country_code: str | None = profile.get("country_code")
    remote: bool = profile.get("remote", False)
    query = profile["target_role"]

    calls = []

    # Onsite calls
    if locations and country_code:
        calls.extend(_fetch_page(query, loc, country_code, page) for loc in locations)
    elif country_code:
        calls.append(_fetch_page(query, None, country_code, page))

    # Global remote call
    if remote:
        calls.append(_fetch_page(query + " remote", None, _REMOTE_COUNTRY, page))

    if not calls:
        return []

    results = await asyncio.gather(*calls)

    seen: set[str] = set()
    deduped: list[dict] = []
    for jobs in results:
        for job in jobs:
            if job["adzuna_id"] not in seen:
                seen.add(job["adzuna_id"])
                deduped.append(job)
    return deduped
