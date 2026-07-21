# Resume Master

AI-powered resume tailoring for a specific job description, with an application tracker. Rewrites your resume to match a JD using an LLM, keeps the output ATS-friendly and free of buzzwords, and exports to PDF.

- **Backend:** FastAPI · Python 3.13 · LiteLLM (multi-provider) · SQLite
- **Frontend:** Next.js 16 · React 19 · Tailwind v4
- **PDF:** headless Chromium (Playwright)

## Quickstart

**Backend** (`:8000`):

```bash
cd apps/backend
uv sync --extra dev
cp .env.example .env          # set your LLM provider + key (see below)
uv run playwright install chromium
uv run uvicorn app.main:app --reload --port 8000
```

**Frontend** (`:3000`, separate terminal):

```bash
cd apps/frontend
npm install
npm run dev
```

Open http://localhost:3000.

## LLM config

Set the provider in `apps/backend/.env`. Supported: `openai`, `anthropic`, `gemini`, `groq`, `openrouter`, `deepseek`, `ollama`, `openai_compatible`.

Example — Groq:

```env
LLM_PROVIDER=groq
LLM_MODEL=groq/openai/gpt-oss-120b
LLM_API_KEY=gsk_...
```

## Tests

```bash
cd apps/backend && uv run pytest
cd apps/frontend && npm run test
```

## License & attribution

Apache License 2.0 — see [`LICENSE`](LICENSE). Personal fork of [srbhr/Resume-Matcher](https://github.com/srbhr/Resume-Matcher); original work and copyright belong to the upstream authors.
