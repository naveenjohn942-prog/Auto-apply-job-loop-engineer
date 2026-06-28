import anthropic

from app.config import settings

_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


async def draft_outreach_email(job: dict, profile: dict) -> str:
    """Return a short cold-outreach email body (plain text)."""
    prompt = (
        f"Write a short, genuine cold-outreach email from a job seeker to a recruiter. "
        f"3-4 sentences max. No fluff. Don't start with 'I hope this email finds you well' "
        f"or any similar filler. Be direct and specific.\n\n"
        f"Candidate: {profile['name']}\n"
        f"Background: {profile['years_of_experience']} years experience, "
        f"skills: {', '.join(profile['skills'][:6])}\n\n"
        f"Job: {job['title']} at {job['company']}\n"
        f"Why they match: {job.get('reasoning', '')}\n\n"
        f"Output only the email body, no subject line."
    )

    response = await _client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()
