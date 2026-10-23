# CodeLens AI

AI-assisted analysis foundation for the educational Mini Python and Mini C language subsets.

## Phase 1 status

Phase 1 provides the React/Vite frontend skeleton, FastAPI backend connectivity, health and language metadata endpoints, tests, environment examples, and deployment guidance. Lexing, parsing, AI generation, code execution, persistence, and comparison are intentionally not implemented yet.

## Architecture

- `frontend/`: React + TypeScript + Vite application.
- `backend/`: Python + FastAPI + Pydantic API.
- Frontend and backend are deployed separately.
- The frontend receives the backend URL from `VITE_API_BASE_URL`.
- No submitted source code is executed.

## Requirements

- Node.js 20 or newer
- Python 3.11 or newer

## Local setup

### Backend

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

The backend runs at `http://127.0.0.1:8000`.

### Frontend

```powershell
Set-Location frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

The frontend runs at the URL printed by Vite, usually `http://localhost:5173`.

## Environment variables

Frontend `.env.local`:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Backend `.env`:

```text
CODELENS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Do not put API keys or credentials in frontend variables. Real `.env` files are ignored by Git.

## API

### `GET /api/health`

Returns a deployment-safe service status.

### `GET /api/languages`

Returns the planned Mini Python and Mini C language subsets. Their lexer and parser are future phases.

## Checks

Frontend production build:

```powershell
Set-Location frontend
npm run build
```

Backend tests:

```powershell
Set-Location backend
pytest
```

Manual local smoke checks:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/languages
```

## Deployment

### Backend on Render

Create a Render Web Service from this GitHub repository, with root directory `backend`:

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Environment variable: `CODELENS_ALLOWED_ORIGINS=<deployed-frontend-origin>`

Render free services may sleep after inactivity. This is acceptable for the Phase 1 demonstration but may make the first request slow.

### Frontend on Vercel

Create a Vercel project from this GitHub repository, with root directory `frontend` and the Vite framework preset. Configure:

```text
VITE_API_BASE_URL=https://<verified-render-backend-host>
```

Redeploy after setting the variable. Then update the Render CORS value to the exact deployed Vercel origin and verify the browser network request.

Deployment is not considered complete until both public URLs and frontend-to-backend connectivity have been tested.

## Known limitations

- Only health and language metadata endpoints exist in Phase 1.
- Mini Python and Mini C are planned subsets, not complete languages.
- No source code is executed.
- No lexer, parser, AST, AI, comparison, database, or saved history exists yet.
- Public free-tier hosting may have cold starts and usage limits.
