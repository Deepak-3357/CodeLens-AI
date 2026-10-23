import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()


class HealthResponse(BaseModel):
    status: str
    service: str


class Language(BaseModel):
    id: str
    name: str
    status: str


class LanguagesResponse(BaseModel):
    languages: list[Language]


def configured_origins() -> list[str]:
    raw_origins = os.getenv(
        "CODELENS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


app = FastAPI(title="CodeLens AI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins(),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="codelens-ai-backend")


@app.get("/api/languages", response_model=LanguagesResponse)
def languages() -> LanguagesResponse:
    return LanguagesResponse(
        languages=[
            Language(id="mini_python", name="Mini Python", status="planned subset"),
            Language(id="mini_c", name="Mini C", status="planned subset"),
        ]
    )
