from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings


class NtfyClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.Client(timeout=20.0)

    def test_connection(self) -> dict[str, Any]:
        if not self.settings.ntfy_topic:
            return {"ok": False, "message": "NTFY_TOPIC is not configured"}
        return self.publish("FreelancerAuto test", "ntfy connection test", tags=["test"])

    def publish(self, title: str, message: str, tags: list[str] | None = None, click: str | None = None) -> dict[str, Any]:
        if not self.settings.ntfy_topic:
            return {"ok": False, "message": "NTFY_TOPIC is not configured"}
        headers = {"Title": title, "Tags": ",".join(tags or ["briefcase"])}
        if self.settings.ntfy_token:
            headers["Authorization"] = f"Bearer {self.settings.ntfy_token}"
        if click:
            headers["Click"] = click
        response = self._client.post(
            f"{self.settings.ntfy_base_url.rstrip('/')}/{self.settings.ntfy_topic}",
            content=message.encode("utf-8"),
            headers=headers,
        )
        response.raise_for_status()
        return {"ok": True, "response": response.json()}

