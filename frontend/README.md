# Munki Manager Frontend

React SPA built with [Vite](https://vite.dev), [React Router](https://reactrouter.com), [Tailwind CSS](https://tailwindcss.com), and [shadcn/ui](https://ui.shadcn.com).

## Getting Started

```bash
bun install
bun dev
```

Open [http://localhost:3000](http://localhost:3000). The Vite dev server proxies `/api/*`, `/repo/*`, and `/icons/*` to the backend at `http://localhost:8000`.

## Build

```bash
bun run build
```

Output goes to `dist/`. In production the Docker image serves these files with nginx and proxies API paths to the backend container.
