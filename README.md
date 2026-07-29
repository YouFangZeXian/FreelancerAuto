# FreelancerAuto / Freelancer.com 项目监控与辅助投标系统

**中文**：一个可直接运行的 Freelancer.com 项目监控、智能筛选、AI 分析与人工确认投标系统。它帮助你发现合适项目、生成中英双语投标草稿，并把真实投标始终保留在人工确认之后。

**English**: A runnable Freelancer.com project monitoring, intelligent filtering, AI analysis, and human-approved bidding system. It helps you find suitable projects, generate bilingual proposal drafts, and keeps real bid submission behind explicit human confirmation.

Built with FastAPI, SQLAlchemy, SQLite, APScheduler, Jinja2, and httpx.

## 已实现功能 / Implemented features

- [x] Freelancer 官方 API 调研与来源文档 / Official Freelancer API research and source documentation
- [x] 配置、数据库与 Freelancer API 客户端 / Configuration, database, and Freelancer API client
- [x] 项目搜索、本地筛选、去重与持久化 / Project search, local filtering, deduplication, and persistence
- [x] OpenAI 兼容 AI 分析与严格结构化输出 / OpenAI-compatible AI analysis with strict structured output
- [x] ntfy 通知 / ntfy notifications
- [x] 响应式人工审核控制台 / Responsive human-review console
- [x] 官方 Bid API 客户端、人工批准与安全降级 / Official Bid API client, manual approval, and safe fallback
- [x] 测试、Docker 部署与使用文档 / Tests, Docker deployment, and operating documentation

## 安全默认值 / Safety defaults

- `FREELANCER_MOCK_MODE=true`：默认使用模拟项目，不访问真实项目数据。 / Uses sample projects by default and does not access live project data.
- `AI_DRY_RUN=true`：默认不调用真实 AI 服务。 / Does not call a live AI provider by default.
- `FREELANCER_BID_SUBMISSION_ENABLED=false`：默认禁用真实投标。 / Real bid submission is disabled by default.
- 每次投标都必须先批准草稿，再进行一次独立的最终确认。 / Every bid requires an approved draft and a separate final confirmation.
- 不提供无人值守批量投标、验证码绕过、盗取 Cookie 或网页点击自动化。 / No unattended bulk-bidding, CAPTCHA bypass, stolen cookies, or browser-click automation is implemented.

## 快速开始 / Quick start

### 本地 Python 运行 / Run locally with Python

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

打开 / Open: [http://localhost:8000](http://localhost:8000)

### Docker 运行 / Run with Docker

```powershell
Copy-Item .env.example .env
Copy-Item config/profile.example.yaml config/profile.yaml
docker compose up -d --build
```

## 配置说明 / Configuration

- `.env`：密钥、服务端点与运行时环境变量；仅本地保存，绝不能提交。 / Secrets, provider endpoints, and runtime environment variables; keep this file local and never commit it.
- `config/filters.yaml`：可公开提交的本地筛选规则。 / Local filtering rules that are safe to commit.
- `config/profile.yaml`：你的能力、报价与可用时间；从 `config/profile.example.yaml` 创建，仅本地保存。 / Your capabilities, pricing, and availability; create it from `config/profile.example.yaml` and keep it local.
- 网页控制台也可修改不含密钥的 AI 模型、超时、通知阈值与轮询间隔。 / The web console can also edit non-secret AI model, timeout, notification threshold, and polling interval settings.

AI 服务使用 `${AI_BASE_URL}/chat/completions`，因此无需改动源码即可使用 OpenAI、DeepSeek 或其他兼容 OpenAI 的网关。

The AI provider uses `${AI_BASE_URL}/chat/completions`, allowing OpenAI, DeepSeek, and other OpenAI-compatible gateways to be selected without source changes.

## 安全发布到 GitHub / Publish to GitHub safely

只维护一个工作目录，不要复制出第二个项目版本。仓库提交安全模板（`.env.example` 与 `config/profile.example.yaml`），而 `.env`、`config/profile.yaml` 和本地 SQLite 数据库会被 Git 忽略；Docker 构建也会排除这些私密文件。

Keep one working directory rather than maintaining a second copied project. The repository tracks safe templates (`.env.example` and `config/profile.example.yaml`), while `.env`, `config/profile.yaml`, and local SQLite data are ignored by Git. Docker build contexts also exclude the private files.

首次提交前，确认暂存列表不包含 `.env` 或 `config/profile.yaml`：

Before the first commit, confirm that neither `.env` nor `config/profile.yaml` appears in the staged file list:

```powershell
git init
git add .
git status
```

## 文档 / Documentation

- [Freelancer API 调研 / Freelancer API findings](docs/freelancer-api-findings.md)
- [系统架构 / Architecture](docs/architecture.md)
- [使用说明 / Usage](docs/usage.md)
- [部署说明 / Deployment](docs/deployment.md)

## 测试 / Tests

```powershell
pytest -q
```
