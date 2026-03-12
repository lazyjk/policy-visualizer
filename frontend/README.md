# Policy Visualizer — Frontend

React + Vite + TypeScript frontend for [Policy Visualizer](../README.md).

## Overview

This is the interactive web UI. It uploads a ClearPass or Cisco ISE XML export,
renders an interactive flow diagram using React Flow + dagre, and provides a
Policy Details side panel, WYSIWYG annotation editor, and multi-format export
(PNG, SVG, PDF, PDF+appendix, Draw.io).

## Local Development

Requires the FastAPI backend running on `:8000`. See the root README for full
setup instructions.

```bash
npm install
npm run dev
```

The dev server runs at `http://localhost:5173` and proxies `/api` requests to
`http://localhost:8000`.

## Available Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start dev server with HMR |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | Run ESLint |

## Tests

There are no frontend-specific tests currently. Backend and API tests live in
`tests/` at the repository root and are run with `.venv/bin/pytest tests/`.

## Full Setup

For Docker-based setup, local backend setup, and API documentation, see the
[root README](../README.md).
