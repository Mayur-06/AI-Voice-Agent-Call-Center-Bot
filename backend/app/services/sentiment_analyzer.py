from app.orchestration.graphs import sentiment_graph


async def analyze_sentiment(user_text: str) -> str:
    result = await sentiment_graph.ainvoke({"text": user_text, "retries": 0})
    return result.get("sentiment", "neutral")
