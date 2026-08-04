# `core/`

Shared infrastructure. Everything here is module-agnostic and may be imported by
any module.

`core/` must never import from `modules/` — that inverts the dependency and is
blocked by the `boundaries/element-types` rule in `eslint.config.js`. When two
modules need the same behaviour, it moves here rather than being imported across.

| Directory   | Owns                                                                       |
| ----------- | -------------------------------------------------------------------------- |
| `api/`      | Typed fetch wrapper, auth token custody, generated OpenAPI types           |
| `sse/`      | The single SSE connection and its event dispatch into TanStack Query       |
| `ui/`       | Custom components, composed from shadcn primitives, styled only via tokens |
| `tokens/`   | Design tokens — the sole source of every visual value                      |
| `layout/`   | App shell, boot gate, sidebar frame                                        |
| `router/`   | Route tree assembly and the root boot guard                                |
| `registry/` | Module registry — each module contributes nav entries and routes here      |
