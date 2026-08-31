from fastapi import APIRouter
from app.orchestration.graphs import voice_router_graph

router = APIRouter(prefix="/api/voices", tags=["voices"])

_FALLBACK_VOICES = [
    {"voice_id": "en-IN-NeerjaNeural", "name": "Neerja (Female, India)", "language": "en-IN", "gender": "female"},
    {"voice_id": "en-IN-PrabhatNeural", "name": "Prabhat (Male, India)", "language": "en-IN", "gender": "male"},
    {"voice_id": "en-US-JennyNeural", "name": "Jenny (Female, US)", "language": "en-US", "gender": "female"},
]


async def list_voices():
    return list(_FALLBACK_VOICES)


@router.get("/")
async def get_voices():
    try:
        voices = await list_voices()
    except Exception:
        voices = list(_FALLBACK_VOICES)

    transformed = []
    for v in voices:
        if "ShortName" in v:
            transformed.append({
                "voice_id": v.get("ShortName"),
                "name": v.get("Name", v.get("ShortName", "")),
                "language": v.get("Locale", ""),
                "gender": v.get("Gender", "").lower(),
                "preview_url": None,
            })
        else:
            transformed.append({
                "voice_id": v.get("id", v.get("voice_id")),
                "name": v.get("name", v.get("Name", "")),
                "language": v.get("language", v.get("Locale", "")),
                "gender": v.get("gender", v.get("Gender", "")).lower(),
                "preview_url": v.get("preview_url"),
            })

    try:
        route_state = await voice_router_graph.ainvoke({
            "sentiment": "neutral",
            "conversation": [],
            "voice_id": transformed[0]["voice_id"] if transformed else _FALLBACK_VOICES[0]["voice_id"],
            "persona_id": "default",
        })
        recommended = route_state.get("persona_id", "default")
        for v in transformed:
            if v["voice_id"] == _FALLBACK_VOICES[0]["voice_id"]:
                v["recommended_for"] = recommended
                break
    except Exception:
        pass

    return transformed
