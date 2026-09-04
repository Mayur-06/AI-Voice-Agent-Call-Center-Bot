import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import AsyncIterable, Optional, Tuple

from app.services.conversation_mgr import ConversationManager
from app.services.sentiment_analyzer import analyze_sentiment, save_sentiment
from app.services.rag import requires_rag, retrieve_relevant_chunks
from app.services.llm import generate_response_stream, get_persona_system_prompt
from app.services.sentences import split_sentences
from app.services.session import save_turn
from app.services.tts import stream_sentences
from app.websocket.manager import manager, _append_log

logger = logging.getLogger(__name__)


async def _send_filler(session_id: str, context_type: str, latency_ms: int) -> None:
    try:
        from app.orchestration.graphs import filler_graph

        result = await filler_graph.ainvoke({"context_type": context_type, "latency_ms": latency_ms})
        filler_text = result.get("message") or "Please hold..."
        await manager.send_json(session_id, {"type": "filler", "text": filler_text})
        await _append_log(
            session_id,
            {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS filler session={session_id} text={filler_text}"},
        )
    except Exception:
        pass


async def start_turn_with_filler(
    session_id: str,
    user_text: str,
    conversation_mgr: ConversationManager,
    voice_id: str,
    persona_id: str,
    db_session_id: str,
    stt_latency_ms: int | None = None,
    filler_threshold_ms: int = 1500,
    user_message_id: str | None = None,
) -> dict:
    from contextlib import suppress

    conversation_mgr.append_user(user_text)
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS transcript session={session_id} text={user_text}"})
    if not user_message_id:
        user_message_id = await save_turn(db_session_id, "user", user_text, latency_ms=0, stt_latency_ms=stt_latency_ms)

    sentiment = "neutral"
    try:
        sentiment = await analyze_sentiment(user_text)
    except Exception:
        pass
    await manager.send_json(session_id, {"type": "sentiment", "label": sentiment})
    if sentiment == "frustrated":
        await manager.send_json(session_id, {"type": "alert", "level": "warning", "message": "Frustration detected! Escalating agent tone."})
    try:
        await save_sentiment(db_session_id, user_message_id, sentiment)
    except Exception:
        pass

    await manager.send_json(session_id, {"type": "status", "message": "retrieving_context"})
    context = []
    if requires_rag(user_text):
        try:
            context = await retrieve_relevant_chunks(user_text, session_id=db_session_id)
        except Exception:
            pass
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS RAG context session={session_id} chunks={len(context) if context else 0}"})

    system_instruction = await get_persona_system_prompt(persona_id)

    turn_start = time.perf_counter()
    llm_start = time.perf_counter()
    full_response = ""
    sentences_sent = 0
    timeout_error = False
    partial_response_container: dict[str, str] = {"text": ""}
    llm_latency_ms: int | None = None
    tts_first_audio_latency_ms: int | None = None
    turn_done = asyncio.Event()
    filler_task: asyncio.Task | None = None
    assistant_message_id: str | None = None

    async def _filler_monitor():
        await asyncio.sleep(filler_threshold_ms / 1000)
        if not turn_done.is_set():
            await _send_filler(session_id, "thinking", int((time.perf_counter() - llm_start) * 1000))

    filler_task = asyncio.create_task(_filler_monitor())

    async def sentence_stream() -> Tuple[str, int]:
        nonlocal full_response, sentences_sent
        rag_context = context if context else None
        buffer = ""
        async for chunk in generate_response_stream(conversation_mgr.get_history(), system_instruction, context=rag_context):
            full_response += chunk
            buffer += chunk
            partial_response_container["text"] = full_response
            sentences = await split_sentences(buffer)
            while len(sentences) > 1:
                sentence = sentences.pop(0)
                buffer = buffer[len(sentence):].lstrip()
                yield sentence, sentences_sent
                sentences_sent += 1
        if buffer.strip():
            yield buffer.strip(), sentences_sent
            sentences_sent += 1

    try:
        await manager.send_json(session_id, {"type": "status", "message": "thinking"})
        await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS LLM stream started session={session_id}"})
        ai_recording_start_ms = int((time.perf_counter() - turn_start) * 1000) if turn_start else 0
        sentences_sent, tts_first_audio_latency_ms = await asyncio.wait_for(
            stream_sentences(session_id, sentence_stream(), voice_id),
            timeout=90,
        )
        ai_recording_end_ms = int((time.perf_counter() - turn_start) * 1000) if turn_start else ai_recording_start_ms
    except asyncio.TimeoutError:
        timeout_error = True
        if not full_response:
            full_response = "I'm sorry, I'm taking too long to respond. Please try again."
    except asyncio.CancelledError:
        raise
    finally:
        turn_done.set()
        if filler_task and not filler_task.done():
            filler_task.cancel()
        with suppress(asyncio.CancelledError):
            if filler_task:
                await filler_task

    llm_latency_ms = int((time.perf_counter() - llm_start) * 1000)
    total_turn_latency_ms = int((time.perf_counter() - turn_start) * 1000)

    await manager.send_json(
        session_id,
        {
            "type": "latencies",
            "stt": stt_latency_ms,
            "llm": llm_latency_ms,
            "ttsFirstAudio": tts_first_audio_latency_ms,
            "total": total_turn_latency_ms,
        },
    )
    await manager.send_json(session_id, {"type": "status", "message": "response_ready"})
    await _append_log(session_id, {"ts": datetime.now(timezone.utc).isoformat(), "level": "info", "msg": f"WS response ready session={session_id} text={full_response} timeout={timeout_error}"})

    conversation_mgr.append_assistant(full_response)
    assistant_message_id = await save_turn(
        db_session_id,
        "assistant",
        full_response,
        latency_ms=total_turn_latency_ms,
        interrupted=False,
        stt_latency_ms=stt_latency_ms,
        llm_latency_ms=llm_latency_ms,
        tts_first_audio_latency_ms=tts_first_audio_latency_ms,
        recording_start_ms=ai_recording_start_ms,
        recording_end_ms=ai_recording_end_ms,
    )
    await manager.send_json(
        session_id,
        {
            "type": "transcript",
            "role": "assistant",
            "text": full_response,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {
        "user_message_id": user_message_id,
        "assistant_message_id": assistant_message_id,
        "user_text": user_text,
        "assistant_text": full_response,
        "sentiment": sentiment,
        "total_turn_latency_ms": total_turn_latency_ms,
        "timeout_error": timeout_error,
    }


async def process_turn(
    session_id: str,
    user_text: str,
    conversation_mgr: ConversationManager,
    voice_id: str,
    persona_id: str,
    db_session_id: str,
    stt_latency_ms: int | None = None,
    user_message_id: str | None = None,
) -> dict:
    return await start_turn_with_filler(
        session_id,
        user_text,
        conversation_mgr,
        voice_id,
        persona_id,
        db_session_id,
        stt_latency_ms=stt_latency_ms,
        user_message_id=user_message_id,
    )