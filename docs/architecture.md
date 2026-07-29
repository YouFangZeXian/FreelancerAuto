# Architecture

## Data flow

```text
Freelancer API / mock data
  -> ProjectService (normalize + Project ID dedupe)
  -> FilterService (YAML rules, zero AI cost)
  -> AnalysisService (strict JSON contract)
  -> SQLite (project + analysis + editable draft)
  -> NotificationService (threshold + ntfy dedupe)
  -> Web/CLI human review
  -> BidService preflight
  -> Freelancer Bid API or manual project link
```

## Module boundaries

- `app/clients`: external HTTP contracts for Freelancer and ntfy.
- `app/ai`: OpenAI-compatible provider with timeout, retry, JSON parsing and schema validation.
- `app/models`: the required eight persistent tables.
- `app/repositories`: database access for projects.
- `app/services`: filtering, analysis, notification, cycle orchestration, runtime settings and bid safety.
- `app/api`: JSON health and project endpoints.
- `app/web.py` + `app/templates`: server-rendered review console.
- `app/tasks`: APScheduler worker.
- `app/cli.py`: operational commands.

SQLite runs in WAL mode with foreign keys and a busy timeout so the web and worker containers can share the mounted database. For larger multi-user deployments, replace SQLite with PostgreSQL before horizontal scaling.

## Security boundaries

- Secrets are accepted only from environment variables and never written by the settings UI.
- Logs redact bearer tokens, Freelancer OAuth headers and API-key-like values.
- Raw project/AI payloads are stored, but configuration secrets are never part of those payloads.
- No route or CLI command performs unattended bulk bidding.
- Approval is invalidated whenever proposal, price or delivery time changes.

