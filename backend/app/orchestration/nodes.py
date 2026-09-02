import json
import re
from google import genai
from google.genai import types
from app.config import settings


_client = genai.Client(api_key=settings.google_api_key)


async def _call_gemini(prompt: str, model: str | None = None) -> str:
    model_name = model or settings.gemini_model
    response = await _client.aio.models.generate_content(
        model=model_name,
        contents=[prompt],
    )
    return response.text or ""


async def sentence_splitter_node(state: dict) -> dict:
    text = state.get("text", "").strip()
    if not text:
        return {"text": text, "sentences": []}

    prompt = (
        "Split the following text into individual sentences. "
        "Respect semantic boundaries and handle abbreviations, numbers, and quotes correctly. "
        'Return ONLY a JSON array of strings, nothing else. Example: ["Sentence 1.", "Sentence 2."]\n\n'
        f"Text: {text}"
    )

    try:
        result = await _call_gemini(prompt)
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
        sentences = json.loads(cleaned)
        if isinstance(sentences, list) and all(isinstance(s, str) for s in sentences):
            return {"text": text, "sentences": sentences}
    except Exception:
        pass

    parts = re.split(r"(?<=[.!?])\s+", text)
    return {"text": text, "sentences": [part for part in parts if part]}


async def sentiment_node(state: dict) -> dict:
    text = state.get("text", "")
    retries = state.get("retries", 0)

    prompt = (
        "Classify sentiment of this message as EXACTLY one of: positive, neutral, negative, frustrated.\n"
        f"Message: '{text}'"
    )

    try:
        result = await _call_gemini(prompt)
        sentiment = result.strip().lower()
        if sentiment in {"positive", "neutral", "negative", "frustrated"}:
            return {"text": text, "sentiment": sentiment, "retries": retries}
    except Exception:
        pass

    positive_words = ["good", "great", "excellent", "happy", "thank", "thanks", "love", "wonderful"]
    negative_words = ["bad", "terrible", "awful", "hate", "angry", "frustrated", "upset", "worst"]

    text_lower = text.lower()
    pos_count = sum(1 for w in positive_words if w in text_lower)
    neg_count = sum(1 for w in negative_words if w in text_lower)

    if neg_count > pos_count:
        sentiment = "frustrated" if "frustrated" in text_lower or "angry" in text_lower else "negative"
    elif pos_count > neg_count:
        sentiment = "positive"
    else:
        sentiment = "neutral"

    return {"text": text, "sentiment": sentiment, "retries": retries + 1}


async def summarizer_node(state: dict) -> dict:
    transcript = state.get("transcript", "")

    prompt = (
        "Generate a structured post-call summary from this transcript in JSON format containing:\n"
        '- key_topics (list of strings)\n'
        '- decisions_made (list of strings)\n'
        '- action_items (list of strings)\n'
        '- resolution_status (string)\n'
        '- sentiment_overview (string)\n\n'
        f"Transcript:\n{transcript}\n\n"
        "Return ONLY valid JSON, no markdown, no explanation."
    )

    try:
        result = await _call_gemini(prompt)
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
        parsed = json.loads(cleaned)

        required = ["key_topics", "decisions_made", "action_items", "resolution_status", "sentiment_overview"]
        if all(k in parsed for k in required):
            return {"transcript": transcript, "summary": json.dumps(parsed), "validated": True}
    except Exception:
        pass

    fallback = {
        "key_topics": [],
        "decisions_made": [],
        "action_items": [],
        "resolution_status": "unknown",
        "sentiment_overview": "neutral",
    }
    return {"transcript": transcript, "summary": json.dumps(fallback), "validated": False}


async def filler_node(state: dict) -> dict:
    context_type = state.get("context_type", "thinking")
    latency_ms = state.get("latency_ms", 0)

    prompt = (
        f"Generate a brief, natural-sounding filler phrase for a voice assistant that is {context_type}. "
        f"Current response latency is {latency_ms}ms. "
        "Return ONLY the filler text, no quotes, no explanation. "
        "Examples: 'Let me look into that...', 'One moment please...', 'Checking now...'"
    )

    try:
        result = await _call_gemini(prompt)
        message = result.strip().strip('"').strip("'")
        if message:
            return {"context_type": context_type, "latency_ms": latency_ms, "message": message}
    except Exception:
        pass

    fillers = {
        "thinking": "Let me think about that for a moment...",
        "searching": "Searching our knowledge base...",
        "escalating": "Let me connect you with a specialist...",
    }
    return {"context_type": context_type, "latency_ms": latency_ms, "message": fillers.get(context_type, "Please hold...")}


async def rag_router_node(state: dict) -> dict:
    query = state.get("query", "")

    prompt = (
        "Classify whether the following user query requires retrieving information from a document knowledge base. "
        "Return ONLY 'yes' or 'no'. "
        "Examples that need retrieval: 'What does the policy say about X?', 'Find information about Y'. "
        "Examples that don't need retrieval: 'Hello', 'How are you?', 'Tell me a joke', 'What time is it?'.\n\n"
        f"Query: {query}"
    )

    try:
        result = await _call_gemini(prompt)
        answer = result.strip().lower()
        should_retrieve = answer == "yes"
        confidence = 0.9 if should_retrieve or answer == "no" else 0.5
        return {"query": query, "should_retrieve": should_retrieve, "confidence": confidence}
    except Exception:
        return {"query": query, "should_retrieve": False, "confidence": 0.0}


async def insights_node(state: dict) -> dict:
    sessions = state.get("sessions", [])
    turns = state.get("turns", [])

    total_sessions = len(sessions)
    total_turns = len(turns)

    latencies = [t["latency_ms"] for t in turns if t.get("latency_ms") is not None]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    sentiments = [t["sentiment"] for t in turns if t.get("sentiment")]
    sentiment_breakdown = {s: sentiments.count(s) for s in set(sentiments) if s}

    durations = []
    for s in sessions:
        started = s.get("started_at")
        ended = s.get("ended_at")
        if started and ended:
            try:
                from datetime import datetime
                start_dt = datetime.fromisoformat(started)
                end_dt = datetime.fromisoformat(ended)
                durations.append((end_dt - start_dt).total_seconds())
            except Exception:
                pass

    avg_duration = sum(durations) / len(durations) if durations else 0

    anomalies = []
    if avg_latency > 5000:
        anomalies.append("High average latency detected")
    if total_sessions > 0 and total_turns / total_sessions < 1:
        anomalies.append("Low engagement rate detected")

    insights = {
        "total_sessions": total_sessions,
        "total_turns": total_turns,
        "avg_latency_ms": round(avg_latency, 2),
        "avg_session_duration_s": round(avg_duration, 2),
        "sentiment_breakdown": sentiment_breakdown,
        "interruption_count": sum(1 for t in turns if t.get("interrupted")),
        "anomalies": anomalies,
    }

    return {"sessions": sessions, "turns": turns, "insights": insights}


async def voice_router_node(state: dict) -> dict:
    sentiment = state.get("sentiment", "neutral")
    conversation = state.get("conversation", [])

    prompt = (
        "Based on the user's sentiment and conversation context, recommend a voice persona. "
        "Return ONLY the persona_id from the available options: default, professional, friendly, empathetic. "
        "If the user is frustrated or upset, choose 'empathetic'. "
        "If the conversation is formal/work-related, choose 'professional'. "
        "If the user is cheerful, choose 'friendly'. "
        "Default to 'default' if unsure.\n\n"
        f"Current sentiment: {sentiment}\n"
        f"Conversation length: {len(conversation)} messages"
    )

    try:
        result = await _call_gemini(prompt)
        persona_id = result.strip().lower().replace(" ", "_")
        valid_personas = {"default", "professional", "friendly", "empathetic"}
        if persona_id not in valid_personas:
            persona_id = "default"
        return {**state, "persona_id": persona_id}
    except Exception:
        return {**state, "persona_id": "default"}


async def extract_node(state: dict) -> dict:
    file_bytes = state.get("file_bytes", b"")
    filename = state.get("filename", "")

    if filename.lower().endswith(".pdf"):
        try:
            from PyPDF2 import PdfReader
            import io
            reader = PdfReader(io.BytesIO(file_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            if not text.strip():
                return {**state, "text": "", "error": "Empty PDF text", "status": "error"}
            return {**state, "text": text, "error": None, "status": "extracted"}
        except Exception as exc:
            return {**state, "text": "", "error": f"Failed to extract text from PDF: {exc}", "status": "error"}
    else:
        try:
            text = file_bytes.decode("utf-8")
            return {**state, "text": text, "error": None, "status": "extracted"}
        except Exception as exc:
            return {**state, "text": "", "error": f"Failed to decode file: {exc}", "status": "error"}


async def chunk_node(state: dict) -> dict:
    text = state.get("text", "")
    if not text:
        return {**state, "chunks": [], "status": "chunked"}

    chunk_size = 500
    overlap = 50
    cleaned = re.sub(r"\s+", " ", text).strip()
    chunks = []
    start = 0
    while start < len(cleaned):
        end = start + chunk_size
        chunk = cleaned[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap

    return {**state, "chunks": chunks, "status": "chunked"}


async def embed_node(state: dict) -> dict:
    chunks = state.get("chunks", [])
    if not chunks:
        return {**state, "embeddings": [], "status": "embedded"}

    try:
        from app.services.rag import _get_model
        model = _get_model()
        embeddings = model.encode(chunks, show_progress_bar=False).tolist()
        return {**state, "embeddings": embeddings, "status": "embedded"}
    except Exception as exc:
        return {**state, "embeddings": [], "error": f"Embedding failed: {exc}", "status": "error"}


async def index_node(state: dict) -> dict:
    chunks = state.get("chunks", [])
    embeddings = state.get("embeddings", [])
    document_id = state.get("document_id", "")

    if not chunks or not embeddings:
        return {**state, "status": "indexed"}

    try:
        from app.services.rag import store_chunks_in_pinecone
        store_chunks_in_pinecone(document_id, None, chunks, embeddings)
        return {**state, "status": "indexed"}
    except Exception as exc:
        return {**state, "error": f"Indexing failed: {exc}", "status": "error"}


async def validate_node(state: dict) -> dict:
    chunks_count = len(state.get("chunks", []))
    status = state.get("status", "")
    error = state.get("error")
    retries = state.get("retries", 0)

    if error or chunks_count == 0:
        if retries >= 2:
            return {**state, "validated": False, "error": error or "Validation failed after retries"}
        return {**state, "validated": False, "retries": retries + 1}

    return {**state, "chunks_count": chunks_count, "validated": True}
