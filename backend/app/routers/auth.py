from fastapi import APIRouter, HTTPException, status, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from app.models.database import get_supabase

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str


async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    supabase = get_supabase()
    try:
        user = supabase.auth.get_user(credentials.credentials)
        if not user or not user.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return user.user
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


@router.post("/login")
async def login(data: LoginRequest):
    supabase = get_supabase()
    try:
        res = supabase.auth.sign_in_with_password({"email": data.email, "password": data.password})
        return {"access_token": res.session.access_token, "token_type": "bearer"}
    except Exception as e:
        error_text = str(e)
        if "Email not confirmed" in error_text or "email_not_confirmed" in error_text:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email not confirmed. Please confirm your email or disable email confirmation in Supabase Auth settings for development.",
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_text)


@router.post("/register")
async def register(data: RegisterRequest):
    supabase = get_supabase()
    try:
        res = supabase.auth.sign_up({"email": data.email, "password": data.password})
        return {"user_id": res.user.id}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))