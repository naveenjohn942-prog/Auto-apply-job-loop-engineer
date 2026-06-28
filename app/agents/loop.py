import asyncio
import logging

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.evaluator import evaluate_job
from app.agents.generator import generate_candidates
from app.agents.verifier import verify_match
from app.db import JobPosting

log = logging.getLogger(__name__)

MAX_EVALUATED = 100
MIN_QUALITY_MATCHES = 20
QUALITY_THRESHOLD = 7  # score >= this counts as a quality match


async def run_loop(profile: dict, profile_id: int, session: AsyncSession) -> list[dict]:
    """
    Generator/evaluator loop.
    Exits when MIN_QUALITY_MATCHES found or MAX_EVALUATED candidates scored.
    Commits to DB after each page so progress survives a crash.
    """
    evaluated = 0
    quality_matches: list[dict] = []
    page = 1

    while evaluated < MAX_EVALUATED and len(quality_matches) < MIN_QUALITY_MATCHES:
        candidates = await generate_candidates(profile, page)
        log.info("loop page=%d candidates=%d evaluated=%d quality=%d", page, len(candidates), evaluated, len(quality_matches))
        if not candidates:
            log.info("loop empty page — stopping")
            break  # Adzuna returned nothing — no more pages

        # Evaluate entire page concurrently; each call is a separate Claude instance
        # ponytail: up to 20 concurrent Claude calls per page — fine for personal use
        scores = await asyncio.gather(
            *[evaluate_job(job, profile) for job in candidates],
            return_exceptions=True,
        )

        exceptions = sum(1 for s in scores if isinstance(s, Exception))
        log.info("loop page=%d scored=%d exceptions=%d", page, len(scores) - exceptions, exceptions)

        for job, result in zip(candidates, scores):
            if isinstance(result, Exception):
                log.warning("evaluator exception for %s: %s", job["adzuna_id"], result)
                continue

            evaluated += 1
            stmt = (
                pg_insert(JobPosting)
                .values(
                    adzuna_id=job["adzuna_id"],
                    title=job["title"],
                    company=job["company"],
                    location=job["location"],
                    description=job["description"],
                    url=job["url"],
                    salary_min=job["salary_min"],
                    salary_max=job["salary_max"],
                    category=job["category"],
                    score=result["score"],
                    reasoning=result["reasoning"],
                    skill_matches=result["skill_matches"],
                    skill_gaps=result["skill_gaps"],
                    candidate_profile_id=profile_id,
                )
                .on_conflict_do_nothing(constraint="uq_job_adzuna_candidate")
            )
            await session.execute(stmt)

            if result["score"] >= QUALITY_THRESHOLD:
                verdict = await verify_match(job, profile, result["reasoning"])
                if verdict["refuted"]:
                    log.info("verifier refuted %s: %s", job["title"], verdict["reason"])
                else:
                    log.info("verifier confirmed %s: %s", job["title"], verdict["reason"])
                    quality_matches.append({**job, **result})

            if evaluated >= MAX_EVALUATED or len(quality_matches) >= MIN_QUALITY_MATCHES:
                break

        # Persist progress after each page — crash-safe
        await session.commit()
        page += 1

    return quality_matches
