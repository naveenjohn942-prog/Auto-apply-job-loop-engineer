from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from arq.connections import RedisSettings, create_pool

from app.config import settings

app = FastAPI(title="AutoApply")


@app.post("/start")
async def start_pipeline(
    resume: UploadFile = File(...),
    locations: str = Form("Bangalore"),
    country_code: str = Form("in"),
    remote: bool = Form(False),
    years_of_experience: float | None = Form(None),
):
    if resume.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    location_list = [loc.strip() for loc in locations.split(",") if loc.strip()]
    pdf_bytes = await resume.read()
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    job = await redis.enqueue_job(
        "run_pipeline", pdf_bytes, location_list, country_code, remote, years_of_experience
    )
    if job is None:
        raise HTTPException(status_code=500, detail="Failed to enqueue job")

    return {"job_id": job.job_id, "status": "queued"}


@app.get("/health")
async def health():
    return {"status": "ok"}
