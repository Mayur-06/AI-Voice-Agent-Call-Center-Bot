**AI Voice Agent**

Phased Implementation Plan (Backend, Frontend & Database)

This plan reorganizes the agreed backend, frontend, and database scope into 8 sequential build phases. Each phase lists its goal and the concrete work items, grouped so that a working, testable slice of the system exists at the end of every phase.

# **Phase 1: Foundation & Project Scaffolding**

**Goal:** _Stand up the backend, frontend, and database skeleton with no voice logic yet, so every later phase has a place to plug in._

## **Backend**

- Initialize FastAPI project with the agreed folder structure (routers/, websocket/, services/, models/, schemas/, alembic/).
- Set up config.py for environment variables (API keys, DB URL, storage keys).
- Set up SQLAlchemy engine/session and Alembic migrations.
- Create Supabase PostgreSQL project and connect it.
- Create Supabase Storage buckets for documents and recordings.

## **Database**

- Define initial models: sessions, messages, personas, voices, documents, document_chunks, sentiment_records, call_metrics, recordings.
- Write and run first Alembic migration.

## **Frontend**

- Initialize React project with shadcn/ui and custom CSS setup.
- Set up Zustand store skeleton for conversation/session state.
- Scaffold empty Home/Session, Voice Call, Post-Call Review, and Analytics Dashboard screens (routing only, no logic).

## **Health & Wiring**

- Implement GET /api/health returning basic service status.
- Confirm frontend can call the backend and render a placeholder response.

# **Phase 2: Core Voice Pipeline (Single Turn, No RAG/Persona)**

**Goal:** _Get one full voice turn working end-to-end: mic → STT → LLM → TTS → playback._

## **Backend**

- Implement WS /ws/voice/{session_id} and voice_handler.py for connection lifecycle.
- Implement audio_buffer.py to collect incoming audio chunks.
- Integrate webrtcvad in vad_service.py; backend VAD is authoritative for turn boundaries.
- Integrate Groq Whisper in stt_service.py (English only).
- Handle empty/noisy transcription: skip the LLM call and prompt the user to repeat.
- Implement conversation_mgr.py for basic turn history.
- Integrate Gemini in llm_service.py (persona/RAG context added later).
- Implement tts_service.py with Edge TTS, sentence-by-sentence generation and streaming.
- Implement voice_pipeline.py to orchestrate STT → conversation → LLM → TTS.
- Set up PyAV/FFmpeg-based audio_processor.py for format conversion.

## **Frontend**

- Implement microphone capture with MediaRecorder API / Web Audio API.
- Stream audio chunks over WebSocket at the ~250 ms configurable interval.
- Implement AudioContext-based playback of streamed TTS audio.
- Build the WebSocket message protocol (start_call, audio_chunk, stop_call, ping / status, transcript_final, response_text, response_audio, turn_started, turn_ended, error, pong).
- Add basic voice call status in state: idle, listening, processing, speaking.

## **Latency**

- Measure and log STT latency, LLM latency, first-audio TTS latency, and total turn latency.

# **Phase 3: Sessions, Messages & Text Fallback**

**Goal:** _Persist real conversations to the database and support typing when the mic isn't available._

## **Backend**

- Implement POST/GET /api/sessions, GET /api/sessions/{id}, DELETE /api/sessions/{id}.
- Implement POST /api/sessions/{id}/message for text fallback.
- Persist each turn to the messages table (speaker, text, timestamp, sequence_number).
- Support the optional/nullable user_id with an anonymous UUID fallback.

## **Frontend**

- Add text fallback input on the Voice Call screen.
- Render turn-by-turn transcript live during the call.
- Wire Session ID and connection status into shared state.

# **Phase 4: Personas & Voice Selection**

**Goal:** _Let users choose a persona and one of the two Edge TTS voices before/at the start of a call._

## **Backend**

- Implement GET/POST /api/personas and seed the 4 personas (Customer Support, Technical Expert, Sales Assistant, General Assistant) with distinct system prompts.
- Implement GET /api/voices and GET /api/voices/{id}/preview for the 2 configured Edge TTS voices.
- Wire selected persona's system_prompt and voice_id into llm_service.py and tts_service.py.

## **Frontend**

- Build Home/Session screen: persona selection, voice selection with preview playback, document upload entry point.
- Store selected persona and selected voice in shared state.

# **Phase 5: Voice RAG (Documents + Pinecone)**

**Goal:** _Let the assistant answer questions grounded in uploaded documents._

## **Backend**

- Implement POST /api/documents/upload; store files in Supabase Storage via storage_service.py.
- Chunk documents and generate embeddings with sentence-transformers.
- Store chunks in Pinecone and chunk metadata in document_chunks.
- Implement rag_service.py to retrieve relevant chunks for a query.
- Feed retrieved context into llm_service.py only when the query requires it.

## **Frontend**

- Add document upload UI on the Home/Session screen.
- Add a RAG/document-context indicator in the Voice Call screen state.

# **Phase 6: Turn Management, Interruptions & Reliability**

**Goal:** _Make conversations feel natural and make the connection resilient to drops._

## **Conversation Behavior**

- Never send continuous silence to Whisper; rely on VAD silence threshold for end-of-utterance.
- Block AI response generation while the user is still speaking.
- Detect user interruption while AI is speaking; stop Edge TTS playback immediately and clear queued audio.
- Treat an interruption as a new turn while retaining prior context.
- Add filler responses for longer processing times.

## **Connection Management**

- Implement WebSocket heartbeat/ping-pong and stale-connection detection.
- Implement automatic client reconnect using the existing session_id.
- Persist session/conversation state so a temporary disconnect doesn't lose the conversation.
- Handle graceful shutdown, saving conversation state before closing.

# **Phase 7: Recording, Sentiment, Summary & Analytics**

**Goal:** _Turn raw conversations into reviewable, analyzable call data._

## **Recording & Sync**

- Compose user and AI audio into one final call recording, preserving synchronized offsets.
- Store recording_start_ms/recording_end_ms per message for synchronized playback.
- Upload final recordings to Supabase Storage via storage_service.py.

## **Sentiment & Summary**

- Implement sentiment_analyzer.py to classify sentiment per user turn.
- Implement a real-time post-turn frustrated-sentiment alert (sentiment_alert message).
- Implement call_summarizer.py to generate the post-call summary.

## **Backend APIs**

- Implement GET /api/sessions/{id}/transcript, /recording, /summary, /sentiment, /metrics.
- Implement GET /api/analytics for aggregate stats.

## **Frontend**

- Build Post-Call Review screen: synchronized transcript + recording playback, sentiment timeline, summary, metrics.
- Build Analytics Dashboard: total calls, duration, sentiment, latency, calls over time, per-persona performance (Recharts).

# **Phase 8: Exports, Polish & Testing**

**Goal:** _Finish user-facing export features and validate the system against the full testing checklist._

## **Exports**

- Implement GET /api/sessions/{id}/export/transcript?format=txt|json.
- Implement GET /api/sessions/{id}/export/recording?format=mp3|wav.
- Implement GET /api/sessions/{id}/export/summary?format=pdf.
- Add export/download controls and state on the Post-Call Review screen.

## **Testing Checklist**

- Audio chunks arrive approximately every 250 ms.
- Backend VAD correctly detects speech/silence and is authoritative for turn boundaries.
- Whisper returns valid English transcription.
- Empty/noisy/low-quality transcription does not reach the LLM and prompts a repeat.
- LLM receives full conversation history.
- TTS generates valid audio for both configured Edge TTS voices; both previews work.
- Audio plays correctly in the browser.
- WebSocket reconnects after connection loss, and session/conversation state survives it.