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


sentence_splitter_graph = _build_sentence_splitter_graph()
sentiment_graph = _build_sentiment_graph()
summarizer_graph = _build_summarizer_graph()
filler_graph = _build_filler_graph()
rag_router_graph = _build_rag_router_graph()
insights_graph = _build_insights_graph()
voice_router_graph = _build_voice_router_graph()
document_pipeline_graph = _build_document_pipeline_graph()
