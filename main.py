from __future__ import annotations

import sys

import webview

from backend.app_controller import AppApi, AppController
from backend.logging_setup import setup_logging
from backend.resource_paths import frontend_index, resource_path


def main() -> int:
    logger = setup_logging()
    controller = AppController(logger)
    api = AppApi(controller)
    index = frontend_index()
    if not index.exists():
        logger.error("frontend not found: %s", index)
        return 1

    window = webview.create_window(
        "Voice 1C",
        url=index.as_uri(),
        js_api=api,
        width=1280,
        height=820,
        min_size=(1150, 720),
        background_color="#f6f7fb",
    )
    try:
        window.events.closing += controller.shutdown
    except Exception:
        logger.warning("cannot attach closing event", exc_info=True)

    try:
        webview.start(debug=False)
    finally:
        controller.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
