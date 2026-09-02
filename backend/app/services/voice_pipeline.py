import asyncio
import logging
import time
from typing import AsyncIterable, Optional, Tuple

from app.services.conversation_mgr import ConversationManager
from app.services.sentiment_analyzer import analyze_sentiment
from app.services.rag import retrieve_context
from app.services.llm import generate_response_stream
from app.services.sentences import split_sentences
from app.services.session import save_turn
from app.services.tts import stream_sentences
from app.websocket.manager import manager, _append_log

logger = logging.getLogger(__name__)


async def process_turn(
    session_id: str,
    user_text: str,
    conversation_mgr: ConversationManager,
    voice_id: str,
    persona_id: str,
    db_session_id: str,
    stt_latency_ms: int | None = None,
) -> tuple[Optional[str], int, bool]:
    from datetime import datetime, timezone

    conversation_mgr.append_user(user_text)
    await manager.send_json(session_id, {
        "type": "transcript",
        "role": "user",
        "text": user_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS transcript session={session_id} text={user_text}"})
    await save_turn(db_session_id, "user", user_text, latency_ms=0)

    sentiment = "neutral"
    try:
        sentiment = await analyze_sentiment(user_text)
    except Exception:
        pass
    await manager.send_json(session_id, {"type": "sentiment", "label": sentiment})
    if sentiment == "frustrated":
        await manager.send_json(session_id, {"type": "alert", "level": "warning", "message": "Frustration detected! Escalating agent tone."})

    await manager.send_json(session_id, {"type": "status", "message": "retrieving_context"})
    context = []
    try:
        context = await retrieve_context(user_text)
    except Exception:
        pass
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS RAG context session={session_id} chunks={len(context) if context else 0}"})

    system_instruction = "You are a helpful voice assistant."
    if context:
        context_str = "\n".join([f"- {chunk}" for chunk in context])
        system_instruction += (
            "\n\nUse the following reference documents to answer the user's question:\n"
            f"{context_str}\n\n"
            "INSTRUCTION: Cite your sources naturally in spoken prose (for example, 'According to the uploaded agreement...'). "
            "Do NOT use markdown footnotes like [1] or formatted brackets."
        )

    turn_start = time.perf_counter()
    llm_start = time.perf_counter()
    full_response = ""
    sentences_sent = 0
    timeout_error = False
    partial_response_container: dict[str, str] = {"text": ""}
    llm_latency_ms: int | None = None
    tts_first_audio_latency_ms: int | None = None

    async def sentence_stream() -> AsyncIterable[Tuple[str, int]]:
        nonlocal full_response, sentences_sent
        async for chunk in generate_response_stream(conversation_mgr.get_history(), system_instruction):
            full_response += chunk
            partial_response_container["text"] = full_response
            sentences = await split_sentences(full_response)
            while len(sentences) > 1:
                sentence = sentences.pop(0)
                full_response = full_response[len(sentence):].lstrip()
                yield sentence, sentences_sent
                sentences_sent += 1
        if full_response.strip():
            yield full_response.strip(), sentences_sent
            sentences_sent += 1

    try:
        await manager.send_json(session_id, {"type": "status", "message": "thinking"})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS LLM stream started session={session_id}"})
        _, tts_first_audio_latency_ms = await stream_sentences(session_id, sentence_stream(), voice_id)
    except asyncio.TimeoutError:
        timeout_error = True
        if not full_response:
            full_response = "I'm sorry, I'm taking too long to respond. Please try again."
    except asyncio.CancelledError:
        await manager.send_json(session_id, {"type": "status", "message": "interrupted"})
        partial_text = partial_response_container.get("text", "").strip()
        if partial_text:
            conversation_mgr.append_assistant(partial_text + "...")
            await save_turn(db_session_id, "assistant", partial_text + "...", interrupted=True)
        raise

    llm_latency_ms = int((time.perf_counter() - llm_start) * 1000)
    total_turn_latency_ms = int((time.perf_counter() - turn_start) * 1000)

    await manager.send_json(session_id, {"type": "status", "message": "response_ready"})
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS response ready session={session_id} text={full_response} timeout={timeout_error}"})

    conversation_mgr.append_assistant(full_response)
    await save_turn(db_session_id, "assistant", full_response, latency_ms=total_turn_latency_ms, interrupted=False,
                    stt_latency_ms=stt_latency_ms, llm_latency_ms=llm_latency_ms, tts_first_audio_latency_ms=tts_first_audio_latency_ms)
    await manager.send_json(session_id, {
        "type": "transcript",
        "role": "assistant",
        "text": full_response,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return full_response, total_turn_latency_ms, timeout_error
