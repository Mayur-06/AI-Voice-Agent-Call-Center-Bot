# Five-Queue Decoupled WebSocket Voice Pipeline — Implementation Plan

> **Revision note:** Fixes 5 issues found in review of the original AI-generated plan:
> (1) `event_queue` had two competing consumers (`ws_out_task` and the handler loop) — split
> into `control_queue` (handler-only) and `ws_event_queue` (`ws_out_task`-only), see §3.2.
> (2) Barge-in was cooperative-only (`current_turn_id` check) despite §7 claiming
> `task.cancel()` — RAG+LLM and TTS turns now run as tracked child tasks the supervisor can
> actually hard-cancel. (3) `is_speaking` was reset after every sentence, not per turn,
> creating a window where a mid-turn barge-in wouldn't register — now turn-scoped. (4) No
> `QueueFull` handling despite §11.6 expecting drop-on-full behavior — added `safe_put_nowait`.
> (5) `websocket.ping` / `send_pong()` aren't real Starlette APIs — removed, app-level
> heartbeat is JSON-only.
>
> **Second revision:** Checked against `AI_Voice_Agent_Backend_Frontend_Database_Plan.md`
> (the project plan) and found 4 conflicts with decisions it explicitly makes, plus 3 gaps
> in latency/sync tracking it requires. Resolved as three phases — §15, §16, §17. Real-time
> frustrated-sentiment alert (§9 of the project plan) is intentionally deferred, not covered
> by any phase.

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
     │                                                    │                            │
     │  answers app-level ping/pong                       │              [RAG+LLM Task] ◀┘
     │                                                    │                     │
     │  routes control msgs ──▶ Control Queue ──▶ [Handler loop]                ▼
     │                                                    │              Sentence Queue
     │                                                    │                     │
     │                                                    │                     ▼
     │                                                    │               [TTS Task]
     │                                                    │                     │
     │                                                    │                     ▼
     │                                                    │              Audio Out Queue
     │                                                    │                     │
     ▼                                                    ▼                     ▼
[WS Out Task] ◀────────────────────── WS Event Queue (status/transcript/sentiment/error/turn_ended)
```

**Note:** `event_queue` from the original design is split into two single-consumer queues
(see §3.2) — this was the plan's biggest bug: two tasks (`ws_out_task` and the handler loop)
were both draining the same `asyncio.Queue`, which silently splits events between them in
whichever order `.get()` happens to win.

### 3.1 Stage Contracts

| Stage | Input | Output | Executor |
|---|---|---|---|
| WS In Task | `websocket.receive()` | Audio In Queue + Control Queue + app-level pong | — (pure async I/O) |
| VAD/STT Task | Audio In Queue | Text In Queue OR WS Event Queue (`empty_transcript`, `stt_timeout`) | `AudioExecutor` (TPE) |
| RAG+LLM Task | Text In Queue | Sentence Queue | `EmbeddingExecutor` (PPE) for embeddings; Gemini is async HTTP |
| TTS Task | Sentence Queue | Audio Out Queue + `await asyncio.sleep(0)` per chunk | `AudioExecutor` (TPE) for strip_markdown |
| WS Out Task | Audio Out Queue + **WS Event Queue only** | `websocket.send_bytes()` / `send_json()` | — (pure async I/O) |
| Handler loop | **Control Queue only** | Mutates `state` (auth, voice_select), calls `pipeline.handle_barge_in()` | — |
| Supervisor | `speech_detected` event, turn task handles | Hard-cancels turn tasks + drains + barge-in events | — |

### 3.2 Queue Ownership Rule

Every queue has **exactly one** consumer task. `event_queue` is replaced by two queues:
- **`control_queue`** — client-originated control messages (`auth`, `voice_select`, `cancel_turn`,
  `force_stt`, `external_transcript`, `stop_call`, `disconnect`). Consumed only by the handler loop.
- **`ws_event_queue`** — server-originated events destined for the client (`status`, `transcript`,
  `sentiment`, `error`, `turn_ended`, `tts_first_audio`, `filler`). Consumed only by `ws_out_task`.

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

    # Queues (bounded to prevent memory leaks) — each has exactly one consumer
    audio_in_queue: asyncio.Queue[bytes | None]
    text_in_queue: asyncio.Queue[TextInMessage | None]
    sentence_queue: asyncio.Queue[SentenceMessage | None]
    audio_out_queue: asyncio.Queue[bytes | None]
    control_queue: asyncio.Queue[dict | None]      # consumed only by handler loop
    ws_event_queue: asyncio.Queue[dict | None]      # consumed only by ws_out_task

    # Tasks
    ws_in_task: asyncio.Task | None = None
    vad_stt_task: asyncio.Task | None = None
    rag_llm_task: asyncio.Task | None = None
    tts_task: asyncio.Task | None = None
    ws_out_task: asyncio.Task | None = None
    supervisor_task: asyncio.Task | None = None

    # Per-turn sub-tasks — tracked so the supervisor can hard-cancel them,
    # not just flag them via current_turn_id (see §7).
    active_llm_subtask: asyncio.Task | None = None
    active_tts_subtask: asyncio.Task | None = None

    # Shared state
    conversation_mgr: ConversationManager
    vad: VADBuffer
    current_turn_id: str | None = None
    is_speaking: bool = False        # Turn-scoped: True from first sentence queued
                                      # to end-of-turn/barge-in — NOT reset per sentence
    speech_detected: asyncio.Event   # Set by VAD/STT when speech_ended fires
    cancelled_turns: set[str]        # Track cancelled turn IDs for idempotency

    # Phase 1 (§15) — protocol alignment
    call_started: bool = False       # Set on start_call; vad_stt_task drops audio until then
    event_seq: int = 0               # Incrementing sequence_number for every ws_event_queue event

    # Phase 3 (§17) — latency & recording-sync metrics
    call_start_time: float | None = None   # perf_counter() at start_call; recording offsets are relative to this
    turn_started_at: float | None = None   # perf_counter() when current turn began (for total_turn_latency_ms)
```

**`FiveQueuePipeline`** — factory + lifecycle manager:

- `create_session_pipeline(state) -> SessionPipelineState`
- `start_pipeline(state) -> None` — launches all 5 tasks + supervisor
- `stop_pipeline(state) -> None` — cancels all tasks, drains queues, awaits cleanup
- `async handle_barge_in(state) -> None` — same hard-cancel logic as the supervisor's barge-in
  branch (§4.2); exposed here too so an explicit client-sent `cancel_turn` control message
  can trigger it directly, not just VAD-detected speech. **Async** because it awaits the
  cancelled sub-tasks before returning, so callers know the turn is fully torn down.

### 4.2 `backend/app/orchestration/stages.py`

All five stage task factories plus the supervisor:

#### WS In Task
```python
async def ws_in_task(state: SessionPipelineState) -> None:
    # NOTE: Starlette's WebSocket does not surface ASGI-level ping/pong frames to
    # application code — that's handled transparently by uvicorn (ws_ping_interval /
    # ws_ping_timeout in §5.1). Do not branch on msg["type"] == "websocket.ping" or
    # call websocket.send_pong() — neither exists in Starlette's public API. Heartbeat
    # is application-level JSON only, handled below.
    while True:
        msg = await state.websocket.receive()
        if msg["type"] == "websocket.disconnect":
            safe_put_nowait(state.control_queue, {"type": "disconnect"})
            break
        if "bytes" in msg:
            safe_put_nowait(state.audio_in_queue, msg["bytes"])
        elif "text" in msg:
            data = json.loads(msg["text"])
            if data.get("type") == "ping":
                await state.websocket.send_text(json.dumps({"type": "pong"}))
                continue  # Answered immediately, never queued
            if data.get("type") == "stop_call":
                safe_put_nowait(state.control_queue, {"type": "stop_call"})
                break
            if data.get("type") == "stop_playback":
                safe_put_nowait(state.control_queue, {"type": "cancel_turn"})
            elif data.get("type") == "stop_listening":
                safe_put_nowait(state.control_queue, {"type": "force_stt", "data": data})
            elif data.get("type") == "transcript":
                safe_put_nowait(state.control_queue, {"type": "external_transcript", "data": data})
            elif data.get("type") == "auth":
                safe_put_nowait(state.control_queue, {"type": "auth", "data": data})
            elif data.get("type") == "voice_select":
                safe_put_nowait(state.control_queue, {"type": "voice_select", "data": data})
```

`safe_put_nowait` (used by every producer in this pipeline — see §6.1) wraps `put_nowait`
so a full queue drops the item and logs instead of raising unhandled `QueueFull`:

```python
def safe_put_nowait(queue: asyncio.Queue, item) -> bool:
    try:
        queue.put_nowait(item)
        return True
    except asyncio.QueueFull:
        logger.warning("queue_full_dropped", queue=queue, item_type=type(item).__name__)
        return False
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
            safe_put_nowait(state.ws_event_queue, {"type": "error", "message": "stt_timeout"})
            continue

        stt_latency_ms = int((time.perf_counter() - stt_start) * 1000)

        if not user_text or is_noisy_transcription(user_text):
            safe_put_nowait(state.ws_event_queue, {
                "type": "status", "message": "empty_transcript",
                "stt_latency_ms": stt_latency_ms
            })
            continue

        safe_put_nowait(state.ws_event_queue, {
            "type": "transcript", "role": "user", "text": user_text
        })

        safe_put_nowait(state.text_in_queue, TextInMessage(
            session_id=state.session_id,
            text=user_text,
            stt_latency_ms=stt_latency_ms,
        ))
```

#### RAG+LLM Task
The outer loop is a perpetual consumer of `text_in_queue`. Each turn's actual work runs as a
**separate child task** (`state.active_llm_subtask`), spawned with `asyncio.create_task()` and
awaited. This is what lets the supervisor hard-cancel a stuck turn (§7) via `task.cancel()`
without also killing the outer loop — cancelling the outer task would stop it from ever
consuming the *next* turn.

```python
async def rag_llm_task(state: SessionPipelineState, embedding_executor) -> None:
    while True:
        msg = await state.text_in_queue.get()
        if msg is None:
            break

        turn_id = str(uuid.uuid4())
        state.current_turn_id = turn_id

        subtask = asyncio.create_task(_run_llm_turn(state, msg, turn_id, embedding_executor))
        state.active_llm_subtask = subtask
        with suppress(asyncio.CancelledError):
            await subtask
        state.active_llm_subtask = None


async def _run_llm_turn(state, msg, turn_id, embedding_executor) -> None:
        # 1. Append user turn to conversation history
        state.conversation_mgr.append_user(msg.text)

        # 2. Sentiment (async LangGraph — event loop)
        try:
            sentiment = await analyze_sentiment(msg.text)
            safe_put_nowait(state.ws_event_queue, {"type": "sentiment", "label": sentiment})
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

        # 5. Stream LLM tokens, split into sentences, push to Sentence Queue.
        # is_speaking is turn-scoped: set once, here, before any sentence is queued —
        # NOT re-set per sentence in the TTS task (that was the original race: TTS cleared
        # it after every sentence, so a barge-in landing in the gap between two sentences
        # of the same turn would be missed by the supervisor).
        state.is_speaking = True
        safe_put_nowait(state.ws_event_queue, {"type": "status", "message": "thinking"})
        full_response = ""
        buffer = ""
        sentence_idx = 0
        first_audio_sent = False

        async def _filler_monitor():
            await asyncio.sleep(settings.filler_threshold_ms / 1000)
            if state.current_turn_id == turn_id:
                safe_put_nowait(state.ws_event_queue, {"type": "filler"})

        filler = asyncio.create_task(_filler_monitor())

        try:
            async for chunk in generate_response_stream(
                state.conversation_mgr.get_history(),
                system_instruction,
                context=context if context else None,
            ):
                if state.current_turn_id != turn_id:
                    break  # Barge-in (cooperative fallback — see hard-cancel note below)
                full_response += chunk
                buffer += chunk
                sentences = await split_sentences(buffer)
                while len(sentences) > 1:
                    sentence = sentences.pop(0)
                    buffer = buffer[len(sentence):].lstrip()
                    if not first_audio_sent:
                        first_audio_sent = True
                        safe_put_nowait(state.ws_event_queue, {"type": "status", "message": "speaking"})
                    safe_put_nowait(state.sentence_queue, SentenceMessage(
                        text=sentence,
                        turn_id=turn_id,
                        index=sentence_idx,
                        first_sentence=(sentence_idx == 0),
                    ))
                    sentence_idx += 1
                    await asyncio.sleep(0)  # Yield after each sentence queued
        except asyncio.CancelledError:
            raise  # Propagate — let the outer create_task() see the cancellation
        finally:
            filler.cancel()
            with suppress(asyncio.CancelledError):
                await filler

        # Flush remaining buffer
        if buffer.strip() and state.current_turn_id == turn_id:
            safe_put_nowait(state.sentence_queue, SentenceMessage(
                text=buffer.strip(), turn_id=turn_id, index=sentence_idx
            ))

        # Signal end-of-turn — TTS task clears is_speaking when it drains this sentinel
        safe_put_nowait(state.sentence_queue, None)
```

#### TTS Task
```python
async def tts_task(state: SessionPipelineState, audio_executor) -> None:
    while True:
        msg = await state.sentence_queue.get()
        if msg is None:
            state.is_speaking = False  # End-of-turn sentinel — clear here, not per-sentence
            continue
        if msg.turn_id != state.current_turn_id:
            continue  # Stale sentence from cancelled turn

        sentence_start_time = time.perf_counter()
        if msg.first_sentence:
            safe_put_nowait(state.ws_event_queue, {"type": "tts_first_sentence", "turn_id": msg.turn_id})

        first_chunk = True
        try:
            spoken = await asyncio.get_running_loop().run_in_executor(
                audio_executor, strip_markdown, msg.text
            )
            async for chunk in synthesize_speech_stream(spoken, state.voice_id):
                if msg.turn_id != state.current_turn_id:
                    break
                if first_chunk:
                    first_chunk = False
                    safe_put_nowait(state.ws_event_queue, {
                        "type": "tts_first_audio",
                        "turn_id": msg.turn_id,
                        "latency_ms": int((time.perf_counter() - sentence_start_time) * 1000),
                    })
                safe_put_nowait(state.audio_out_queue, bytes(chunk))
                await asyncio.sleep(0)  # CRITICAL: yield per chunk
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            safe_put_nowait(state.ws_event_queue, {"type": "error", "message": f"tts_failed:{exc}"})
```

Each sentence's synthesis also runs as a tracked child task (`state.active_tts_subtask`),
mirroring the RAG+LLM pattern, so the supervisor can hard-cancel a sentence stuck mid-stream
on a slow Edge-TTS connection rather than waiting for the next chunk to yield.

#### WS Out Task
```python
async def ws_out_task(state: SessionPipelineState) -> None:
    while True:
        # Prioritize client-facing events over audio, but don't starve audio.
        # Consumes ws_event_queue ONLY — control_queue belongs to the handler loop (§3.2).
        event = None
        try:
            event = state.ws_event_queue.get_nowait()
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
                safe_put_nowait(state.control_queue, {"type": "disconnect"})
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
Hard-cancels the tracked turn sub-tasks — not just a cooperative `current_turn_id` flag —
so a stuck Gemini/Edge-TTS network await doesn't delay the barge-in past the target latency (§11.3).

```python
async def supervisor_task(state: SessionPipelineState) -> None:
    while True:
        await state.speech_detected.wait()
        state.speech_detected.clear()

        if state.is_speaking:
            # Barge-in: invalidate the turn id first so any task that yields between
            # this point and its cancellation still sees a mismatch and stops cleanly.
            state.current_turn_id = None

            for subtask_attr in ("active_llm_subtask", "active_tts_subtask"):
                subtask = getattr(state, subtask_attr)
                if subtask is not None and not subtask.done():
                    subtask.cancel()
                    with suppress(asyncio.CancelledError):
                        await subtask

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

            state.is_speaking = False
            safe_put_nowait(state.ws_event_queue, {"type": "turn_ended", "reason": "interrupted"})
            safe_put_nowait(state.ws_event_queue, {"type": "status", "message": "idle"})
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
        control_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        ws_event_queue=asyncio.Queue(maxsize=settings.ws_queue_max_size),
        conversation_mgr=conversation_mgr,
        vad=vad,
        speech_detected=asyncio.Event(),
        cancelled_turns=set(),
    )

    pipeline = FiveQueuePipeline(
        audio_executor=websocket.app.state.audio_executor,
        embedding_executor=websocket.app.state.embedding_executor,
    )
    pipeline.start(state)  # starts ws_in, vad_stt, rag_llm, tts, ws_out, supervisor

    # This loop owns control_queue exclusively — it never touches ws_event_queue,
    # and ws_out_task never touches control_queue. Client-facing sends (transcript,
    # status, sentiment, error, turn_ended, tts_first_audio) are pushed straight to
    # ws_event_queue by the stage tasks and sent by ws_out_task — this loop does not
    # forward them, closing the original dual-consumer bug.
    try:
        while True:
            event = await state.control_queue.get()
            if event is None:
                break
            if event.get("type") in ("disconnect", "stop_call"):
                break
            if event.get("type") == "auth":
                data = event["data"]
                state.persona_id = await resolve_persona_id(data.get("persona_id", state.persona_id))
                state.voice_id = data.get("voice_id") or state.voice_id
                safe_put_nowait(state.ws_event_queue, {"type": "status", "message": "authenticated"})
            elif event.get("type") == "voice_select":
                state.voice_id = event["data"].get("voice_id") or state.voice_id
                safe_put_nowait(state.ws_event_queue, {"type": "status", "message": f"voice_selected:{state.voice_id}"})
            elif event.get("type") == "cancel_turn":
                await pipeline.handle_barge_in(state)
            elif event.get("type") == "force_stt":
                # Flush VAD and force STT
                ...
            elif event.get("type") == "external_transcript":
                data = event["data"]
                safe_put_nowait(state.text_in_queue, TextInMessage(
                    session_id=state.session_id,
                    text=data.get("text", ""),
                    stt_latency_ms=None,
                ))
    finally:
        await pipeline.stop(state)
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
    #   safe_put_nowait(audio_out_queue, bytes(chunk))
    # Instead of manager.send_json:
    #   safe_put_nowait(ws_event_queue, {...})   # NOT control_queue — client-facing only
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
   - Sets `state.current_turn_id = None`, invalidating the old turn for any cooperative
     check that fires before hard-cancellation completes
   - Hard-cancels `state.active_llm_subtask` and `state.active_tts_subtask` via
     `task.cancel()` and awaits each — this is the actual bound on barge-in latency
     (§11.3's 50ms target), not the cooperative `current_turn_id` check alone, which only
     helps for in-between-chunk yields and can't interrupt a task blocked mid-await
   - Drains `sentence_queue` and `audio_out_queue` (non-blocking `get_nowait` loop)
   - Sets `state.is_speaking = False`
   - Emits `{"type": "turn_ended", "reason": "interrupted"}` to `ws_event_queue`
   - Emits `{"type": "status", "message": "idle"}` to `ws_event_queue`
4. VAD/STT continues normally; the new utterance's transcript goes to `text_in_queue`
5. RAG+LLM task's outer loop (still alive — only the per-turn sub-task was cancelled)
   picks it up and starts a new `current_turn_id`

## 8. Heartbeat Isolation

- **Application-level ping/pong** (JSON `{"type":"ping"}` / `{"type":"pong"}`): handled exclusively
  by WS In Task, answered inline via `websocket.send_text()` — never queued, never delayed. This
  is the *only* heartbeat mechanism the application code touches.
- **ASGI/Uvicorn keepalive**: left entirely to Uvicorn's own `ws_ping_interval` / `ws_ping_timeout`
  — do not attempt to intercept it in application code. Starlette's `WebSocket.receive()` does not
  surface ASGI-level ping/pong frames to the handler, so there is nothing to branch on here.
- **No `asyncio.sleep()` in WS In/Out tasks** — they only block on `websocket.receive()` / `websocket.send_*()` / `queue.get()` with short timeouts.

## 9. Zero-Sleep Injection Rules

Every tight loop that iterates over async generators or queues MUST yield, and every
`put_nowait` MUST go through `safe_put_nowait` (§4.2) to avoid an unhandled `QueueFull`:

```python
# LLM token stream → sentence queue
async for chunk in generate_response_stream(...):
    ...
    safe_put_nowait(state.sentence_queue, sentence)
    await asyncio.sleep(0)   # ← required

# TTS audio chunks → Audio Out Queue
async for chunk in synthesize_speech_stream(...):
    safe_put_nowait(state.audio_out_queue, bytes(chunk))
    await asyncio.sleep(0)   # ← required

# WS Out task event loop — note ws_event_queue, not the removed event_queue,
# and get_nowait() can raise QueueEmpty, so it's wrapped, not used as a boolean
while True:
    try:
        event = state.ws_event_queue.get_nowait()
    except asyncio.QueueEmpty:
        event = await state.audio_out_queue.get()
    await websocket.send_*(...)
    # No sleep needed — send_* is true async I/O
```

## 10. Cleanup — Files/Functions to Delete After Refactor

| File / Symbol | Reason |
|---|---|
| `handler.py`: `_process_audio_chunk` | Logic moves to `vad_stt_task` |
| `handler.py`: `_partial_stt_loop` + `partial_stt_task` | Superseded by VAD/STT task |
| `handler.py`: `_handle_audio_message` | Logic moves to `vad_stt_task` |
| `handler.py`: `_handle_control_message` | Logic moves to `ws_in_task` (routing) + handler's `control_queue` loop (§5.3) |
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
| Queue memory leak on slow consumers | Bounded queues + `safe_put_nowait` (§4.2) drop-on-full, applied consistently everywhere `put_nowait` is called |
| Edge-TTS cancellation leaves dangling HTTP connections | `synthesize_speech_stream` catches `CancelledError` and closes `Communicate`; this now actually gets triggered promptly because the supervisor hard-cancels `active_tts_subtask` (§7) instead of relying only on the cooperative `turn_id` check |
| Silero VAD model not thread-safe across sessions | VADBuffer is per-session; model singleton uses `threading.Lock` |
| Supabase sync client called from PPE | All Supabase calls stay on default TPE, never PPE |

## 14. Open Questions

1. ~~**VAD backend**~~ — **Closed in §16 (Phase 2): Silero VAD, confirmed.** The project plan's
   webrtcvad reference is the stale document here and should be updated separately.
2. **Partial STT**: The existing `_partial_stt_loop` does live partial transcription. The five-queue spec omits this. Should it be: (a) dropped, (b) moved into VAD/STT task as a side broadcast, or (c) kept as a separate optional stage? → **Recommend**: (b) — VAD/STT task can emit `partial_transcript` events to the event queue during speech.
3. **Filler message timing**: Currently uses `asyncio.create_task` with `asyncio.sleep`. In the new pipeline, should the filler be managed by the RAG+LLM task or the Supervisor? → **Recommend**: RAG+LLM task owns its own filler timer (simpler, fewer moving parts).
4. **Recording composition**: `compose_call_recording` runs at teardown. Should it run in the AudioExecutor? → **Yes** — move to AudioExecutor to avoid blocking the event loop during disconnect.

## 15. Phase 1 — Protocol Alignment (resolves conflicts vs. project plan §10, §2)

The project plan's §10 fixes the WebSocket message protocol as a scope decision, not a
suggestion. The pipeline plan's original message set diverged from it in four ways. All four
are fixed here before any stage code is finalized, since every other phase emits events
through this protocol.

### 15.1 `auth` message — removed entirely

§2 states authentication is explicitly out of scope. The `auth` control message doesn't
implement auth, but the name collides with that decision and isn't in §10's client message
list at all. Persona and voice selection already happen through `POST /api/sessions` before
the socket opens (§5.4, §6.3's Home/Session screen flow) — that's the source of truth.
- Remove the `auth` branch from `ws_in_task` and the handler's `control_queue` loop.
- `voice_select` is kept — it's a legitimate mid-call action (§6.3's Voice Call screen
  doesn't preclude changing voice) and doesn't collide with any named-out-of-scope decision.
  It's a protocol *extension* beyond §10, not a conflict; document it as such rather than
  silently diverging.

### 15.2 `start_call` — added, gates audio processing

§10 lists `start_call` as a required client→server type; the original plan never handled it.
Add `state.call_started: bool = False` to `SessionPipelineState`. `ws_in_task` handles it:

```python
if data.get("type") == "start_call":
    state.call_started = True
    safe_put_nowait(state.control_queue, {"type": "start_call"})
    continue
```

`vad_stt_task` drops audio chunks silently until `state.call_started` is `True` — connection
setup (session creation, pipeline task startup) still happens on WebSocket connect so `ping`
can be answered immediately, but no audio is processed pre-`start_call`.

### 15.3 Outbound event types — renamed/added to match §10 exactly

| Original pipeline plan | §10-compliant | Change |
|---|---|---|
| `{"type": "transcript", "role": "user", ...}` | `{"type": "transcript_final", ...}` | Renamed in `vad_stt_task` — matches §10's note that only final transcripts are sent, never partial |
| *(missing)* | `{"type": "turn_started", "turn_id": ...}` | Added — emitted by `_run_llm_turn` immediately after `state.current_turn_id = turn_id` is set, before sentiment/RAG |
| *(missing)* | `{"type": "response_text", "turn_id": ..., "text": sentence, "index": sentence_idx}` | Added — emitted alongside every `sentence_queue` push in `_run_llm_turn`, so the client gets AI text before/alongside audio |
| `{"type": "tts_first_audio", ...}` | `{"type": "response_audio", "turn_id": ..., "latency_ms": ...}` | Renamed in `tts_task` — this is the §10-required type; `tts_first_audio`/`tts_first_sentence` become internal latency-metric event names only, not sent as separate top-level types (folded into `response_audio`'s payload, see §17.1) |
| `{"type": "sentiment", "label": ...}` | *(kept as-is, documented as extension)* | Not in §10 — §10 only has `sentiment_alert`, which is the deferred frustrated-sentiment feature (§9), a different thing. Keeping generic per-turn `sentiment` as a documented protocol extension avoids conflating "we send sentiment data" with "we implement the alert feature," which stays deferred. |

### 15.4 Every event gets `session_id`, `sequence_number`, `timestamp`

§10: "Every JSON/control event includes session_id, sequence_number and timestamp where
applicable." None of the original pseudocode events carried these. Add a single helper and
route every `ws_event_queue` push through it instead of raw dicts:

```python
def make_event(state: SessionPipelineState, event_type: str, **fields) -> dict:
    state.event_seq += 1  # new counter field on SessionPipelineState, starts at 0
    return {
        "type": event_type,
        "session_id": state.session_id,
        "sequence_number": state.event_seq,
        "timestamp": time.time(),
        **fields,
    }
```

Every `safe_put_nowait(state.ws_event_queue, {...})` call across `vad_stt_task`,
`_run_llm_turn`, `tts_task`, and the supervisor becomes
`safe_put_nowait(state.ws_event_queue, make_event(state, "...", **fields))`.
`event_seq` must only be mutated from these single-threaded coroutines (no lock needed —
everything already runs on the one event loop).

## 16. Phase 2 — VAD: Confirmed Silero, Not webrtcvad

**Decision: Silero VAD**, contradicting the project plan's §3/§5.1, which names `webrtcvad`.
This is a deliberate override, not an oversight — flagging it explicitly so the project plan
doc gets updated to match reality rather than the two documents silently disagreeing.

- `services/vad.py`'s existing `VADBuffer` (Silero-based) is kept as-is (already listed in
  §10's "Keep" list of the original plan).
- Open Question #1 (§14) is now **closed**: Silero, full stop — remove the "webrtcvad as an
  option" framing entirely, it's not being built.
- Action outside this pipeline plan: update `AI_Voice_Agent_Backend_Frontend_Database_Plan.md`
  §3 and §5.1 to say Silero VAD instead of webrtcvad, so the two docs stop disagreeing.
- No code changes needed in `vad_stt_task` beyond what's already specified — it was already
  written against `VADBuffer`/Silero's 32ms frame size; only the project-plan cross-reference
  was wrong.

## 17. Phase 3 — Latency & Recording-Sync Metrics (closes gaps, not conflicts)

Three gaps the project plan requires that the pipeline plan didn't cover (§4 latency
measurement, §7.2 DB columns, §12 recording sync). Sentiment alert is explicitly excluded
per your note — not addressed here.

### 17.1 `llm_latency_ms`

Add to `_run_llm_turn`: start a timer right after `turn_started` is emitted (§15.3), stop it
when the `async for chunk in generate_response_stream(...)` loop exits normally (not on
cancellation — a cancelled turn has no meaningful LLM latency).

```python
llm_start = time.perf_counter()
# ... existing sentiment/RAG/system-prompt prep, then the async for loop ...
# after the loop (only if not cancelled/barged-in):
if state.current_turn_id == turn_id:
    llm_latency_ms = int((time.perf_counter() - llm_start) * 1000)
```

Attach `llm_latency_ms` to the `SentenceMessage` sentinel (`None`) push replaced with a final
`TurnComplete` message carrying `{turn_id, llm_latency_ms}` so `tts_task` (or the handler,
on `turn_ended`) can pass it through to `save_turn` for the `messages.llm_latency_ms` column.

### 17.2 Total turn latency

Defined as: time from `turn_started` to the turn's `response_audio` (first audio chunk) —
matches the frontend's "Last response latency" state field (§6.4 of the project plan) and
`messages.latency_ms` (§7.2). Computed in `tts_task` at the same point `response_audio` is
emitted (§15.3):

```python
if msg.first_sentence and first_chunk:
    total_turn_latency_ms = int((time.perf_counter() - state.turn_started_at) * 1000)
```

Requires `state.turn_started_at: float | None` set alongside `state.current_turn_id` in
`_run_llm_turn` when the turn begins. Passed through to `save_turn` as `latency_ms`.

### 17.3 Recording sync offsets (`recording_start_ms` / `recording_end_ms`)

§12/§7.2 need each message's audio boundaries within the final composed call recording, not
wall-clock time. Add `state.call_start_time: float` (set once, at `start_call`, §15.2).

- **User turns**: `vad_stt_task` records `recording_start_ms = (utterance_start_perf_counter
  - state.call_start_time) * 1000` when VAD detects speech onset, and
  `recording_end_ms` when `speech_ended` fires. Requires `VADBuffer` to expose speech-onset
  timestamp, not just the final audio bytes — check whether `services/vad.py` already tracks
  this internally; if not, it's a small addition to `VADBuffer.process_bytes`.
- **AI turns**: `tts_task` records `recording_start_ms` at the first audio chunk of the turn
  and `recording_end_ms` when the sentinel/`TurnComplete` for that turn is processed (i.e.,
  all sentences for the turn have been synthesized). Since audio composition
  (`compose_call_recording`) appends AI audio after user audio per turn, these offsets are
  relative to `state.call_start_time`, consistent with the user-turn offsets above.
- Both get attached to the same turn record passed to `save_turn`, alongside `llm_latency_ms`
  (§17.1) and `latency_ms` (§17.2) — one DB write per turn with all metrics populated, rather
  than separate partial updates.