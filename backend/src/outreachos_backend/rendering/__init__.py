"""Video rendering: FFmpeg orchestration, overlay assets, and the job queue.

Shared infrastructure, not Video Composer's property. Future modules reuse the
queue for scraping, enrichment, and AI work.

Empty in P0 — P1 builds this entire package headless, driven from a CLI, with
zero UI. Nothing in the frontend may depend on it before its golden-frame suite
passes.

- ``ffmpeg.py``          binary resolution (never from PATH) + process wrapper
- ``probe.py``           FFprobe: duration, dimensions, fps, codec, audio presence
- ``overlay_builder.py`` Pillow mask / border / shadow / background / padding PNGs
- ``pipeline.py``        filtergraph assembly from an ordered list of steps
- ``steps/``             composite step objects, each contributing graph nodes
- ``queue/``             worker pool and job state machine

Python orchestrates FFmpeg; it does not replace it. No ``ffmpeg-python``, no
``moviepy`` — commands are constructed explicitly so they stay readable,
debuggable, and copy-pasteable into a terminal.
"""
