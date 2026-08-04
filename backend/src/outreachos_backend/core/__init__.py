"""Shared backend infrastructure.

Database session, event bus, settings, workspace paths, logging, and (from P4)
the job queue. Every module reuses these; none of them may import a module.

Arrives across checkpoints 3-5:

- ``config``      CLI args and pydantic-settings, with args winning over env
- ``logging``     dictConfig; uvicorn's loggers re-parented into the same file
- ``paths``       workspace layout, frozen-build resource resolution
- ``db``          engine, sessionmaker, and the request-scoped session dependency
- ``boot``        the ``BootReport`` that ``/health`` and diagnostics both read
- ``events``      the SSE event bus and its replay ring buffer
"""
