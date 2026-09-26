from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    debug=settings.DEBUG,
)


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
