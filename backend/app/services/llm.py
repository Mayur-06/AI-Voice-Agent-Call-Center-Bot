from typing import Optional

from google import genai
from google.genai import types
from app.config import settings
from app.models.database import get_supabase, run_supabase

# Built lazily and shared process-wide. Constructing this at import time
# required a live API key just to import the module.
_client: genai.Client | None = None


def get_genai_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.google_api_key)
    return _client


# Appended to every persona prompt. Personas describe *who* the agent is; this
# describes the medium. Without it the agent replied with markdown-formatted
# multi-paragraph answers - a measured 26 seconds of synthesised speech for two
# simple questions - and the markdown leaked into the on-screen transcript.
VOICE_STYLE = (
    "\n\nYou are speaking on a live phone call. Reply in plain spoken language: "
    "no markdown, no bullet points, no headings, no emoji, no asterisks. "
    "Keep answers to one or two short sentences and stop; ask a follow-up "
    "question instead of listing everything you could say."
)


def _build_context_prompt(system_prompt: str, context_chunks: list[tuple[str, str]]) -> str:
    context_lines = []
    for filename, chunk in context_chunks:
        source = filename or "unknown document"
        context_lines.append(f"[{source}] {chunk}")
    context_str = "\n".join(context_lines)
    return (
        f"{system_prompt}\n\n"
        "Reference material that may be relevant:\n"
        f"{context_str}\n\n"
        "If this material answers the caller's question, use it and stay "
        "faithful to the exact figures, dates and times it gives - never round "
        "or approximate them. If it does not cover what they asked, ignore it "
        "and answer normally; say you do not have that detail rather than "
        "inventing one, and never tell the caller what your documents do or do "
        "not contain. Cite sources naturally in spoken prose; do NOT use "
        "markdown footnotes like [1] or formatted brackets."
    )


# A voice call has no natural end, so an unbounded history grew the prompt on
# every turn - steadily raising both cost and time-to-first-token.
MAX_HISTORY_TURNS = 20


def _to_contents(messages: list[dict[str, str]]) -> list:
    recent = messages[-MAX_HISTORY_TURNS:]
    return [
        types.Content(
            role="user" if msg["role"] == "user" else "model",
            parts=[types.Part(text=msg["content"])],
        )
        for msg in recent
    ]


async def get_persona_system_prompt(persona_id: str) -> str:
    client = get_supabase()
    try:
        res = await run_supabase(lambda: client.table("personas").select("system_prompt").eq("id", persona_id).limit(1).execute())
        if res.data:
            return res.data[0]["system_prompt"]
    except Exception:
        pass
    return "You are a helpful voice assistant."


async def generate_response(messages: list[dict[str, str]], system_prompt: str, context: Optional[list[tuple[str, str]]] = None) -> str:
    final_system_prompt = system_prompt
    if context:
        final_system_prompt = _build_context_prompt(system_prompt, context)
    final_system_prompt += VOICE_STYLE

    contents = _to_contents(messages)

    response = await get_genai_client().aio.models.generate_content(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=final_system_prompt,
            max_output_tokens=settings.max_response_tokens,
        ),
    )
    return response.text or ""


async def generate_response_stream(messages: list[dict[str, str]], system_prompt: str, context: Optional[list[tuple[str, str]]] = None):
    final_system_prompt = system_prompt
    if context:
        final_system_prompt = _build_context_prompt(system_prompt, context)
    final_system_prompt += VOICE_STYLE

    contents = _to_contents(messages)

    stream = await get_genai_client().aio.models.generate_content_stream(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=final_system_prompt,
            max_output_tokens=settings.max_response_tokens,
        ),
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text
