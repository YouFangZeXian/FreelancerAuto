# FreelancerAuto

A runnable Freelancer.com project monitoring, AI analysis, notification and human-approved bidding system built with FastAPI, SQLAlchemy, SQLite, APScheduler, Jinja2 and httpx.

## Completion status

- [x] Stage 1: official Freelancer API findings with source links
- [x] Stage 2: configuration, database and Freelancer API client
- [x] Stage 3: search, local filtering, dedupe and persistence
- [x] Stage 4: OpenAI-compatible AI provider and strict structured analysis
- [x] Stage 5: ntfy notifications
- [x] Stage 6: responsive human review console
- [x] Stage 7: official Bid API client with manual approval and safe fallback
- [x] Stage 8: tests, Docker deployment and operating documentation

## Safety defaults

- `FREELANCER_MOCK_MODE=true`
- `AI_DRY_RUN=true`
- `FREELANCER_BID_SUBMISSION_ENABLED=false`
- Every Bid requires an approved draft and a separate final confirmation.
- There is no unattended bulk-bidding switch.
- CAPTCHA bypass, stolen cookies and UI click automation are not implemented.

## Quick start

```powershell
Copy-Item .env.example .env
Copy-Item config/profile.example.yaml config/profile.yaml
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.cli init-db
python -m app.cli run-cycle
python -m app.cli serve
```

Open [http://localhost:8000](http://localhost:8000).

Docker:

```powershell
Copy-Item .env.example .env
Copy-Item config/profile.example.yaml config/profile.yaml
docker compose up -d --build
```

## Configuration

- Secrets and endpoints: `.env`
- Local screening: `config/filters.yaml`
- Freelancer capability profile: `config/profile.yaml` (local and private; create it from `config/profile.example.yaml`)
- Non-secret AI model, timeout, notification threshold and cycle interval can also be edited in the web console.

The AI provider uses `${AI_BASE_URL}/chat/completions`, so OpenAI, DeepSeek and other OpenAI-compatible gateways can be selected without source changes.

## Publishing to GitHub safely

Keep one working folder; do not maintain a second copied project. The repository includes safe templates (`.env.example` and `config/profile.example.yaml`) while `.env`, `config/profile.yaml`, and local SQLite data are excluded from Git. Docker also excludes the private files from image build layers.

Before your first commit, confirm the staged file list contains neither `.env` nor `config/profile.yaml`:

```powershell
git init
git add .
git status
```

## Documentation

- [Freelancer API findings](docs/freelancer-api-findings.md)
- [Architecture](docs/architecture.md)
- [Usage](docs/usage.md)
- [Deployment](docs/deployment.md)

## Tests

```powershell
pytest -q
```
