# Sprint Planning 2.0 — Monorepo

Implementation of the Sprint Planning 2.0 platform described in `../docs/design-doc.md`.

## Layout

```
src/
├── docker-compose.yml      # One-shot local stack
├── platform/               # FastAPI orchestrator (A2A Client)
├── agents/
│   ├── po-agent/           # Reference Product Owner A2A Remote Agent
│   └── dev-agent/          # Reference Developer A2A Remote Agent
├── ui/                     # React human-participant proxy (Vite + SSE)
└── shared/                 # Protocol contracts & shared docs
```

## Run locally

```
cd src
docker compose up --build
```

Services:

| Service     | URL                       |
|-------------|---------------------------|
| Platform    | http://localhost:8000     |
| PO agent    | http://localhost:8001     |
| Dev agent   | http://localhost:8002     |
| UI          | http://localhost:5173     |
| Postgres    | localhost:5432            |
| Redis       | localhost:6379            |

Health check:

```
curl http://localhost:8000/health
curl http://localhost:8001/.well-known/agent.json
curl http://localhost:8002/.well-known/agent.json
```
