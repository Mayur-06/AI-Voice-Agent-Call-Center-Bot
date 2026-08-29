from fastapi import APIRouter, Depends, HTTPException, status
from app.models.database import get_supabase
from app.models.schemas import PersonaCreate, Persona
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/personas", tags=["personas"])


@router.post("", response_model=Persona)
async def create_persona(data: PersonaCreate, user=Depends(get_current_user)):
    supabase = get_supabase()
    res = supabase.table("personas").insert({
        "name": data.name,
        "system_prompt": data.system_prompt,
        "voice_id": data.voice_id,
        "voice_settings": data.voice_settings,
    }).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create persona")
    return Persona(**res.data[0])


@router.get("", response_model=list[Persona])
async def list_personas(user=Depends(get_current_user)):
    supabase = get_supabase()
    res = supabase.table("personas").select("*").execute()
    return [Persona(**p) for p in res.data]
