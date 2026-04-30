# BGPX

BGP Toolkit and Looking Glass.

BGPX is a lightweight network diagnostics platform that combines a FastAPI backend with a React/Tailwind frontend, delivered over HTTPS from a single runtime. It currently provides operational **health**, **ping**, and **traceroute** capabilities and is structured for clean growth into broader looking-glass/BGP tooling.

---

## Features

### Implemented
- `GET /api/health` backend health check
- `GET /api/ping?host=<target>` single-probe ICMP ping
- `GET /api/traceroute?host=<target>` traceroute with normalized hop data
- HTTPS runtime via Uvicorn (default port `443`)
- Python-managed self-signed cert generation for local/dev environments
- Integrated frontend + backend serving model

### Planned / Coming Soon
- BGP lookup workflows
- ASN lookup workflows
- Prefix lookup workflows
- Additional looking-glass diagnostics

---

## Architecture Overview

### Runtime model
- **Backend**: FastAPI + Uvicorn (`code/backend`)
- **Frontend**: React + TypeScript + Vite + Tailwind (`code/frontend`)
- In production-style flow, frontend assets are built (`code/frontend/dist`) and served by FastAPI.
- API remains under `/api/*`.

### Backend layer design
The backend is organized with explicit layer boundaries:

`api -> apps -> services/infra -> models`

- `api/`: Route composition and transport contracts
- `apps/`: Feature-level orchestration
- `services/`: Domain/service logic (currently mainly SSL cert service)
- `infra/`: Low-level/network integrations (ICMP adapters/parsers)
- `models/`: Shared feature contracts

---

## Repository Structure

```text
.
├── README.md
├── LICENSE
├── bruno-requests/
│   └── BGPX/
│       ├── opencollection.yml
│       ├── Get_Health.yml
│       ├── Ping.yml
│       ├── Traceroute.yml
│       └── Samples/
├── code/
│   ├── requirements.txt
│   ├── backend/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── apps/
│   │   ├── infra/
│   │   ├── models/
│   │   ├── services/
│   │   └── tests/
│   └── frontend/
│       ├── package.json
│       ├── vite.config.ts
│       └── src/
└── ssl-certs/ (generated locally, ignored by git)
```

---

## Prerequisites

- Python 3.11+ recommended
- Node.js 20+ and npm
- A system/network environment where ICMP operations are allowed

Install backend dependencies:

```bash
python3 -m pip install -r code/requirements.txt
```

Install frontend dependencies:

```bash
cd code/frontend
npm install
```

---

## Quick Start (Integrated HTTPS App)

1) Build frontend assets:

```bash
cd code/frontend
npm run build
```

2) Run backend (serves API + built frontend):

```bash
cd code/backend
python3 main.py
```

3) Open:

- App: `https://localhost/`
- API health: `https://localhost/api/health`

> Note: local certs are self-signed by default, so browsers/clients may require trust configuration.

---

## Development Workflow

### Option A: Split terminals (common frontend workflow)

Terminal 1 (backend):

```bash
cd code/backend
python3 main.py
```

Terminal 2 (frontend dev server):

```bash
cd code/frontend
npm run dev
```

Vite proxies `/api` to `https://localhost:443` (see `code/frontend/vite.config.ts`).

### Option B: Single backend terminal with frontend dev redirect mode

```bash
cd code/backend
python3 main.py --dev
```

In this mode, backend:
- sets frontend mode to dev,
- auto-starts Vite if not already running,
- redirects non-API routes to the frontend dev URL (default `http://localhost:5173`).

---

## Configuration

### Runtime environment variables

- `BGPX_HOST` (default: `0.0.0.0`)
- `BGPX_PORT` (default: `443`)
- `BGPX_FRONTEND_MODE` (`dist` or `dev`, default: `dist`)
- `BGPX_FRONTEND_DEV_URL` (default: `http://localhost:5173`)

### Test-related environment variables

- `BGPX_API_BASE_URL` (used by integration tests hitting a live endpoint)
- `BGPX_CA_BUNDLE` (optional CA bundle path for HTTPS verification in ping integration test)

---

## API Reference (Current)

### Health

```http
GET /api/health
```

Example response:

```json
{
  "status": "ok",
  "service": "bgpx-backend"
}
```

### Ping

```http
GET /api/ping?host=1.1.1.1
```

Example response:

```json
{
  "result": "success",
  "ping_time_ms": 12.34,
  "ttl": 57,
  "message": "ping success"
}
```

### Traceroute

```http
GET /api/traceroute?host=8.8.8.8
```

Example response:

```json
{
  "result": "success",
  "hops": [
    {
      "distance": 1,
      "address": "192.168.1.1",
      "rtts_ms": [1.1],
      "avg_rtt_ms": 1.1,
      "min_rtt_ms": 1.1,
      "max_rtt_ms": 1.1,
      "packets_sent": 1,
      "packets_received": 1,
      "packet_loss": 0.0
    }
  ],
  "message": "traceroute completed: success"
}
```

---

## Testing

Backend tests use **pytest**.

Run all backend tests:

```bash
pytest code/backend/tests
```

Run unit tests only:

```bash
pytest code/backend/tests/unit
```

Run integration tests only:

```bash
pytest code/backend/tests/integration
```

---

## Bruno API Requests

Ready-to-run Bruno collection is provided under:

- `bruno-requests/BGPX/`

Includes:
- `Get_Health.yml`
- `Ping.yml`
- `Traceroute.yml`
- CRUD request samples in `Samples/` as templates

Collection docs: `bruno-requests/README.md`

---

## TLS / Certificates

On startup, backend ensures certificate files exist in `ssl-certs/`:

- `bgpx.net.crt`
- `bgpx.net.key`

If missing, they are generated automatically via `code/backend/services/sslCert_service.py` for local/dev use.

---

## Troubleshooting

- **Frontend returns 404 in dist mode**
  - Build frontend first: `cd code/frontend && npm run build`
- **HTTPS certificate warnings**
  - Expected with self-signed local certs; trust cert locally or use `curl -k` for quick checks
- **Ping/traceroute behavior differs by environment**
  - ICMP/network permissions and routing policies can affect outcomes
- **Traceroute integration test fails in restricted environments**
  - Ensure runtime has required network capabilities/permissions

---

## License

This project is licensed under **GNU Affero General Public License v3.0**.

See: [`LICENSE`](./LICENSE)

