# Usage

## First run without credentials

```powershell
Copy-Item .env.example .env
Copy-Item config/profile.example.yaml config/profile.yaml
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.cli init-db
python -m app.cli check-config
python -m app.cli run-cycle
python -m app.cli list-projects
python -m app.cli serve
```

Mock mode inserts representative allowed and rejected projects. AI dry-run produces a valid structured analysis without contacting a model. It never simulates a successful real Bid submission.

## CLI commands

```text
python -m app.cli init-db
python -m app.cli check-config
python -m app.cli test-ai
python -m app.cli test-freelancer
python -m app.cli test-ntfy
python -m app.cli fetch-projects
python -m app.cli analyze-pending
python -m app.cli run-cycle
python -m app.cli list-projects
python -m app.cli show-project PROJECT_ID
python -m app.cli draft PROJECT_ID
python -m app.cli approve PROJECT_ID
python -m app.cli bid PROJECT_ID --dry-run
python -m app.cli bid PROJECT_ID --confirm
python -m app.cli serve
python -m app.cli worker
```

## Safe live workflow

1. Configure a production Personal Access Token with the needed scope.
2. Set `FREELANCER_MOCK_MODE=false`; leave real submission disabled.
3. Run connection tests and fetch/analyze projects.
4. Edit the draft in the project detail page.
5. Approve the draft.
6. Run `bid PROJECT_ID --dry-run` and inspect the payload.
7. Only then set `FREELANCER_BID_SUBMISSION_ENABLED=true`.
8. Submit from the dashboard by typing `SUBMIT`, or run `bid PROJECT_ID --confirm`.

Changing the draft after approval resets approval. Failed submissions are recorded and never retried automatically.
