from fastapi import FastAPI
from app.routers.auth import router as auth_router
from app.routers import plans


app = FastAPI()
app.include_router(plans.router)

@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"ok": True, "service": "wsai-backend", "port": 8010}

@app.get("/")
def root():
    return {"message": "WSAI backend is running"}

app.include_router(auth_router)
