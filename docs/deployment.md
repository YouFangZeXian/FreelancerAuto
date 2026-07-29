# Deployment

## Docker Compose

1. Copy `.env.example` to `.env`.
2. Copy `config/profile.example.yaml` to `config/profile.yaml` and tailor it locally.
3. Keep `FREELANCER_MOCK_MODE=true` and `AI_DRY_RUN=true` for the first local check.
4. Run `docker compose up -d --build`.
5. Open `http://localhost:8000`.
6. Inspect logs with `docker compose logs -f web worker`.

The `web` service exposes the control console. The `worker` service runs the cycle every `SCHEDULER_INTERVAL_MINUTES` and shares `./data` and `./config` with the web process.

## Production / Alibaba Cloud ECS

- Install Docker Engine and the Compose plugin.
- Put the repository under an application directory owned by a non-root service account.
- Restrict inbound access to a reverse proxy; do not expose Uvicorn directly to the public internet.
- Add TLS and access control in Nginx, Caddy, Cloudflare Access, or an equivalent gateway.
- Back up `data/freelancer_auto.db`, `config/filters.yaml` and `config/profile.yaml` securely. Do not commit `.env` or `config/profile.yaml` to a public repository.
- Rotate the Freelancer Personal Access Token at least every 30 days as documented by Freelancer.
- Start with real bid submission disabled. Enable it only after live connection tests and a successful dry-run on the exact approved draft.

## Switching to Sandbox

Set:

```env
FREELANCER_MOCK_MODE=false
FREELANCER_BASE_URL=https://www.freelancer-sandbox.com
FREELANCER_ACCESS_TOKEN=<sandbox token>
```

Sandbox and production tokens cannot be exchanged.
