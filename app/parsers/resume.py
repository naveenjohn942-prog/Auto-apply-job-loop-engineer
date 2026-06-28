from datetime import datetime
import re

import pdfplumber
import anthropic

from app.config import settings


def _compute_years_of_experience(experience: list[dict]) -> float:
    total_months = 0
    for entry in experience:
        duration = entry.get("duration", "")
        parts = re.split(r"\s*[-–]\s*", duration)
        if len(parts) != 2:
            continue
        start_str, end_str = parts
        try:
            start = datetime.strptime(start_str.strip(), "%B %Y")
            end = datetime.now() if end_str.strip().lower() in ("current", "present", "now") \
                else datetime.strptime(end_str.strip(), "%B %Y")
            months = (end.year - start.year) * 12 + (end.month - start.month)
            total_months += max(months, 0)
        except ValueError:
            continue
    return round(total_months / 12, 1)

_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

_EXTRACT_TOOL = {
    "name": "extract_profile",
    "description": "Extract a structured candidate profile from resume text",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "target_role": {
                "type": "string",
                "description": "The role the candidate is most suited for or explicitly targeting",
            },
            "skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Technical and domain skills, most relevant first",
            },
            "experience": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string"},
                        "title": {"type": "string"},
                        "duration": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                    "required": ["company", "title"],
                },
            },
            "education": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "institution": {"type": "string"},
                        "degree": {"type": "string"},
                        "year": {"type": "string"},
                    },
                    "required": ["institution", "degree"],
                },
            },
        },
        "required": ["name", "target_role", "skills", "experience", "education"],
    },
}


async def parse_resume(pdf_path: str) -> tuple[str, dict]:
    """Returns (raw_text, structured_profile)."""
    with pdfplumber.open(pdf_path) as pdf:
        raw_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    response = await _client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        tools=[_EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "extract_profile"},
        messages=[
            {
                "role": "user",
                "content": f"Extract the candidate profile from this resume:\n\n{raw_text}",
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_profile":
            profile = block.input
            if isinstance(profile.get("skills"), str):
                profile["skills"] = [s.strip() for s in profile["skills"].split(",") if s.strip()]
            profile["years_of_experience"] = _compute_years_of_experience(profile.get("experience", []))
            return raw_text, profile

    raise ValueError("Claude did not return a structured profile")
