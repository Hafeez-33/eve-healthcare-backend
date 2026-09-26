from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    debug=settings.DEBUG,
)

app.include_router(auth_router)


@app.get("/", tags=["General"])
def read_root():
    return {
        "message": "EVE Healthcare Backend API",
        "status": "running",
    }


@app.get("/health", tags=["General"])
def health_check():
    return {
        "status": "healthy",
    }
