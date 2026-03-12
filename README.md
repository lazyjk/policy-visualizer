![Policy Visualizer](docs/assets/policy_visualizer_icon_package/policy_visualizer_github_banner_fixed_v2.svg)

Policy Visualizer converts a network policy XML service export into:

- a normalized policy model,
- a compiled decision-flow graph,
- and an interactive browser diagram.

![Policy Visualizer screenshot](docs/assets/policy-visualizer-screenshot.png)

## What it does

- Parses **Aruba ClearPass** and **Cisco ISE** service export XML (RADIUS + TACACS); format is auto-detected on upload
- Normalizes policy conditions into canonical Boolean expressions
- Builds deterministic Policy IR and Flow IR
- Serves Flow IR from a FastAPI backend
- Renders an interactive flow diagram in a React Flow frontend with WYSIWYG annotation support
- Surfaces full rule conditions and actions in a Policy Details side panel (click any decision or action node)
- Exports diagrams to PNG, SVG, PDF, and Draw.io format (BETA)
- Exports PDF with optional policy details appendix (rule tables, conditions, actions)
- Supports static SVG/PNG/PDF generation via CLI (ClearPass only; offline/scripted use)

## Tech Stack

- **Backend/API:** FastAPI, defusedxml
- **Compiler pipeline:** Python — ClearPass (`src/parser.py`, `src/normalizer.py`, `src/policy_ir.py`, `src/flow_ir.py`) and Cisco ISE (`src/ise_parser.py`, `src/ise_normalizer.py`, `src/ise_policy_ir.py`, `src/ise_flow_ir.py`)
- **Frontend:** React + Vite + React Flow + Dagre + Tiptap
- **Packaging:** Docker + docker-compose
- **Static rendering:** Graphviz (ClearPass only; offline CLI use)

## Prerequisites

### Option A (recommended): Docker

- Docker Desktop with Compose support

### Option B: Local development

- Python 3.11+
- Node.js 20+
- Graphviz installed and on PATH (not required for web app — only needed for CLI static rendering)

## Run with Docker

From repository root:

```bash
docker compose up --build
```

Services:

- Frontend: http://localhost:80
- API: http://localhost:8000
- API health: http://localhost:8000/api/health

## Run locally (without Docker)

### 1) Backend/API

From repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### 2) Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Default frontend dev URL: http://localhost:5173

## CLI usage (offline / scripted, ClearPass only)

> The interactive web app (Docker or local dev) is the recommended workflow. The CLI renders static diagrams from ClearPass XML only and does not require the web stack.

From repository root:

```bash
python -m src.cli path/to/service.xml --output diagram.svg
```

Examples:

```bash
# List services in XML
python -m src.cli path/to/service.xml --list-services

# Render specific service
python -m src.cli path/to/service.xml --service "My Service Name" --output diagram.svg

# Render PNG/PDF
python -m src.cli path/to/service.xml --output diagram.png --format png
python -m src.cli path/to/service.xml --output diagram.pdf --format pdf
```

## API endpoints

- `GET /api/health` — liveness check
- `POST /api/services` — upload XML and list services (ClearPass or ISE; format auto-detected)
- `POST /api/flow` — upload XML and compile selected/default service to Flow IR

The maximum upload size is **10 MB**; files larger than this return HTTP `413`. Other error statuses: `415` (wrong extension), `422` (invalid XML structure or no services found), `500` (processing error). Unresolved object references are soft-failed — the API returns HTTP `200` with a `warnings` array in the response.

## Test suite

From repository root:

```bash
.venv/bin/pytest tests/
```

Current collected count: **245 tests**.

To regenerate the documented totals:

```bash
# Total collected tests (includes parametrized expansion)
.venv/bin/python -m pytest --collect-only -q tests

# Per-file collected counts
.venv/bin/python -m pytest --collect-only -q tests | awk -F'::' '/^tests\//{count[$1]++} END{for (f in count) printf "%s %d\n", f, count[f]}' | sort
```

## Project structure (high level)

- `src/` — ClearPass and ISE parser, normalizer, policy IR, flow IR, renderer, CLI
- `api/` — FastAPI app and routes
- `frontend/` — React app and diagram components
- `tests/` — parser/normalizer/policy/flow/API tests and fixtures
- `docs/` — feature specs, release map (2.0, historical), and per-version release notes (`docs/releases/`)

## Notes

- Supports both Aruba ClearPass and Cisco ISE XML exports; format is auto-detected on upload.
- Annotations support rich text (bold, italic, bullets, fonts, images) via the WYSIWYG editor.
- The app is deterministic by design: same XML input produces the same compiled graph structure.
- Current workflow is upload/view-only (no policy editing UI).

## License

MIT © 2026 James Jackson
