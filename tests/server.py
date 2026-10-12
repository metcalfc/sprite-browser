"""Run the demo app on a free port in a background thread, for tests."""

from __future__ import annotations

import os
import socket
import threading
import time

import requests
import uvicorn


class LiveServer:
    def __init__(self, inbox_token: str | None = "test-token") -> None:
        if inbox_token:
            os.environ["DEMO_INBOX_TOKEN"] = inbox_token
        else:
            os.environ.pop("DEMO_INBOX_TOKEN", None)
        os.environ.pop("FLY_REGION", None)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(
            "storefront.app:app", host="127.0.0.1", port=self.port, log_level="warning"
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> LiveServer:
        self.thread.start()
        for _ in range(100):
            try:
                requests.get(f"{self.url}/healthz", timeout=1)
                return self
            except requests.ConnectionError:
                time.sleep(0.05)
        raise RuntimeError("test server did not start")

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5)
