from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.auth import router as auth_router
from app.routers.auth import get_current_user, MeResponse
from app.routers import plans, chat, threads, admin, public
from app.db.models import User
from fastapi import Depends
from app.core.config import settings

app = FastAPI()


def _parse_cors_origins(raw: str) -> list[str]:
    origins = [o.strip() for o in (raw or "").split(",")]
    return [o for o in origins if o]


allowed_origins = _parse_cors_origins(settings.CORS_ALLOW_ORIGINS)
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.get("/health")
def health():
    return {"ok": True, "service": "wsai-backend", "port": 8010}

@app.get("/")
def root():
    return {"message": "WSAI backend is running"}

@app.get("/me", response_model=MeResponse, tags=["auth"])
def me_alias(user: User = Depends(get_current_user)):
    return MeResponse(id=user.id, email=user.email, is_active=user.is_active)

app.include_router(auth_router)
app.include_router(plans.router)
app.include_router(chat.router)
app.include_router(threads.router)
app.include_router(admin.router)
app.include_router(public.router)
