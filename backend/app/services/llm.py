import httpx
from app.config import settings


GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"


async def generate_response(messages: list[dict[str, str]], system_prompt: str) -> str:
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
    }
    params = {"key": settings.google_api_key}
    async with httpx.AsyncClient() as client:
        response = await client.post(GEMINI_API_URL, params=params, json=payload, timeout=30.0)
        response.raise_for_status()
        result = response.json()
        return result["candidates"][0]["content"]["parts"][0]["text"]
