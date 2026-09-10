from app.orchestration.graphs import summarizer_graph


async def generate_call_summary(conversation_history: list[dict]) -> str:
    transcript = "\n".join(
        [f"{m['role']}: {m['content']}" for m in conversation_history]
    )
    result = await summarizer_graph.ainvoke({"transcript": transcript})
    return result.get("summary", "")
