from typing import Optional

from google import genai
from google.genai import types
from app.config import settings
from app.models.database import get_supabase

_client = genai.Client(api_key=settings.google_api_key)


def _build_context_prompt(system_prompt: str, context_chunks: list[tuple[str, str]]) -> str:
    context_lines = []
    for filename, chunk in context_chunks:
        source = filename or "unknown document"
        context_lines.append(f"[{source}] {chunk}")
    context_str = "\n".join(context_lines)
    return (
        f"{system_prompt}\n\n"
        "Relevant document context:\n"
        f"{context_str}\n\n"
        "Use the above context to answer the user's question accurately. "
        "Cite your sources naturally in spoken prose. "
        "Do NOT use markdown footnotes like [1] or formatted brackets."
    )


async def get_persona_system_prompt(persona_id: str) -> str:
    supabase = get_supabase()
    try:
        res = supabase.table("personas").select("system_prompt").eq("id", persona_id).limit(1).execute()
        if res.data:
            return res.data[0]["system_prompt"]
    except Exception:
        pass
    return "You are a helpful voice assistant."


async def generate_response(messages: list[dict[str, str]], system_prompt: str, context: Optional[list[tuple[str, str]]] = None) -> str:
    final_system_prompt = system_prompt
    if context:
        final_system_prompt = _build_context_prompt(system_prompt, context)

    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    response = _client.models.generate_content(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=final_system_prompt),
    )
    return response.text or ""


async def generate_response_stream(messages: list[dict[str, str]], system_prompt: str, context: Optional[list[tuple[str, str]]] = None):
    final_system_prompt = system_prompt
    if context:
        final_system_prompt = _build_context_prompt(system_prompt, context)

    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    for chunk in _client.models.generate_content_stream(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=final_system_prompt),
    ):
        if chunk.text:
            yield chunk.text
