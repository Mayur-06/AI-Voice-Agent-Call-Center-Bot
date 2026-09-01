from google import genai
from google.genai import types
from app.config import settings


_client = genai.Client(api_key=settings.google_api_key)


async def generate_response(messages: list[dict[str, str]], system_prompt: str) -> str:
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    response = _client.models.generate_content(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return response.text or ""


async def generate_response_stream(messages: list[dict[str, str]], system_prompt: str):
    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    for chunk in _client.models.generate_content_stream(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    ):
        if chunk.text:
            yield chunk.text
