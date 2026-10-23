# CodeLens AI

AI-assisted analysis foundation for the educational Mini Python and Mini C language subsets.

## Phase 3 status

Phase 3 adds a genuine Mini C lexer, recursive-descent parser, syntax diagnostics, parse-tree output, and frontend integration. AI generation, code execution, persistence, and comparison remain future work.

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

Returns the planned Mini Python and Mini C language subsets.

### `POST /api/analyze`

Analyzes Mini Python source without executing it.

Request:

```json
{"language":"mini_python","code":"x = 10\nprint(x)\n"}
```

The response includes `lexical_valid`, `syntax_valid`, `success`, token locations, structured diagnostics, a JSON-compatible `tree`, grammar version, and summary counts.

When recovery is possible, malformed statements remain in the partial tree with `attributes.incomplete: true`. Missing or invalid expressions are represented as `ErrorExpression` nodes with an error code and message. These nodes are not valid executable or semantic results; the application never executes submitted code.

## Mini Python grammar

Grammar version: `mini-python-1.0`.

```text
program ::= statement*
statement ::= assignment | print_statement | if_statement | while_statement
assignment ::= IDENTIFIER "=" expression NEWLINE
print_statement ::= "print" "(" expression ")" NEWLINE
if_statement ::= "if" expression ":" NEWLINE INDENT statement+ DEDENT ("else" ":" NEWLINE INDENT statement+ DEDENT)?
while_statement ::= "while" expression ":" NEWLINE INDENT statement+ DEDENT
expression ::= comparison
comparison ::= additive (("==" | "!=" | "<" | ">" | "<=" | ">=") additive)*
additive ::= multiplicative (("+" | "-") multiplicative)*
multiplicative ::= unary (("*" | "/" | "%") unary)*
unary ::= ("+" | "-") unary | primary
primary ::= NUMBER | STRING | IDENTIFIER | "True" | "False" | "(" expression ")"
```

The subset uses spaces for indentation; tabs produce a diagnostic. Blank lines and comment-only lines are ignored. Comments begin with `#` and continue to the end of the line. Numeric integers and decimals, single- and double-quoted strings, the listed operators, and the listed delimiters are supported. Full Python syntax, imports, function definitions, lists, dictionaries, `for`, and runtime semantics are unsupported.

## Mini C grammar

Grammar version: `mini-c-1.0`. Mini C is an educational subset and is not an ISO C compiler.

```text
program ::= declaration_or_statement*
declaration_or_statement ::= declaration | statement
declaration ::= type_specifier IDENTIFIER ("=" expression)? ";"
type_specifier ::= "int" | "float" | "double" | "char" | "bool"
statement ::= assignment | printf_statement | block | if_statement | while_statement
assignment ::= IDENTIFIER "=" expression ";"
printf_statement ::= "printf" "(" STRING ("," expression)* ")" ";"
block ::= "{" declaration_or_statement* "}"
if_statement ::= "if" "(" expression ")" statement ("else" statement)?
while_statement ::= "while" "(" expression ")" statement
expression ::= comparison
comparison ::= additive (("==" | "!=" | "<" | ">" | "<=" | ">=") additive)*
additive ::= multiplicative (("+" | "-") multiplicative)*
multiplicative ::= unary (("*" | "/" | "%") unary)*
unary ::= ("+" | "-" | "!") unary | primary
primary ::= NUMBER | STRING | CHARACTER | "true" | "false" | IDENTIFIER | "(" expression ")"
```

Mini C supports `//` and `/* ... */` comments, integer and decimal numbers, quoted strings, character literals, the listed operators and delimiters, nested braces, and boolean literals as an educational extension. Pointers, arrays, structs, functions, preprocessor directives, loops such as `for`, and runtime execution are unsupported. Required semicolons are enforced. Empty input is invalid, and trailing unsupported tokens produce diagnostics.

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

- Mini Python and Mini C analysis are limited to their documented grammars.
- Mini Python and Mini C are planned subsets, not complete languages.
- No source code is executed.
- No lexer, parser, AST, AI, comparison, database, or saved history exists yet.
- Public free-tier hosting may have cold starts and usage limits.
