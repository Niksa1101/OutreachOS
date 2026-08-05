"""Video rendering: FFmpeg orchestration, overlay assets, and the job queue.

P1 implements the headless CLI engine in this package. See ``rendering/cli.py``.
"""

from outreachos_backend.rendering.cli import main as render_main

__all__ = ["render_main"]
