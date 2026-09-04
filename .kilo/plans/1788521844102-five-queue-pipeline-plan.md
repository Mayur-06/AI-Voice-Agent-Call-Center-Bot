# Five-Queue Decoupled WebSocket Voice Pipeline — Implementation Plan

## 1. Goal

Refactor `backend/app/websocket/handler.py` from a 692-line monolith into a strict
**five-queue decoupled pipeline** that eliminates event-loop starvation, isolates
executors by workload type, and makes barge-in instant.

## 2. Current Architecture Gaps

| Gap | Evidence |
|---|---|
| No explicit executors | All `asyncio.to_thread()` / `loop.run_in_executor(None, ...)` share the default pool |
| Audio + control share one `message_queue` | Both binary audio and JSON text land on the same `asyncio.Queue` |
| VAD/STT runs inline in spawned tasks | `_handle_audio_message` does decode+VAD+STT+DB in one `asyncio.create_task` |
| TTS sends directly to WS | `stream_sentences` calls `manager.send_bytes` — bypasses any outbound queue |
| LLM+TTS runs in one task | `start_turn_with_filler` owns the entire turn in a single Task |
| Barge-in only cancels turn task | No queue draining; Sentence/Audio Out queues not cleared |
| Heartbeat shares event loop with pipeline | `_heartbeat` is a separate task but competes for loop time |
| `_partial_stt_loop` polls every 0.5s | Wastes loop iterations on a timer-based approach |

## 3. Target Architecture

```
[WS In Task] ──pushes audio──▶ Audio In Queue ──▶ [VAD/STT Task] ──pushes text──▶ Text In Queue
     │                              ▲                                                    │
     │  answers pong                 │              [RAG+LLM Task] ◀───────────────────┘
     │                              │                     │
     │                              │                     ▼
     │                              │              Sentence Queue
     │                              │                     │
     │                              │                     ▼
     │                              │               [TTS Task]
     │                              │                     │
     │                              │                     ▼
     │                              │              Audio Out Queue
     │                              │                     │
     │                              └─────────────────────┘
     │                                                    │
     ▼                                                    ▼
[WS Out Task] ◀─────── event queue (status / turn_ended / sentiment / error)
```

### 3.1 Stage Contracts

| Stage | Input | Output | Executor |
|---|---|---|---|
| WS In Task | `websocket.receive()` | Audio In Queue + pong | — (pure async I/O) |
| VAD/STT Task | Audio In Queue | Text In Queue OR WS Out event | `AudioExecutor` (TPE) |
| RAG+LLM Task | Text In Queue | Sentence Queue | `EmbeddingExecutor` (PPE) for embeddings; Gemini is async HTTP |
| TTS Task | Sentence Queue | Audio Out Queue + `await asyncio.sleep(0)` per chunk | `AudioExecutor` (TPE) for strip_markdown |
| WS Out Task | Audio Out Queue + event queue | `websocket.send_bytes()` / `send_json()` | — (pure async I/O) |
| Supervisor | All queues | Cancel + drain + barge-in events | — |

## 4. New Files to Create

### 4.1 `backend/app/orchestration/pipeline.py`

**`SessionPipelineState`** — holds all per-session runtime state:

```python
@dataclass
class SessionPipelineState:
    session_id: str
    db_session_id: str
    persona_id: str
    voice_id: str
    websocket: WebSocket

    # Queues (bounded to prevent memory leaks)
    audio_in_queue: asyncio.Queue[bytes | None]
    text_in_queue: asyncio.Queue[TextInMessage | None]
    sentence_queue: asyncio.Queue[SentenceMessage | None]
    audio_out_queue: asyncio.Queue[bytes | None]
    event_queue: asyncio.Queue[dict | None]

    # Tasks
    ws_in_task: asyncio.Task | None = None
    vad_stt_task: asyncio.Task | None = None
    rag_llm_task: asyncio.Task | None = None
    tts_task: asyncio.Task | None = None
    ws_out_task: asyncio.Task | None = None
    supervisor_task: asyncio.Task | None = None

    # Shared state
    conversation_mgr: ConversationManager
    vad: VADBuffer
    current_turn_id: str | None = None
    is_speaking: bool = False        # True while TTS is streaming AI audio
    speech_detected: asyncio.Event   # Set by VAD/STT when speech_ended fires
    cancelled_turns: set[str]        # Track cancelled turn IDs for idempotency
    barge_in_event: asyncio.Event    # Set when barge-in is needed
```

**`FiveQueuePipeline`** — factory + lifecycle manager:

- `create_session_pipeline(state) -> SessionPipelineState`
- `start_pipeline(state) -> None` — launches all 5 tasks + supervisor
- `stop_pipeline(state) -> None` — cancels all tasks, drains queues, awaits cleanup
- `handle_barge_in(state) -> None` — cancels in-flight LLM/TTS, drains queues, emits events

### 4.2 `backend/app/orchestration/stages.py`

All five stage task factories plus the supervisor:

#### WS In Task
```python
async def ws_in_task(state: SessionPipelineState) -> None:
    while True:
        msg = await state.websocket.receive()
        if msg["type"] == "websocket.disconnect":
            state.event_queue.put_nowait({"type": "disconnect"})
            break
        if msg["type"] == "websocket.ping":
            await state.websocket.send_pong(msg.get("data", b""))
            continue  # Never queued — answered immediately
        if "bytes" in msg:
            state.audio_in_queue.put_nowait(msg["bytes"])
        elif "text" in msg:
            data = json.loads(msg["text"])
            if data.get("type") == "ping":
                await state.websocket.send_text(json.dumps({"type": "pong"}))
                continue
            if data.get("type") == "stop_call":
                state.event_queue.put_nowait({"type": "stop_call"})
                break
            if data.get("type") == "stop_playback":
                state.event_queue.put_nowait({"type": "cancel_turn"})
            elif data.get("type") == "stop_listening":
                state.event_queue.put_nowait({"type": "force_stt", "data": data})
            elif data.get("type") == "transcript":
                state.event_queue.put_nowait({"type": "external_transcript", "data": data})
            elif data.get("type") == "auth":
                state.event_queue.put_nowait({"type": "auth", "data": data})
            elif data.get("type") == "voice_select":
                state.event_queue.put_nowait({"type": "voice_select", "data": data})
```

#### VAD/STT Task
```python
async def vad_stt_task(state: SessionPipelineState, audio_executor) -> None:
    while True:
        chunk = await state.audio_in_queue.get()
        if chunk is None:
            break
        # 1. Decode in AudioExecutor
        try:
            pcm = await asyncio.get_running_loop().run_in_executor(
                audio_executor, decode_to_pcm, chunk, settings.audio_sample_rate
            )
        except Exception:
            continue

        # 2. VAD in AudioExecutor (PyTorch inference)
        vad_frame_ms = 32
        frame_size = int(settings.audio_sample_rate * 2 * (vad_frame_ms / 1000))
        frame_audio, speech_ended = await asyncio.get_running_loop().run_in_executor(
            audio_executor, state.vad.process_bytes, pcm, frame_size
        )

        if speech_ended and frame_audio:
            state.speech_detected.set()

        if not speech_ended:
            continue

        # 3. Convert to WAV in AudioExecutor
        wav_audio = await asyncio.get_running_loop().run_in_executor(
            audio_executor, pcm_to_wav, frame_audio, settings.audio_sample_rate
        )

        # 4. STT (async HTTP — Groq Whisper, runs on event loop)
        stt_start = time.perf_counter()
        try:
            user_text = await asyncio.wait_for(transcribe_audio(wav_audio), timeout=15)
        except asyncio.TimeoutError:
            state.event_queue.put_nowait({"type": "error", "message": "stt_timeout"})
            continue

        stt_latency_ms = int((time.perf_counter() - stt_start) * 1000)

        if not user_text or is_noisy_transcription(user_text):
            state.event_queue.put_nowait({
                "type": "status", "message": "empty_transcript",
                "stt_latency_ms": stt_latency_ms
            })
            continue

        state.event_queue.put_nowait({
            "type": "transcript", "role": "user", "text": user_text
        })

        state.text_in_queue.put_nowait(TextInMessage(
            session_id=state.session_id,
            text=user_text,
            stt_latency_ms=stt_latency_ms,
        ))
```

#### RAG+LLM Task
```python
async def rag_llm_task(state: SessionPipelineState, embedding_executor) -> None:
    while True:
        msg = await state.text_in_queue.get()
        if msg is None:
            break

        turn_id = str(uuid.uuid4())
        state.current_turn_id = turn_id

        # 1. Append user turn to conversation history
        state.conversation_mgr.append_user(msg.text)

        # 2. Sentiment (async LangGraph — event loop)
        try:
            sentiment = await analyze_sentiment(msg.text)
            state.event_queue.put_nowait({"type": "sentiment", "label": sentiment})
        except Exception:
            sentiment = "neutral"

        # 3. RAG retrieval — embeddings in ProcessPoolExecutor, Pinecone query in default pool
        context = []
        if requires_rag(msg.text):
            try:
                context = await retrieve_relevant_chunks(
                    msg.text,
                    session_id=state.db_session_id,
                    # The rag.py module already uses run_in_executor internally;
                    # sentence-transformers model.encode() runs in PPE.
                )
            except Exception:
                pass

        # 4. Get system prompt
        system_instruction = await get_persona_system_prompt(state.persona_id)

        # 5. Stream LLM tokens, split into sentences, push to Sentence Queue
        state.event_queue.put_nowait({"type": "status", "message": "thinking"})
        full_response = ""
        buffer = ""
        sentence_idx = 0
        first_audio_sent = False

        async def _filler_monitor():
            await asyncio.sleep(settings.filler_threshold_ms / 1000)
            if state.current_turn_id == turn_id:
                state.event_queue.put_nowait({"type": "filler"})

        filler = asyncio.create_task(_filler_monitor())

        try:
            async for chunk in generate_response_stream(
                state.conversation_mgr.get_history(),
                system_instruction,
                context=context if context else None,
            ):
                if state.current_turn_id != turn_id:
                    break  # Barge-in
                full_response += chunk
                buffer += chunk
                sentences = await split_sentences(buffer)
                while len(sentences) > 1:
                    sentence = sentences.pop(0)
                    buffer = buffer[len(sentence):].lstrip()
                    if not first_audio_sent:
                        first_audio_sent = True
                        state.event_queue.put_nowait({"type": "status", "message": "speaking"})
                    state.sentence_queue.put_nowait(SentenceMessage(
                        text=sentence,
                        turn_id=turn_id,
                        index=sentence_idx,
                        first_sentence=(sentence_idx == 0),
                    ))
                    sentence_idx += 1
                    await asyncio.sleep(0)  # Yield after each sentence queued
        except asyncio.CancelledError:
            pass
        finally:
            filler.cancel()
            with suppress(asyncio.CancelledError):
                await filler

        # Flush remaining buffer
        if buffer.strip() and state.current_turn_id == turn_id:
            state.sentence_queue.put_nowait(SentenceMessage(
                text=buffer.strip(), turn_id=turn_id, index=sentence_idx
            ))

        # Signal end-of-turn
        state.sentence_queue.put_nowait(None)
```

#### TTS Task
```python
async def tts_task(state: SessionPipelineState, audio_executor) -> None:
    first_chunk_time: float | None = None
    sentence_start_time: float | None = None

    while True:
        msg = await state.sentence_queue.get()
        if msg is None:
            break
        if msg.turn_id != state.current_turn_id:
            continue  # Stale sentence from cancelled turn

        state.is_speaking = True
        sentence_start_time = time.perf_counter()
        if msg.first_sentence:
            state.event_queue.put_nowait({"type": "tts_first_sentence", "turn_id": msg.turn_id})

        audio_buffer = bytearray()
        first_chunk = True
        try:
            spoken = await asyncio.get_running_loop().run_in_executor(
                audio_executor, strip_markdown, msg.text
            )
            async for chunk in synthesize_speech_stream(spoken, state.voice_id):
                if msg.turn_id != state.current_turn_id:
                    break
                if first_chunk:
                    first_chunk_time = time.perf_counter()
                    first_chunk = False
                    state.event_queue.put_nowait({
                        "type": "tts_first_audio",
                        "turn_id": msg.turn_id,
                        "latency_ms": int((first_chunk_time - sentence_start_time) * 1000),
                    })
                audio_buffer.extend(chunk)
                state.audio_out_queue.put_nowait(bytes(chunk))
                await asyncio.sleep(0)  # CRITICAL: yield per chunk
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            state.event_queue.put_nowait({"type": "error", "message": f"tts_failed:{exc}"})
        state.is_speaking = False
```

#### WS Out Task
```python
async def ws_out_task(state: SessionPipelineState) -> None:
    while True:
        # Prioritize events over audio, but don't starve audio
        event = None
        try:
            event = state.event_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

        if event is None:
            try:
                audio_chunk = await asyncio.wait_for(
                    state.audio_out_queue.get(), timeout=0.05
                )
            except asyncio.TimeoutError:
                continue
            if audio_chunk is None:
                break
            try:
                await state.websocket.send_bytes(audio_chunk)
            except Exception:
                state.event_queue.put_nowait({"type": "disconnect"})
                break
            continue

        if event.get("type") == "disconnect":
            break
        if event.get("type") == "stop_call":
            try:
                await state.websocket.close()
            except Exception:
                pass
            break
        # ... handle other events (status, sentiment, transcript, etc.)
        try:
            await state.websocket.send_json(event)
        except Exception:
            break
```

#### Supervisor Task
```python
async def supervisor_task(state: SessionPipelineState) -> None:
    while True:
        await state.speech_detected.wait()
        state.speech_detected.clear()

        if state.is_speaking:
            # Barge-in: cancel current turn, drain queues
            state.current_turn_id = None  # Makes all stage tasks skip their work
            # Drain Sentence Queue
            while not state.sentence_queue.empty():
                try:
                    state.sentence_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            # Drain Audio Out Queue
            while not state.audio_out_queue.empty():
                try:
                    state.audio_out_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            state.event_queue.put_nowait({"type": "turn_ended", "reason": "interrupted"})
            state.event_queue.put_nowait({"type": "status", "message": "idle"})
```

## 5. Modified Files

### 5.1 `backend/app/config.py` — Add executor pool sizes and queue bounds

Add these fields to `Settings`:

```python
ws_audio_executor_workers: int = 4          # VAD, PyAV, TTS strip_markdown
ws_embedding_executor_workers: int = 2      # SentenceTransformer (PPE)
ws_queue_max_size: int = 256                # Bounded queues per session
```

### 5.2 `backend/app/main.py` — Create executors at startup, store on `app.state`

In `lifespan()`, after existing startup code:

```python
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

@app.on_event("startup")
async def _create_executors():
    app.state.audio_executor = ThreadPoolExecutor(
        max_workers=settings.ws_audio_executor_workers,
        thread_name_prefix="audio",
    )
    app.state.embedding_executor = ProcessPoolExecutor(
        max_workers=settings.ws_embedding_executor_workers,
    )

@app.on_event("shutdown")
async def _shutdown_executors():
    app.state.audio_executor.shutdown(wait=True)
    app.state.embedding_executor.shutdown(wait=True)
```

### 5.3 `backend/app/websocket/handler.py` — Thin to ~80 lines

Replace the 692-line handler with:

```python
@router.websocket("/ws/voice/{session_id}")
async def websocket_voice(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)
    await _log_stage(session_id, "CONNECTION_ESTABLISHED")

    try:
        persona_id = await _get_default_persona_id()
        anonymous_user_id = str(uuid.uuid4())
        db_session_id = await create_session(persona_id=persona_id, user_id=anonymous_user_id, session_id=session_id)
        existing_session = await _load_session(db_session_id)
        voice_id = existing_session.get("selected_voice") if existing_session else None
        if not voice_id:
            try:
                voice_id = await get_persona_voice_id(persona_id)
            except Exception:
                voice_id = "en-IN-NeerjaNeural"
    except Exception as exc:
        await manager.send_json(session_id, {"type": "error", "message": f"session_init_failed:{type(exc).__name__}"})
        manager.disconnect(session_id)
        return

    conversation_mgr = ConversationManager()
    if existing_session:
        try:
            await conversation_mgr.load_from_db(db_session_id)
        except Exception:
            pass

    vad = VADBuffer(sample_rate=settings.audio_sample_rate)

    state = SessionPipelineState(
        session_id=session_id,
        db_session_id=db_session_id,
        persona_id=persona_id,
        voice_id=voice_id,
        websocket=websocket,
        audio_in_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        text_in_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        sentence_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        audio_out_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        event_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        conversation_mgr=conversation_mgr,
        vad=vad,
        speech_detected=asyncio.Event(),
        barge_in_event=asyncio.Event(),
        cancelled_turns=set(),
    )

    pipeline = FiveQueuePipeline(
        audio_executor=websocket.app.state.audio_executor,
        embedding_executor=websocket.app.state.embedding_executor,
    )
    pipeline.start(state)

    try:
        while True:
            event = await state.event_queue.get()
            if event is None:
                break
            if event.get("type") == "disconnect":
                break
            if event.get("type") == "stop_call":
                break
            if event.get("type") == "auth":
                data = event["data"]
                state.persona_id = await resolve_persona_id(data.get("persona_id", state.persona_id))
                state.voice_id = data.get("voice_id") or state.voice_id
                await manager.send_json(session_id, {"type": "status", "message": "authenticated"})
            elif event.get("type") == "voice_select":
                state.voice_id = event["data"].get("voice_id") or state.voice_id
                await manager.send_json(session_id, {"type": "status", "message": f"voice_selected:{state.voice_id}"})
            elif event.get("type") == "cancel_turn":
                pipeline.handle_barge_in(state)
            elif event.get("type") == "force_stt":
                # Flush VAD and force STT
                ...
            elif event.get("type") == "external_transcript":
                data = event["data"]
                state.text_in_queue.put_nowait(TextInMessage(
                    session_id=state.session_id,
                    text=data.get("text", ""),
                    stt_latency_ms=None,
                ))
            elif event.get("type") == "transcript":
                await manager.send_json(session_id, event)
            elif event.get("type") == "status":
                await manager.send_json(session_id, event)
            elif event.get("type") == "sentiment":
                await manager.send_json(session_id, event)
            elif event.get("type") == "error":
                await manager.send_json(session_id, event)
            elif event.get("type") == "tts_first_audio":
                # Track latency metric
                ...
            elif event.get("type") == "turn_ended":
                await manager.send_json(session_id, event)
    finally:
        pipeline.stop(state)
        # Save recording, summary, end_session (existing logic)
        ...
```

### 5.4 `backend/app/services/tts.py` — Push to Audio Out Queue, not WS

`stream_sentences` becomes a pure sentence-to-audio-bytes transformer:

```python
async def stream_sentences(
    session_id: str,
    sentences: AsyncIterable[Tuple[str, int]],
    voice_id: str,
    audio_out_queue: asyncio.Queue,
    turn_id: str,
    current_turn_ref: dict[str, str | None],
) -> Tuple[int, int | None]:
    # Same sentence loop, but instead of manager.send_bytes:
    #   audio_out_queue.put_nowait(bytes(chunk))
    # Instead of manager.send_json:
    #   event_queue.put_nowait({...})
    # Check current_turn_ref["turn_id"] for barge-in
```

### 5.5 `backend/app/services/voice_pipeline.py` — Split into sentence producer

`start_turn_with_filler` becomes a coroutine that:
1. Does sentiment + RAG + system prompt prep (same as now)
2. Creates a `sentence_queue = asyncio.Queue()` and starts TTS as a background task
3. Streams LLM tokens, splits sentences, puts them in `sentence_queue`
4. The TTS task consumes from `sentence_queue` and pushes to `audio_out_queue`
5. Waits for TTS to finish or turn cancellation

The old `stream_sentences` call inside `start_turn_with_filler` is replaced with the new queue-based TTS task.

## 6. Executor Isolation Strategy

| Executor | Type | Max Workers | Used For |
|---|---|---|---|
| `audio_executor` | `ThreadPoolExecutor` | 4 (configurable) | `decode_to_pcm`, `pcm_to_wav`, `VADBuffer.process_bytes`, `strip_markdown`, `compose_call_recording` |
| `embedding_executor` | `ProcessPoolExecutor` | 2 (configurable) | `SentenceTransformer.encode()` (in `rag.py`) |
| default pool | `ThreadPoolExecutor` | `min(32, os.cpu_count() + 4)` | Supabase REST calls (`run_supabase`), Pinecone queries, file I/O, storage uploads |

**Rule:** No blocking call from the Audio or Embedding workloads may land on the default pool.

## 7. Barge-In / Interruption Protocol

1. VAD/STT sets `state.speech_detected` event when `speech_ended=True`
2. Supervisor task wakes on `speech_detected`
3. If `state.is_speaking`:
   - Sets `state.current_turn_id = None` (a new UUID, invalidating the old turn)
   - Cancels the in-flight `rag_llm_task` and `tts_task` via `task.cancel()`
   - Drains `sentence_queue` and `audio_out_queue` (non-blocking `get_nowait` loop)
   - Emits `{"type": "turn_ended", "reason": "interrupted"}` to event queue
   - Emits `{"type": "status", "message": "idle"}` to event queue
4. VAD/STT continues normally; the new utterance's transcript goes to `text_in_queue`
5. RAG+LLM task picks it up and starts a new `current_turn_id`

## 8. Heartbeat Isolation

- **Application-level ping/pong** (JSON `{"type":"ping"}` / `{"type":"pong"}`): handled exclusively by WS In Task — never queued, never delayed.
- **ASGI/Uvicorn keepalive**: left to Uvicorn's default `ws_ping_interval` / `ws_ping_timeout`.
- **No `asyncio.sleep()` in WS In/Out tasks** — they only block on `websocket.receive()` / `websocket.send_*()` / `queue.get()` with short timeouts.

## 9. Zero-Sleep Injection Rules

Every tight loop that iterates over async generators or queues MUST yield:

```python
# LLM token stream → sentence queue
async for chunk in generate_response_stream(...):
    ...
    state.sentence_queue.put_nowait(sentence)
    await asyncio.sleep(0)   # ← required

# TTS audio chunks → Audio Out Queue
async for chunk in synthesize_speech_stream(...):
    state.audio_out_queue.put_nowait(bytes(chunk))
    await asyncio.sleep(0)   # ← required

# WS Out task event loop
while True:
    event = state.event_queue.get_nowait() or await audio_out_queue.get()
    await websocket.send_*(...)
    # No sleep needed — send_* is true async I/O
```

## 10. Cleanup — Files/Functions to Delete After Refactor

| File / Symbol | Reason |
|---|---|
| `handler.py`: `_process_audio_chunk` | Logic moves to `vad_stt_task` |
| `handler.py`: `_partial_stt_loop` + `partial_stt_task` | Superseded by VAD/STT task |
| `handler.py`: `_handle_audio_message` | Logic moves to `vad_stt_task` |
| `handler.py`: `_handle_control_message` | Logic moves to `ws_in_task` + event loop |
| `handler.py`: `_response_worker` + `response_queue` | Replaced by `text_in_queue` + `rag_llm_task` |
| `handler.py`: `audio_tasks: set[Task]` | Replaced by pipeline task management |
| `handler.py`: `processing_lock` | Not needed — each stage is single-task per session |
| `handler.py`: `_heartbeat` | ASGI keepalive + WS In pong handling sufficient |
| `handler.py`: `_cancel_current_turn` | Moved to `pipeline.handle_barge_in` |
| `handler.py`: `_cancel_pending_audio_tasks` | No longer needed |
| `handler.py`: `_on_turn_done` | Moved to rag_llm_task / ws_out_task lifecycle |
| `services/voice_pipeline.py`: `start_turn_with_filler` | Replaced by queue-based `rag_llm_task` + `tts_task` |
| `services/voice_pipeline.py`: `process_turn` | Thin wrapper over above, no longer needed |
| `services/voice_pipeline.py`: `_send_filler` | Inline into rag_llm_task |

**Keep:**
- `services/tts.py`: `synthesize_speech`, `synthesize_speech_stream`, `strip_markdown`, `_stream_audio_chunks`
- `services/vad.py`: Entire file (VADBuffer + Silero model)
- `services/stt.py`: `transcribe_audio`, `is_noisy_transcription`
- `services/audio_processor.py`: `decode_to_pcm`, `pcm_to_wav`, `compose_call_recording`
- `services/rag.py`: `retrieve_relevant_chunks`, `requires_rag` (just move embedding work to PPE)
- `services/llm.py`: `generate_response_stream`, `get_persona_system_prompt`
- `services/conversation_mgr.py`: Entire file
- `services/session.py`: `save_turn`, `end_session`, `create_session`

## 11. Validation Steps

1. **Unit test each stage task** with mocked queues and a fake WebSocket
2. **Integration test**: simulate 5 concurrent WebSocket sessions, each streaming 10s of audio
   - Verify no event-loop starvation (measure loop lag with `loop.slow_callback_duration`)
   - Verify pong latency < 50ms under full load
3. **Barge-in test**: start a long LLM response, inject VAD speech, verify:
   - Old turn cancelled within 50ms
   - Sentence Queue drained
   - Audio Out Queue drained
   - New turn starts cleanly
4. **Executor isolation test**: run a slow DB query (5s) on the default pool while streaming audio
   - Verify VAD/STT latency unchanged
   - Verify TTS audio chunks keep flowing
5. **ProcessPool test**: index a document while a voice call is active
   - Verify no GIL contention on event loop
6. **Queue backpressure test**: set `ws_queue_max_size=4`, flood audio chunks
   - Verify `queue.put_nowait` raises `Full` and chunk is dropped with a log entry
   - Verify no OOM

## 12. Rollout Strategy

1. **Phase 1**: Add executors to `config.py` + `main.py`. No behavior change.
2. **Phase 2**: Create `pipeline.py` + `stages.py`. Keep old handler intact, add a feature flag to switch.
3. **Phase 3**: Enable new pipeline for 10% of sessions, monitor metrics.
4. **Phase 4**: Full rollout, delete old code paths.

## 13. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `ProcessPoolExecutor` startup overhead for SentenceTransformer | Pre-warm at app startup: `embedding_executor.submit(_get_model)` |
| Queue memory leak on slow consumers | Bounded queues + `put_nowait` with drop-on-full |
| Edge-TTS cancellation leaves dangling HTTP connections | `synthesize_speech_stream` catches `CancelledError` and closes `Communicate` |
| Silero VAD model not thread-safe across sessions | VADBuffer is per-session; model singleton uses `threading.Lock` |
| Supabase sync client called from PPE | All Supabase calls stay on default TPE, never PPE |

## 14. Open Questions

1. **VAD backend**: The task spec mentions `webrtcvad`; the codebase uses Silero VAD. Should we add webrtcvad as an option or stick with Silero? → **Recommend**: Keep Silero (already working, better accuracy). webrtcvad would be a separate effort.
2. **Partial STT**: The existing `_partial_stt_loop` does live partial transcription. The five-queue spec omits this. Should it be: (a) dropped, (b) moved into VAD/STT task as a side broadcast, or (c) kept as a separate optional stage? → **Recommend**: (b) — VAD/STT task can emit `partial_transcript` events to the event queue during speech.
3. **Filler message timing**: Currently uses `asyncio.create_task` with `asyncio.sleep`. In the new pipeline, should the filler be managed by the RAG+LLM task or the Supervisor? → **Recommend**: RAG+LLM task owns its own filler timer (simpler, fewer moving parts).
4. **Recording composition**: `compose_call_recording` runs at teardown. Should it run in the AudioExecutor? → **Yes** — move to AudioExecutor to avoid blocking the event loop during disconnect.
