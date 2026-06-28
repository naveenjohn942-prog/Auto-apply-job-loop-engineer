import anthropic

from app.config import settings

_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

_VERIFY_TOOL = {
    "name": "verify_match",
    "description": "Try to refute a positive job match. Default to refuted=True if uncertain.",
    "input_schema": {
        "type": "object",
        "properties": {
            "refuted": {
                "type": "boolean",
                "description": "True if you found a strong reason this application would fail or waste the candidate's time.",
            },
            "reason": {
                "type": "string",
                "description": "1-2 sentences. If refuted, state the dealbreaker. If confirmed, state why it survives scrutiny.",
            },
        },
        "required": ["refuted", "reason"],
    },
}


async def verify_match(job: dict, profile: dict, evaluator_reasoning: str) -> dict:
    """
    Adversarial agent: tries to find a dealbreaker that the evaluator missed.
    Returns {"refuted": bool, "reason": str}.
    Defaults to refuted=True if uncertain.
    """
    prompt = (
        f"An evaluator scored this job match positively. Your job is to find a reason it should be REJECTED. "
        f"Be adversarial. Default to refuted=True if you are unsure.\n\n"
        f"Reject if ANY of these are true:\n"
        f"- The role is clearly senior/lead level despite a non-senior title\n"
        f"- A hard technical skill required by the JD is completely absent from the candidate's profile\n"
        f"- The role is in a domain the candidate has zero experience in (e.g. embedded, ML research, blockchain)\n"
        f"- The JD explicitly requires 5+ years\n\n"
        f"Candidate: {profile['name']}, {profile.get('years_of_experience', '?')} yrs experience\n"
        f"Skills: {', '.join(profile['skills']) if isinstance(profile['skills'], list) else profile['skills']}\n\n"
        f"Job: {job['title']} at {job['company']}\n"
        f"Description: {job['description'][:1000]}\n\n"
        f"Evaluator said: {evaluator_reasoning}"
    )

    response = await _client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=256,
        tools=[_VERIFY_TOOL],
        tool_choice={"type": "tool", "name": "verify_match"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "verify_match":
            return block.input

    # ponytail: if Claude fails to return the tool, treat as refuted to be safe
    return {"refuted": True, "reason": "Verifier did not return a result"}
