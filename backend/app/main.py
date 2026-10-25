import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.languages.mini_python.analyzer import analyze_mini_python
from app.languages.mini_c.analyzer import analyze_mini_c
from app.automata import MAX_AUTOMATA_INPUT, get_automaton, list_automata, simulate
from app.ai_provider import AIProviderError, GrokProvider, MAX_SOURCE_LENGTH, SUPPORTED_LANGUAGES

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


class AutomataSimulationRequest(BaseModel):
    input: str = Field(max_length=MAX_AUTOMATA_INPUT)


class GenerateAlternativeRequest(BaseModel):
    language: str
    source_code: str = Field(max_length=MAX_SOURCE_LENGTH)


class GenerateAlternativeResponse(BaseModel):
    language: str
    generated_code: str
    provider: str
    model: str


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
            Language(id="mini_python", name="Mini Python", status="implemented subset"),
            Language(id="mini_c", name="Mini C", status="implemented subset"),
        ]
    )


@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze(request: AnalyzeRequest) -> AnalysisResponse:
    if request.language == "mini_python":
        return AnalysisResponse(**analyze_mini_python(request.code))
    if request.language == "mini_c":
        return AnalysisResponse(**analyze_mini_c(request.code))
    if request.language not in {"mini_python", "mini_c"}:
        raise HTTPException(
            status_code=422,
            detail="Unsupported language. Choose mini_python or mini_c.",
        )


@app.get("/api/automata")
def automata() -> dict:
    return {"automata": list_automata()}


@app.get("/api/automata/{automaton_id}")
def automaton_detail(automaton_id: str) -> dict:
    definition = get_automaton(automaton_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Unknown automaton.")
    return definition


@app.post("/api/automata/{automaton_id}/simulate")
def automaton_simulate(automaton_id: str, request: AutomataSimulationRequest) -> dict:
    definition = get_automaton(automaton_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Unknown automaton.")
    return simulate(definition, request.input)


@app.post("/api/generate-alternative", response_model=GenerateAlternativeResponse)
def generate_alternative(request: GenerateAlternativeRequest) -> GenerateAlternativeResponse:
    if request.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=422, detail="Unsupported language. Choose mini_python or mini_c.")
    if not request.source_code.strip():
        raise HTTPException(status_code=422, detail="Source code must not be blank.")
    try:
        generated_code, model = GrokProvider().generate(request.language, request.source_code)
    except AIProviderError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    return GenerateAlternativeResponse(
        language=request.language,
        generated_code=generated_code,
        provider="grok",
        model=model,
    )
