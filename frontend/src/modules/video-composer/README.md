# `modules/video-composer/`

Generates personalized outreach videos in batches by overlaying one reusable
talking-head video onto many website screen recordings.

Empty until P2 — P0 builds only the shell that will host it, and P1 is a headless
render engine with no UI at all.

| Directory     | Owns                                                              |
| ------------- | ----------------------------------------------------------------- |
| `routes/`     | Route components: Campaigns, Campaign detail, Render Queue        |
| `components/` | Module-specific UI, composed from `core/ui` and shadcn primitives |
| `hooks/`      | Module-specific React hooks                                       |
| `api/`        | TanStack Query hooks over the generated client in `core/api`      |
| `state/`      | Zustand stores for ephemeral editor interaction state only        |
