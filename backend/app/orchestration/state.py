from typing import TypedDict, Annotated, Sequence, Optional, Any
from langgraph.graph import add_messages


class ConversationState(TypedDict):
    session_id: str
    conversation: list[dict[str, str]]
    messages: Annotated[Sequence[Any], add_messages]
    current_turn: Optional[dict[str, Any]]
    voice_id: str
    persona_id: str
    sentiment: str
    context: list[str]
    status: str
    partial_response: str
    error: Optional[str]
    user_text: str
    filler_message: Optional[str]
    should_retrieve: bool
    interrupted: bool


class SentenceSplitterState(TypedDict):
    text: str
    sentences: list[str]


class SentimentState(TypedDict):
    text: str
    sentiment: str
    retries: int


class SummarizerState(TypedDict):
    transcript: str
    summary: str
    validated: bool


class FillerState(TypedDict):
    context_type: str
    latency_ms: int
    message: str


class RagRouterState(TypedDict):
    query: str
    should_retrieve: bool
    confidence: float


class InsightsState(TypedDict):
    sessions: list[dict]
    turns: list[dict]
    insights: dict


class VoiceRouterState(TypedDict):
    sentiment: str
    conversation: list[dict[str, str]]
    voice_id: str
    persona_id: str


class DocumentPipelineState(TypedDict):
    file_bytes: bytes
    filename: str
    persona_id: str
    text: str
    chunks: list[str]
    embeddings: list[list[float]]
    document_id: str
    chunks_count: int
    error: Optional[str]
    status: str
    retries: int
