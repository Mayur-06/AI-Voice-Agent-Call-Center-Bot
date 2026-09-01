from langgraph.graph import StateGraph, END, START

from app.orchestration.state import (
    SentenceSplitterState,
    SentimentState,
    SummarizerState,
    FillerState,
    RagRouterState,
    InsightsState,
    VoiceRouterState,
    DocumentPipelineState,
    ConversationState,
)
from app.orchestration.nodes import (
    sentence_splitter_node,
    sentiment_node,
    summarizer_node,
    filler_node,
    rag_router_node,
    insights_node,
    voice_router_node,
    extract_node,
    chunk_node,
    embed_node,
    index_node,
    validate_node,
    preflight_node,
    audio_vad_router_node,
    stt_node,
    transcript_validator_node,
    retriever_node,
    generate_response_node,
    tts_node,
    post_turn_node,
    interrupted_node,
)


def _build_sentence_splitter_graph():
    graph = StateGraph(SentenceSplitterState)
    graph.add_node("split", sentence_splitter_node)
    graph.add_edge(START, "split")
    graph.add_edge("split", END)
    return graph.compile()


def _build_sentiment_graph():
    graph = StateGraph(SentimentState)
    graph.add_node("analyze", sentiment_node)
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", END)
    return graph.compile()


def _build_summarizer_graph():
    graph = StateGraph(SummarizerState)
    graph.add_node("summarize", summarizer_node)
    graph.add_edge(START, "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()


def _build_filler_graph():
    graph = StateGraph(FillerState)
    graph.add_node("generate", filler_node)
    graph.add_edge(START, "generate")
    graph.add_edge("generate", END)
    return graph.compile()


def _build_rag_router_graph():
    graph = StateGraph(RagRouterState)
    graph.add_node("route", rag_router_node)
    graph.add_edge(START, "route")
    graph.add_edge("route", END)
    return graph.compile()


def _build_insights_graph():
    graph = StateGraph(InsightsState)
    graph.add_node("analyze", insights_node)
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", END)
    return graph.compile()


def _build_voice_router_graph():
    graph = StateGraph(VoiceRouterState)
    graph.add_node("route", voice_router_node)
    graph.add_edge(START, "route")
    graph.add_edge("route", END)
    return graph.compile()


def _build_document_pipeline_graph():
    graph = StateGraph(DocumentPipelineState)
    graph.add_node("extract", extract_node)
    graph.add_node("chunk", chunk_node)
    graph.add_node("embed", embed_node)
    graph.add_node("index", index_node)
    graph.add_node("validate", validate_node)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "chunk")
    graph.add_edge("chunk", "embed")
    graph.add_edge("embed", "index")
    graph.add_edge("index", "validate")
    graph.add_conditional_edges(
        "validate",
        lambda s: "retry" if not s.get("validated") and s.get("retries", 0) < 2 else "end",
        {"retry": "extract", "end": END},
    )
    return graph.compile()


def _build_conversation_graph():
    graph = StateGraph(ConversationState)
    graph.add_node("preflight", preflight_node)
    graph.add_node("audio_vad_router", audio_vad_router_node)
    graph.add_node("stt", stt_node)
    graph.add_node("transcript_validator", transcript_validator_node)
    graph.add_node("rag_router", rag_router_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("generate_response", generate_response_node)
    graph.add_node("tts", tts_node)
    graph.add_node("post_turn", post_turn_node)
    graph.add_node("interrupted", interrupted_node)

    graph.add_edge(START, "preflight")
    graph.add_edge("preflight", "audio_vad_router")
    graph.add_edge("audio_vad_router", "stt")
    graph.add_edge("stt", "transcript_validator")
    graph.add_edge("transcript_validator", "rag_router")
    graph.add_conditional_edges(
        "rag_router",
        lambda s: "retriever" if s.get("should_retrieve") else "generate_response",
        {"retriever": "retriever", "generate_response": "generate_response"},
    )
    graph.add_edge("retriever", "generate_response")
    graph.add_edge("generate_response", "tts")
    graph.add_edge("tts", "post_turn")
    graph.add_edge("post_turn", END)

    graph.add_edge("interrupted", END)
    return graph.compile()


sentence_splitter_graph = _build_sentence_splitter_graph()
sentiment_graph = _build_sentiment_graph()
summarizer_graph = _build_summarizer_graph()
filler_graph = _build_filler_graph()
rag_router_graph = _build_rag_router_graph()
insights_graph = _build_insights_graph()
voice_router_graph = _build_voice_router_graph()
document_pipeline_graph = _build_document_pipeline_graph()
conversation_graph = _build_conversation_graph()
