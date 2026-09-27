"""Logging setup. One call, from an entry point; modules just getLogger."""
from __future__ import annotations

import logging
import os
import sys

# Fixed short name so the HTTP switch is easy to type:
#   logging.getLogger("checkerduck.http").setLevel(logging.DEBUG)
HTTP_LOGGER = "checkerduck.http"


def setup(level: int = logging.INFO, http_debug: bool | None = None) -> None:
    """Configure the root logger. Safe to call again; the last call wins.

    stdout, not stderr, so notebooks don't paint every line as an error.
    force=True matters: basicConfig is a silent no-op once root has handlers,
    which is already true under Deepnote/IPython and under uvicorn.
    """
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    # basicConfig(force=True) replaces root's handlers but cannot undo
    # logging.config.fileConfig's disable_existing_loggers, so setup() works
    # regardless of whether something already configured logging.
    for existing in logging.Logger.manager.loggerDict.values():
        if isinstance(existing, logging.Logger):
            existing.disabled = False
    if http_debug is None:
        http_debug = bool(os.environ.get("CHECKERDUCK_HTTP_DEBUG"))
    if http_debug:
        # Raw request/response bodies, plus urllib3's own retry accounting.
        logging.getLogger(HTTP_LOGGER).setLevel(logging.DEBUG)
        logging.getLogger("urllib3.util.retry").setLevel(logging.DEBUG)
