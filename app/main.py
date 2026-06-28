from fastapi import FastAPI, File, HTTPException, UploadFile
from arq.connections import RedisSettings, create_pool

from app.config import settings

app = FastAPI(title="AutoApply")


@app.post("/start")
async def start_pipeline(resume: UploadFile = File(...)):
    if resume.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    pdf_bytes = await resume.read()
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    job = await redis.enqueue_job("run_pipeline", pdf_bytes)

    return {"job_id": job.job_id, "status": "queued"}


@app.get("/health")
async def health():
    return {"status": "ok"}
