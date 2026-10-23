import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.languages.mini_python.analyzer import analyze_mini_python

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


class AnalyzeRequest(BaseModel):
    language: str
    code: str = Field(max_length=100_000)


class TokenResponse(BaseModel):
    type: str
    lexeme: str
    line: int
    column: int
    end_line: int
    end_column: int


class DiagnosticResponse(BaseModel):
    severity: str
    code: str
    message: str
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None


class AnalysisResponse(BaseModel):
    language: str
    grammar_version: str
    lexical_valid: bool
    syntax_valid: bool
    success: bool
    tokens: list[TokenResponse]
    diagnostics: list[DiagnosticResponse]
    tree: dict | None
    summary: dict[str, int]


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
    allow_methods=["GET", "POST"],
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


@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze(request: AnalyzeRequest) -> AnalysisResponse:
    if request.language != "mini_python":
        raise HTTPException(
            status_code=422,
            detail="Only the mini_python analyzer is available in Phase 2; mini_c is planned for a later phase.",
        )
    return AnalysisResponse(**analyze_mini_python(request.code))
