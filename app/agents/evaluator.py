import anthropic

from app.config import settings

_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

_SCORE_TOOL = {
    "name": "score_job",
    "description": "Score how well a job posting matches the candidate profile",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "description": "Match quality: 1=terrible fit, 10=perfect fit",
            },
            "reasoning": {
                "type": "string",
                "description": "1-2 sentence explanation of the score",
            },
            "skill_matches": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Candidate skills that match this role",
            },
            "skill_gaps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Required skills the candidate appears to lack",
            },
        },
        "required": ["score", "reasoning", "skill_matches", "skill_gaps"],
    },
}


async def evaluate_job(job: dict, profile: dict) -> dict:
    """Score a single job against the candidate profile. Starts from skepticism."""
    prompt = (
        f"You are a skeptical recruiter reviewing a job match. "
        f"Default to a LOW score unless there is strong evidence of fit. "
        f"A score of 7+ means you would recommend this application.\n\n"
        f"CONTEXT: This candidate is based in Bangalore, India. "
        f"In the Indian startup market, 1-2 years of production backend experience "
        f"is competitive for SDE-1 and junior SDE-2 roles. Do not penalise "
        f"for lacking 4-6 years unless the JD explicitly requires it.\n\n"
        f"HARD RULE — overrides everything else:\n"
        f"- If the title contains Senior, Staff, Principal, Lead, SDE-2, SDE-3, SDE II, SDE III, "
        f"Engineer II, Engineer III, or any equivalent seniority marker, score ≤ 3.\n\n"
        f"Candidate: {profile['name']}\n"
        f"Target role: {profile['target_role']}\n"
        f"Skills: {', '.join(profile['skills']) if isinstance(profile['skills'], list) else profile['skills']}\n"
        f"Years of experience: {profile.get('years_of_experience', 'unknown')}\n\n"
        f"Job Title: {job['title']}\n"
        f"Company: {job['company']}\n"
        f"Location: {job['location']}\n"
        f"Description: {job['description'][:1500]}"
    )

    response = await _client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        tools=[_SCORE_TOOL],
        tool_choice={"type": "tool", "name": "score_job"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "score_job":
            return block.input

    raise ValueError(f"Claude did not score job {job['adzuna_id']}")
