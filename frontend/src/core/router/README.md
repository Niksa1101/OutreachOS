# `core/router/`

TanStack Router tree assembly, code-based rather than file-based.

Code-based is deliberate: modules contribute their own routes through the
registry, and file-based routing would fight that by deriving the tree from disk
layout instead.

The root `beforeLoad` guard owns two redirects — no workspace goes to `/setup`,
an unhealthy backend goes to `/diagnostics`. Both are real routes outside the
shell layout, so neither can inherit a layout that assumes a live backend.
