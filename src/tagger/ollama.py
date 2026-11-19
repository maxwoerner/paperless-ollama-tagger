"""Ollama client using structured output."""
import json
import re

import httpx


class OllamaUnavailable(Exception):
    pass


class OllamaTimeout(Exception):
    pass


class OllamaBadOutput(Exception):
    pass


def version_at_least(v: str, minimum: tuple[int, int, int]) -> bool:
    nums = [int(x) for x in re.findall(r"\d+", v.split("-")[0].split("+")[0])][:3]
    nums += [0] * (3 - len(nums))
    return tuple(nums) >= minimum


class OllamaClient:
    def __init__(self, base_url: str, model: str, num_ctx: int, timeout: float):
        self._model = model
        self._num_ctx = num_ctx
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def version(self) -> str:
        try:
            r = self._http.get("/api/version")
            r.raise_for_status()
            return str(r.json()["version"])
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise OllamaUnavailable(f"cannot read Ollama version: {e}") from e

    def _chat_once(self, messages: list[dict], schema: dict) -> str:
        try:
            r = self._http.post(
                "/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "format": schema,
                    "stream": False,
                    "options": {"num_ctx": self._num_ctx, "temperature": 0},
                },
            )
        except httpx.ReadTimeout as e:
            raise OllamaTimeout(str(e)) from e
        except httpx.HTTPError as e:
            raise OllamaUnavailable(str(e)) from e
        if r.status_code >= 400:
            # 5xx, and 4xx such as 404 "model not found": a server/config problem,
            # not this document's fault. Abort the run rather than mark documents.
            raise OllamaUnavailable(f"HTTP {r.status_code}: {r.text[:200]}")
        try:
            return r.json()["message"]["content"]
        except (KeyError, ValueError, TypeError) as e:
            raise OllamaBadOutput(f"unexpected response shape: {e}") from e

    def chat_json(self, messages: list[dict], schema: dict) -> dict:
        last: Exception | None = None
        for _ in range(2):
            content = self._chat_once(messages, schema)
            try:
                data = json.loads(content)
            except (ValueError, TypeError) as e:
                last = e
                continue
            if isinstance(data, dict):
                return data
            last = ValueError("answer is not a JSON object")
        raise OllamaBadOutput(str(last))
