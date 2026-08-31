from app.orchestration.graphs import sentence_splitter_graph


async def split_sentences(text: str) -> list[str]:
    result = await sentence_splitter_graph.ainvoke({"text": text})
    return result.get("sentences", [])
