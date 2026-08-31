from fastapi import APIRouter, HTTPException, status
from app.models.database import get_supabase
from app.models.schemas import PersonaCreate, Persona
from typing import List

router = APIRouter(prefix="/api/personas", tags=["personas"])


@router.get("/", response_model=List[Persona])
async def list_personas():
    supabase = get_supabase()
    res = supabase.table("personas").select("*").execute()
    return res.data or []


@router.post("/", response_model=Persona, status_code=status.HTTP_201_CREATED)
async def create_persona(persona_data: PersonaCreate):
    supabase = get_supabase()
    res = supabase.table("personas").insert(persona_data.model_dump()).execute()
    return res.data[0]
