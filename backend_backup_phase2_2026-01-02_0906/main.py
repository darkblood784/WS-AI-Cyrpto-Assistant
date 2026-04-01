from fastapi import FastAPI

from app.routers.auth import router as auth_router
from app.routers import plans, chat, threads

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True, "service": "wsai-backend", "port": 8010}

@app.get("/")
def root():
    return {"message": "WSAI backend is running"}

app.include_router(auth_router)
app.include_router(plans.router)
app.include_router(chat.router)
app.include_router(threads.router)
