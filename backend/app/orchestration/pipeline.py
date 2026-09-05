import asyncio
import logging
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from app.services.conversation_mgr import ConversationManager
from app.services.vad import VADBuffer

logger = logging.getLogger(__name__)


def safe_put_nowait(queue: asyncio.Queue, item) -> bool:
    try:
        queue.put_nowait(item)
        return True
    except asyncio.QueueFull:
        logger.warning(
            "queue_full_dropped queue=%s item_type=%s",
            id(queue),
            type(item).__name__,
        )
        return False


def make_event(state: "SessionPipelineState", event_type: str, **fields) -> dict:
    state.event_seq += 1
    return {
        "type": event_type,
        "session_id": state.session_id,
        "sequence_number": state.event_seq,
        "timestamp": time.time(),
        **fields,
    }


@dataclass
class TextInMessage:
    session_id: str
    text: str
    stt_latency_ms: int | None
    recording_start_ms: int | None = None
    recording_end_ms: int | None = None


@dataclass
class SentenceMessage:
    text: str
    turn_id: str
    index: int
    first_sentence: bool = False


@dataclass
class TurnComplete:
    turn_id: str
    llm_latency_ms: int
    full_response: str
    total_turn_latency_ms: int
    stt_latency_ms: int | None
    ai_recording_start_ms: int | None
    db_session_id: str


@dataclass
class SessionPipelineState:
    session_id: str
    db_session_id: str
    persona_id: str
    voice_id: str
    websocket: Any

    audio_in_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    text_in_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    sentence_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    audio_out_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    control_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    ws_event_queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    ws_in_task: asyncio.Task | None = None
    vad_stt_task: asyncio.Task | None = None
    rag_llm_task: asyncio.Task | None = None
    tts_task: asyncio.Task | None = None
    ws_out_task: asyncio.Task | None = None
    supervisor_task: asyncio.Task | None = None

    active_llm_subtask: asyncio.Task | None = None
    active_tts_subtask: asyncio.Task | None = None

    conversation_mgr: ConversationManager | None = None
    vad: VADBuffer | None = None
    current_turn_id: str | None = None
    is_speaking: bool = False
    speech_detected: asyncio.Event = field(default_factory=asyncio.Event)
    cancelled_turns: set = field(default_factory=set)

    call_started: bool = False
    event_seq: int = 0

    call_start_time: float | None = None
    turn_started_at: float | None = None

    user_pcm_buffer: bytearray = field(default_factory=bytearray)


class FiveQueuePipeline:
    def __init__(self, audio_executor, embedding_executor):
        self.audio_executor = audio_executor
        self.embedding_executor = embedding_executor

    def start_pipeline(self, state: SessionPipelineState) -> None:
        from app.orchestration.stages import (
            ws_in_task,
            vad_stt_task,
            rag_llm_task,
            tts_task,
            ws_out_task,
            supervisor_task,
        )
        state.ws_in_task = asyncio.create_task(ws_in_task(state))
        state.vad_stt_task = asyncio.create_task(vad_stt_task(state, self.audio_executor))
        state.rag_llm_task = asyncio.create_task(rag_llm_task(state, self.embedding_executor))
        state.tts_task = asyncio.create_task(tts_task(state, self.audio_executor))
        state.ws_out_task = asyncio.create_task(ws_out_task(state))
        state.supervisor_task = asyncio.create_task(supervisor_task(state))

    async def stop_pipeline(self, state: SessionPipelineState) -> None:
        tasks = [
            state.ws_in_task,
            state.vad_stt_task,
            state.rag_llm_task,
            state.tts_task,
            state.ws_out_task,
            state.supervisor_task,
        ]
        for task in tasks:
            if task is not None and not task.done():
                task.cancel()
        for task in tasks:
            if task is not None:
                with suppress(asyncio.CancelledError):
                    await task

        for queue in [
            state.audio_in_queue,
            state.text_in_queue,
            state.sentence_queue,
            state.audio_out_queue,
            state.control_queue,
            state.ws_event_queue,
        ]:
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

    async def handle_barge_in(self, state: SessionPipelineState) -> None:
        if not state.is_speaking:
            return
        state.current_turn_id = None
        for subtask_attr in ("active_llm_subtask", "active_tts_subtask"):
            subtask = getattr(state, subtask_attr)
            if subtask is not None and not subtask.done():
                subtask.cancel()
                with suppress(asyncio.CancelledError):
                    await subtask
        while not state.sentence_queue.empty():
            try:
                state.sentence_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        while not state.audio_out_queue.empty():
            try:
                state.audio_out_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        state.is_speaking = False
        safe_put_nowait(state.ws_event_queue, make_event(state, "turn_ended", reason="interrupted"))
        safe_put_nowait(state.ws_event_queue, make_event(state, "status", message="idle"))
