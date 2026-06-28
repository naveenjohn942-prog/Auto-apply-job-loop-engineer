import asyncio

import httpx

from app.config import settings


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
    locations: list[str] = profile.get("locations", ["Bangalore"])
    country_code: str = profile.get("country_code", "in")
    remote: bool = profile.get("remote", False)
    query = profile["target_role"]

    if remote:
        return await _fetch_page(query + " remote", None, country_code, page)

    if len(locations) == 1:
        return await _fetch_page(query, locations[0], country_code, page)

    # Multiple locations: parallel calls, deduplicate by adzuna_id
    pages = await asyncio.gather(*[
        _fetch_page(query, loc, country_code, page) for loc in locations
    ])
    seen: set[str] = set()
    deduped: list[dict] = []
    for jobs in pages:
        for job in jobs:
            if job["adzuna_id"] not in seen:
                seen.add(job["adzuna_id"])
                deduped.append(job)
    return deduped
