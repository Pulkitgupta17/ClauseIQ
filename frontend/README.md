# ClauseIQ Frontend

React single-page app that drives the ClauseIQ contract analyzer with a live,
streaming, multi-agent UX.

## Stack

- **Vite + React 18 + TypeScript** (strict, `noUncheckedIndexedAccess`, zero `any`)
- **Tailwind v4** (CSS-first tokens) + **shadcn/ui** (Radix primitives), dark default via `next-themes`
- **TanStack Query** (mutations), **Zustand** (analysis state), **Zod** (runtime validation of every API/SSE payload)
- **Framer Motion** (animations, `prefers-reduced-motion` aware via `MotionConfig reducedMotion="user"`)
- **Biome** (lint + format), **Vitest** + Testing Library

## Run

```bash
pnpm install
pnpm dev        # http://localhost:5173 (expects the backend on :8000)
```

Point at a different backend with `VITE_API_URL` (e.g. `VITE_API_URL=http://localhost:8000 pnpm dev`).

Scripts: `pnpm build` (type-check + bundle), `pnpm preview`, `pnpm test`, `pnpm biome`.

## How it works

1. **`/`** — `ContractUploader` takes a pasted contract or a PDF. PDF text is
   extracted **in the browser** with a lazy-loaded `pdfjs` (the backend's analyze
   endpoint takes text, so no upload endpoint is needed). The request is
   Zod-validated, stashed in the Zustand store, and the app routes to `/analysis/:id`.
2. **`/analysis/:id`** — `useStreamingAgents` opens an SSE stream and feeds each
   event into the store. Because the stream is a **POST** (the contract is the
   body) and `EventSource` is GET-only, the stream is consumed via `fetch` +
   `ReadableStream` and parsed frame-by-frame (`lib/sse.ts`). The `AgentTrace`
   shows each agent completing live; results animate in as `ClauseCard`s with a
   `RiskGauge` and citation dialogs.
3. **`/about`** — explainer + MCP install link.

## Notable decisions

- **Zod mirrors the backend Pydantic models** (`lib/schemas.ts`) and validates
  every response/SSE frame, so a backend contract change surfaces as a typed
  failure rather than a silent `undefined`.
- **Client-side PDF extraction** keeps the backend (frozen after M2) unchanged.
- **Routes are code-split** and `pdfjs` is lazy — initial JS is ~84 kB gzip,
  which keeps Lighthouse Performance at 100.
- **Citations open a dialog with the full statutory text** (already carried on
  each citation), reinforcing the "grounded, not guessed" guarantee in the UI.

## Tests

`pnpm test` covers the Zod schemas, the SSE frame parser, the severity mapping,
the analysis store's event→step state machine, and the `useAnalyzeContract`
mutation.
