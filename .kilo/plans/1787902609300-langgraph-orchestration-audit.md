# LLM / LangGraph Refactor Audit

Goal: identify places in the current backend that are manually orchestrated but should be handled by LLM/LangGraph instead, with concrete migration guidance.

## Current State Summary
- Voice agent pipeline is manually orchestrated in `app/websocket/handler.py` using asyncio primitives.
- Several “AI” steps are direct API calls with no orchestration, retry, or fallback layer.
- Some logic is hardcoded instead of model/runtime-driven.
- Two auth systems coexist: Supabase Auth and custom JWT auth.

## Detailed Comparison Table

| Area | Current Manual Implementation | File(s) | Lines | Why Manual Is Problematic | Recommended LangGraph Approach |
|------|-------------------------------|---------|-------|---------------------------|--------------------------------|
| Conversation state machine | asyncio.Lock, task cancel, message_queue, audio_tasks set, current_turn_task_ref dict | `app/websocket/handler.py` | 128-395 | Brittle cancellation, race conditions, hard to extend states | StateGraph with nodes: idle, listening, processing, responding, playing; edges for interruption/reconnect |
| Turn-taking + interruption | Manual task cancel + reconnect logic | `app/websocket/handler.py` | 132-138, 340-350, 372-377 | Race conditions; cleanup can leak tasks on disconnect | Interruptible graph nodes with `Command` resume; LangGraph handles state persistence |
| Sentence splitting | Regex `re.split(r"(?<=[.!?])\s+", ...)` | `app/services/sentences.py` | 1-9 | Breaks on abbreviations ("Dr."), numbers ("3.14"), quotes | LLM splitter node that respects semantic boundaries; can insert SSML pauses |
| Sentiment analysis | Direct Gemini call, no retry | `app/services/sentiment_analyzer.py` | 1-16 | No fallback if Gemini fails; always returns "neutral" on error | Graph node with retry policy; fallback to rule-based heuristic; output to conversation context |
| Call summarization | Direct Gemini call, no validation | `app/services/call_summarizer.py` | 1-19 | Static prompt; no validation that JSON output is well-formed | Graph node: transcript → topics → action_items → sentiment_overview → structured validator |
| Filler responses | Hardcoded strings: "I'm sorry, I'm taking too long..." | `app/websocket/handler.py` | 72, 109 | Mechanical UX; no differentiation between thinking/searching/escalating | Context-aware LLM filler node based on query type and latency |
| RAG routing | Always retrieve context from ChromaDB | `app/websocket/handler.py` | 202-218 | Wastes latency/tokens on chit-chat; unnecessary ChromaDB calls | LLM router node: classify query as document-related or conversational; conditional edge to retriever |
| Analytics | Manual aggregation: counts, averages | `app/routers/analytics.py` | 1-28 | Simple stats only; no insight layer | Agent insight node: detect anomalies, trends, generate recommendations |
| Voice/persona selection | Hardcoded defaults: `voice_id = "en-IN-NeerjaNeural"` | `app/websocket/handler.py` | 263; `app/routers/voices.py` | 1-15 | Cannot adapt to user history or sentiment | Dynamic graph routing based on user profile, sentiment, conversation context |
| Document upload pipeline | Linear sync: read → split → embed → index | `app/routers/documents.py` | 16-28 | No validation, retry, or progress feedback; single failure aborts all | LangGraph pipeline: extract → chunk → embed → index → validate with retries and checkpoints |

## Top Refactor Targets (Prioritized)

### P0: Conversation Orchestration (Highest Impact)
**Current:** 395 lines of manual asyncio orchestration in `handler.py`  
**Target:** LangGraph StateGraph with ~100 lines of graph definition + node functions  
**Benefit:** Declarative state transitions, built-in interruption handling, easier testing

### P1: LLM-Gated Routing (Medium Impact)
**Current:** Unconditional ChromaDB calls + hardcoded filler  
**Target:** Add LLM router node before RAG; dynamic filler node  
**Benefit:** Reduced latency/token waste, better UX

### P2: Text Processing Nodes (Low Effort, High Quality)
**Current:** Regex sentence splitting, raw Gemini calls for sentiment/summary  
**Target:** LLM splitter + graph-wrapped sentiment/summary with retry/fallback  
**Benefit:** Better text quality, graceful degradation

### P3: Document Upload Pipeline (Medium Effort)
**Current:** Linear script in router  
**Target:** LangGraph pipeline with progress tracking  
**Benefit:** Resilience, observability

## Migration Strategy

### Phase 1: Graph Skeleton
1. Define LangGraph State model matching current session/turn data
2. Extract node functions from existing services (STT, LLM, TTS, RAG)
3. Build graph: Preflight → Audio/VAD Router → STT → Transcript Validator → RAG Router → LLM → TTS Stream → Post-Turn
4. Keep existing WebSocket handler as thin wrapper that calls `graph.invoke()`

### Phase 2: Replace Manual Orchestration
1. Move state machine logic into graph edges
2. Replace task cancel + queue with graph `interrupt()` + `Command`
3. Add checkpointing for session resume after disconnect

### Phase 3: Add LLM Nodes
1. Replace regex splitter with LLM splitter node
2. Wrap sentiment/summary in graph nodes with retry/fallback
3. Add RAG router LLM node
4. Replace static filler with dynamic filler node

### Phase 4: Document Upload Graph
1. Build separate graph for document processing
2. Add progress streaming back to client via WebSocket

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LangGraph adds latency | Medium | High | Benchmark each node; keep critical path <500ms |
| Graph complexity exceeds manual code | Low | Medium | Start with minimal graph; iterate |
| LLM routing misclassification | Medium | Medium | Fallback to always-on RAG if confidence low |
| Checkpoint storage overhead | Low | Low | Use in-memory for MVP; Redis for production |

## Validation Plan
1. Unit tests for each graph node (mock LLM/STT/TTS)
2. Integration tests: full session simulation with traced graph execution
3. Latency measurement per node; target <2s end-to-end
4. A/B test: manual vs graph on 50 sessions; compare latency and success rate

## Open Questions
1. Should LangGraph checkpointing use in-memory, Redis, or Supabase? (Recommend Redis for cloud deployment)
2. Should we keep existing WebSocket handler structure or replace entirely? (Recommend thin wrapper over graph)
3. Do we need streaming graph execution for TTS, or batch? (Recommend streaming for perceived latency)
