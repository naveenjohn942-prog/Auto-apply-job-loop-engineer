import httpx

from app.config import settings

_ADZUNA_COUNTRY = "in"


async def generate_candidates(profile: dict, page: int = 1) -> list[dict]:
    """Fetch one page of job postings from Adzuna matching the candidate profile."""
    query = profile["target_role"]

    params = {
        "app_id": settings.adzuna_app_id,
        "app_key": settings.adzuna_app_key,
        "results_per_page": 20,
        "what": query,
        "where": "Bangalore",
        "content-type": "application/json",
    }

    base = f"https://api.adzuna.com/v1/api/jobs/{_ADZUNA_COUNTRY}/search"
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
