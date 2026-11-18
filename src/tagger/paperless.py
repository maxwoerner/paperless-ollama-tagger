"""Thin Paperless-ngx REST client."""
import math
from collections.abc import Iterator

import httpx

from tagger.vocab import CustomField, Vocabulary

PAGE_SIZE = 100
DOC_PAGE_SIZE = 25


class PaperlessError(Exception):
    pass


class PaperlessClient:
    def __init__(self, base_url: str, token: str, timeout: float):
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={
                "Authorization": f"Token {token}",
                "Accept": "application/json; version=7",
            },
        )

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, url: str, **kw) -> httpx.Response:
        try:
            r = self._http.request(method, url, **kw)
        except httpx.HTTPError as e:
            raise PaperlessError(f"{method} {url}: {e}") from e
        if r.status_code >= 500:
            raise PaperlessError(f"{method} {url}: HTTP {r.status_code}")
        return r

    def _ok(self, method: str, url: str, **kw) -> httpx.Response:
        r = self._request(method, url, **kw)
        if r.status_code >= 400:
            raise PaperlessError(f"{method} {url}: HTTP {r.status_code} {r.text[:200]}")
        return r

    def version(self) -> str:
        v = self._ok("GET", "/api/").headers.get("X-Version")
        if not v:
            raise PaperlessError("Paperless did not send an X-Version header")
        return v

    def own_user_id(self) -> int:
        return int(self._ok("GET", "/api/ui_settings/").json()["user"]["id"])

    def _all(self, path: str) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            data = self._ok("GET", path, params={"page": page, "page_size": PAGE_SIZE}).json()
            out.extend(data["results"])
            if not data.get("next"):
                return out
            page += 1

    def load_vocabulary(self) -> Vocabulary:
        fields = [
            CustomField(
                id=f["id"],
                name=f["name"],
                data_type=f["data_type"],
                select_options=list((f.get("extra_data") or {}).get("select_options") or []),
            )
            for f in self._all("/api/custom_fields/")
        ]
        names = lambda path: {x["name"]: x["id"] for x in self._all(path)}  # noqa: E731
        return Vocabulary(
            tags=names("/api/tags/"),
            correspondents=names("/api/correspondents/"),
            document_types=names("/api/document_types/"),
            custom_fields=fields,
        )

    def ensure_tags(self, names: list[str]) -> dict[str, int]:
        existing = {t["name"]: t["id"] for t in self._all("/api/tags/")}
        result: dict[str, int] = {}
        for n in names:
            if n not in existing:
                r = self._ok("POST", "/api/tags/", json={"name": n, "matching_algorithm": 0})
                existing[n] = r.json()["id"]
            result[n] = existing[n]
        return result

    def pending_documents(self, inbox_tag_id: int, error_tag_id: int) -> Iterator[dict]:
        """Yield unprocessed docs. Re-queries instead of following `next`, because
        processed documents leave the filter and would shift the pages."""
        seen: set[int] = set()
        page = 1
        while True:
            data = self._ok(
                "GET",
                "/api/documents/",
                params={
                    "tags__id__all": inbox_tag_id,
                    "tags__id__none": error_tag_id,
                    "ordering": "added",
                    "page_size": DOC_PAGE_SIZE,
                    "page": page,
                },
            ).json()
            fresh = [d for d in data["results"] if d["id"] not in seen]
            if fresh:
                for d in fresh:
                    seen.add(d["id"])
                    yield d
                page = 1
                continue
            # Nothing new on this page (e.g. dry run leaves docs in the queue):
            # look further only if the server says more pages exist.
            if data.get("next") and page < math.ceil(data.get("count", 0) / DOC_PAGE_SIZE):
                page += 1
                continue
            return

    def user_edited(self, doc_id: int, own_user_id: int) -> bool | None:
        r = self._request("GET", f"/api/documents/{doc_id}/history/")
        if r.status_code >= 400:
            return None
        try:
            entries = r.json()
        except ValueError:
            return None
        if not isinstance(entries, list):
            return None
        for e in entries:
            actor = e.get("actor")
            if e.get("action") == "update" and actor is not None and actor.get("id") != own_user_id:
                return True
        return False

    def patch_document(self, doc_id: int, body: dict) -> None:
        self._ok("PATCH", f"/api/documents/{doc_id}/", json=body)
