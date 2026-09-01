**AI Voice Agent**

Backend, Frontend & Database Implementation Plan

# 1\. Project Objective

- Build a Real-Time Turn-Based Voice AI assistant that users can interact with through a browser microphone. "Real-time" refers to low-latency conversational response timing, not frame-by-frame phoneme processing.
- Capture user audio and send it to the FastAPI backend through WebSocket.
- Convert speech to text using Whisper with English as the supported STT language.
- Process the user query using an LLM with conversation history and RAG context when required.
- Convert the AI response to speech using Edge TTS.
- Support exactly 2 selectable Edge TTS voices with voice previews.
- Stream generated audio back to the browser for playback.
- Maintain conversation context across turns.
- Support document-based Voice RAG using Pinecone.
- Provide call recording, turn-by-turn transcript, sentiment analysis, call summary and call analytics.
- Provide text fallback when the microphone is unavailable.
- Provide synchronized post-call transcript and recording review.
- Provide transcript, recording and summary export options.

# 2\. Agreed Implementation Decisions and Scope Boundaries

- STT language: English only. Additional STT languages are intentionally out of scope for this implementation.
- TTS provider: Edge TTS will be used instead of ElevenLabs/OpenAI TTS.
- TTS voice count: exactly 2 Edge TTS voices will be configured and exposed for selection and preview.
- Personas: 4 personas will be implemented. Because only 2 TTS voices are being used, voices may be shared across personas; the personas remain differentiated by system prompt, specialization and behavior.
- Frontend: React, CSS (custom css is required) and shadcn/ui.
- RAG/vector store: Pinecone is used only for document embeddings and retrieval.
- Application database: Supabase PostgreSQL stores application/session metadata and relational data.
- ORM: SQLAlchemy.
- Database migrations: Alembic.
- File/object storage: Supabase Storage for uploaded documents and final call recordings.

The user_id field is optional and nullable; when authentication is unavailable, an anonymous fallback identifier may be used solely to associate sessions without implementing full user identity management.

- Authentication is out of scope unless added later. Sessions can be identified by UUID.

# 3\. Overall Architecture

- Frontend: React + custom CSS + shadcn/ui.
- Backend: FastAPI + Python.
- Real-time communication: WebSocket.
- Speech-to-Text: Groq Whisper; English only.
- LLM: Google Gemini
- Text-to-Speech: Edge TTS with exactly 2 configured voices.
- Voice Activity Detection: webrtcvad.
- RAG: Pinecone+ sentence-transformers.
- Application database: Supabase PostgreSQL.
- Database access: SQLAlchemy.
- Database migrations: Alembic.
- File storage: Supabase Storage for uploaded documents and call recordings.
- Audio processing: PyAV, which requires the underlying FFmpeg shared libraries

# 4\. Voice Pipeline

- Browser microphone captures audio using MediaRecorder API or Web Audio API.
- Audio chunks are sent to the backend through WebSocket at an approximately 250 ms configurable interval.
- Backend VAD detects speech onset and speech offset and is the authoritative source for turn boundaries. Client-side VAD, if enabled, is non-authoritative and is used only as an optional performance/UI optimization.
- Backend buffers audio until end-of-utterance is detected.
- Groq Whisper converts the completed utterance into English text.
- If the transcription is empty, noisy or unusable, the system does not call the LLM and asks the user to repeat.
- Conversation manager adds conversation history.
- RAG retrieves relevant document context when the query requires uploaded documents.
- LLM generates the response.
- The response is split into sentences where possible as a core pipeline requirement so Edge TTS can generate and stream audio sentence-by-sentence.
- Edge TTS converts response sentences into audio.
- Audio chunks are streamed back through WebSocket.
- Browser plays the AI response through AudioContext.
- The system measures STT latency, LLM latency, first-audio TTS latency and total turn latency.

# 5\. Backend Plan

# 5.1 Backend Technology

- FastAPI with WebSocket support.
- asyncio and httpx for asynchronous processing and external API calls.
- SQLAlchemy for PostgreSQL database access.
- Alembic for database schema migrations.
- Groq Whisper for English STT.
- Edge TTS for speech synthesis.
- LLM provider such as Gemini
- webrtcvad.
- Pinecone for vector retrieval.
- sentence-transformers for document embeddings.
- PyAV, which requires the underlying FFmpeg shared libraries, for audio conversion and recording preparation.
- Supabase Storage for documents and recordings.

# 5.2 Backend Folder Structure

backend/

app/

main.py

config.py

routers/

sessions.py

documents.py

personas.py

voices.py

analytics.py

exports.py

websocket/

voice_handler.py

audio_buffer.py

protocol.py

services/

stt_service.py

tts_service.py

llm_service.py

voice_pipeline.py

vad_service.py

audio_processor.py

conversation_mgr.py

sentiment_analyzer.py

call_summarizer.py

rag_service.py

storage_service.py

models/

database.py

session.py

message.py

persona.py

document.py

analytics.py

recording.py

voice.py

schemas/

session.py

message.py

persona.py

analytics.py

export.py

alembic/

versions/

env.py

script.py.mako

recordings/ # temporary/local processing only if required

uploads/ # temporary/local processing only if required

alembic.ini

requirements.txt

# 5.3 Backend Services

- voice_handler.py – manages WebSocket connections, audio messages, status updates, heartbeats and errors.
- audio_buffer.py – collects incoming audio chunks until the utterance is complete.
- vad_service.py – detects speech onset and speech offset.
- stt_service.py – sends completed audio to Whisper and returns English transcription.
- conversation_mgr.py – maintains turn history, context and speaker information.
- rag_service.py – processes uploaded documents and retrieves relevant Pinecone chunks for voice questions.
- llm_service.py – combines persona instructions, conversation history, RAG context and the current question.
- tts_service.py – converts AI responses to Edge TTS audio, manages the 2 configured voices and performs the required sentence-by-sentence generation and streaming.
- audio_processor.py – converts audio formats and prepares recordings.
- storage_service.py – uploads and retrieves document/recording files through Supabase Storage.
- sentiment_analyzer.py – classifies user sentiment per turn.
- call_summarizer.py – generates the post-call summary.
- voice_pipeline.py – orchestrates STT → conversation/RAG → LLM → Edge TTS.

# 5.4 Backend API Plan

- WS /ws/voice/{session_id} – real-time audio streaming.
- POST /api/sessions – create a voice session.
- GET /api/sessions – list voice sessions.
- GET /api/sessions/{id} – session details and transcript.
- DELETE /api/sessions/{id} – delete session and associated recording metadata/files.
- POST /api/sessions/{id}/message – text fallback message.
- GET /api/sessions/{id}/transcript – full timestamped transcript.
- GET /api/sessions/{id}/recording – call recording.
- GET /api/sessions/{id}/summary – generated call summary.
- GET /api/sessions/{id}/sentiment – sentiment timeline.
- GET /api/sessions/{id}/metrics – call metrics.
- POST /api/documents/upload – upload documents for Voice RAG.
- GET/POST /api/personas – list/create personas.
- GET /api/voices – list the 2 available Edge TTS voices.
- GET /api/voices/{id}/preview – generate/return a voice preview.
- GET /api/analytics – aggregate analytics.
- GET /api/health – health status for STT, TTS and LLM.
- GET /api/sessions/{id}/export/transcript?format=txt|json – export transcript.
- GET /api/sessions/{id}/export/recording?format=mp3|wav – export recording.
- GET /api/sessions/{id}/export/summary?format=pdf – export call summary.

# 6\. Frontend Plan

# 6.1 Frontend Technology

- React
- Custom CSS.
- shadcn/ui.
- MediaRecorder API or Web Audio API for microphone capture.
- Native WebSocket API.
- AudioContext for low-latency TTS playback.
- Zustand for conversation state.
- Recharts for sentiment and analytics charts.
- wavesurfer.js optionally for waveform visualization.

# 6.3 Frontend Screens

- Home / Session screen – select persona, select one of the 2 voices, upload documents and start a call.
- Voice Call screen – microphone button, audio visualizer, turn-by-turn transcript, persona information, text fallback, mute/end-call controls and latency indicator.
- Post-Call Review – synchronized transcript and recording playback, sentiment timeline, summary, call metrics and export controls.
- Analytics Dashboard – total calls, duration, sentiment, latency, calls over time and per-persona performance.

# 6.4 Frontend State

- Session ID.
- Connection status.
- Voice call status: idle, listening, processing or speaking.
- Turn-by-turn transcript.
- Selected persona.
- Selected Edge TTS voice.
- Microphone/mute state.
- Last response latency.
- STT, LLM and TTS stage latency for the latest turn.
- RAG/document context indicator.
- Recording/playback state.
- Export/download state.

# 7\. Database Plan

# 7.1 Database Choice

- Use Supabase PostgreSQL as the main application database.
- Use SQLAlchemy for database access.
- Use Alembic for schema migrations.
- Use Pinecone separately for document embeddings and retrieval.
- Use Supabase Storage for uploaded documents and final call recordings rather than storing large audio files directly in PostgreSQL.

# 7.2 Key Table Fields

- sessions: id, user_id (optional/nullable anonymous fallback identifier), persona_id, status, started_at, ended_at, duration, selected_voice.
- messages: id, session_id, speaker, text, timestamp, audio_url, recording_start_ms, recording_end_ms, sentiment, latency_ms, stt_latency_ms, llm_latency_ms, tts_first_audio_latency_ms, sequence_number.
- personas: id, name, description, system_prompt, voice_id, domain, avatar_url.
- voices: id, name, voice_id, language, preview_url.
- documents: id, session_id, filename, file_type, storage_path, status, uploaded_at.
- document_chunks: id, document_id, chunk_text, embedding_id, metadata.
- sentiment_records: id, session_id, message_id, sentiment, score, created_at.
- call_metrics: id, session_id, total_duration, user_speaking_time, agent_speaking_time, turn_count, average_latency, sentiment_score, resolution_status.
- recordings: id, session_id, storage_path, duration, file_size, created_at.

# 8\. Conversation & Turn Management

- Do not send continuous silence to Whisper.
- Detect the end of an utterance using VAD and a configurable silence threshold.
- Do not generate an AI response while the user is still speaking.
- When AI is speaking, monitor for user interruption.
- Stop Edge TTS playback immediately when the user interrupts.
- Clear queued AI audio after interruption.
- Process the interruption as a new turn while retaining previous context.
- Store each turn with speaker, text, timestamp, audio reference, recording offsets and sentiment.
- Use filler responses where needed for longer processing times.

# 9\. Other Features

- Customer Support persona – empathetic, patient and solution-oriented.
- Technical Expert persona – precise, knowledgeable and step-by-step.
- Sales Assistant persona – friendly, persuasive and feature-focused.
- General Assistant persona – balanced and helpful.
- Personas use the configured 2 Edge TTS voices; the voices may be shared across personas.
- Sentiment classification per user turn.
- Real-time post-turn frustrated-sentiment alert.
- Synchronized transcript-to-recording playback using message audio offsets.

# 10\. WebSocket Message Protocol

- Define an explicit bidirectional protocol.
- Client → Server message types: start_call, audio_chunk, stop_call, ping.
- Server → Client message types: status, transcript_final, response_text, response_audio, turn_started, turn_ended, sentiment_alert, error, pong. The implementation uses turn-based transcription: Whisper returns the final transcript after VAD detects end-of-utterance; partial/streaming transcript events are not required.
- Every JSON/control event includes session_id, sequence_number and timestamp where applicable.
- Audio payloads use binary WebSocket messages where practical; JSON is used for metadata/control messages.
- Default microphone chunk interval is approximately 250 ms and remains configurable for latency tuning.

# 11\. Connection Management & Recovery

- Implement WebSocket heartbeat/ping-pong handling and stale-connection detection.
- Implement automatic client reconnect with the existing session_id.
- Persist session/conversation state so a temporary WebSocket disconnect does not lose the conversation.
- Handle graceful shutdown and save the current conversation state before closing the session.

# 12\. Recording & Transcript Synchronization

- The final call recording must contain both user and AI audio.
- Each message stores exact audio segment boundaries needed for synchronized playback.

Backend audio composition orchestrates user and AI audio into a unified final call recording, preserving synchronized turn timestamps and message-level audio offsets.

- Temporary audio processing may use local files before the final recording is uploaded to Supabase Storage.

# 14\. Testing Checklist

- Audio chunks arrive approximately every 250 ms.
- Backend VAD detects speech and silence and is authoritative for turn boundaries; client-side VAD is optional and non-authoritative.
- Whisper returns valid English transcription.
- Empty/noisy/low-quality transcription does not reach the LLM and prompts the user to repeat.
- LLM receives conversation history.
- TTS generates valid audio for both configured Edge TTS voices.
- Voice previews work for both voices.
- Audio plays correctly in the browser.
- WebSocket reconnects after connection loss.
- Session and conversation state survive a temporary WebSocket reconnect.