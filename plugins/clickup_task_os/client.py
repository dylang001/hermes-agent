"""Thin ClickUp REST client used only by the Task OS plugin/CLI.

Not registered as a model tool — agents reach this via `hermes task-os …`
or the cron script, never via core tool schemas.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


class ClickUpAPIError(RuntimeError):
    def __init__(self, status: int, payload: Any, url: str):
        self.status = status
        self.payload = payload
        self.url = url
        super().__init__(f"ClickUp API {status} for {url}: {payload}")


@dataclass(frozen=True)
class ClickUpTask:
    id: str
    name: str
    description: str
    status: str
    tags: tuple[str, ...]
    url: str
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> "ClickUpTask":
        status_obj = raw.get("status") or {}
        status = str(status_obj.get("status") or "")
        tags = tuple(
            str(t.get("name") or "")
            for t in (raw.get("tags") or [])
            if t.get("name")
        )
        return cls(
            id=str(raw.get("id") or ""),
            name=str(raw.get("name") or ""),
            description=str(raw.get("description") or raw.get("text_content") or ""),
            status=status,
            tags=tags,
            url=str(raw.get("url") or ""),
            raw=raw,
        )

    def has_tag(self, name: str) -> bool:
        target = name.casefold()
        return any(t.casefold() == target for t in self.tags)

    def status_matches(self, name: str) -> bool:
        return self.status.casefold() == name.casefold()


class ClickUpClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.clickup.com/api/v2",
        opener=None,
    ):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._opener = opener  # injectable for tests

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            # Support repeated keys via sequence values
            pairs: List[tuple[str, str]] = []
            for key, value in params.items():
                if value is None:
                    continue
                if isinstance(value, (list, tuple)):
                    for item in value:
                        pairs.append((key, str(item)))
                else:
                    pairs.append((key, str(value)))
            url = f"{url}?{urllib.parse.urlencode(pairs)}"

        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            if self._opener is not None:
                with self._opener(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"raw": raw[:500]}
            raise ClickUpAPIError(exc.code, payload, url) from exc

    def get_task(self, task_id: str) -> ClickUpTask:
        data = self._request("GET", f"/task/{task_id}")
        return ClickUpTask.from_api(data)

    def list_tasks(
        self,
        list_id: str,
        *,
        statuses: Optional[Sequence[str]] = None,
        include_closed: bool = False,
        page: int = 0,
    ) -> List[ClickUpTask]:
        params: Dict[str, Any] = {
            "include_closed": str(include_closed).lower(),
            "page": page,
            "subtasks": "false",
        }
        if statuses:
            params["statuses[]"] = list(statuses)
        data = self._request("GET", f"/list/{list_id}/task", params=params)
        return [ClickUpTask.from_api(t) for t in (data.get("tasks") or [])]

    def set_status(self, task_id: str, status: str) -> ClickUpTask:
        data = self._request("PUT", f"/task/{task_id}", body={"status": status})
        return ClickUpTask.from_api(data)

    def add_tag(self, task_id: str, tag: str) -> None:
        self._request("POST", f"/task/{task_id}/tag/{urllib.parse.quote(tag)}")

    def remove_tag(self, task_id: str, tag: str) -> None:
        try:
            self._request("DELETE", f"/task/{task_id}/tag/{urllib.parse.quote(tag)}")
        except ClickUpAPIError as exc:
            # Idempotent: missing tag is fine.
            if exc.status not in (404, 400):
                raise

    def add_comment(self, task_id: str, text: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"/task/{task_id}/comment",
            body={"comment_text": text},
        )

    def ensure_tags(self, task_id: str, tags: Iterable[str]) -> None:
        task = self.get_task(task_id)
        for tag in tags:
            if not task.has_tag(tag):
                self.add_tag(task_id, tag)
                task = ClickUpTask(
                    id=task.id,
                    name=task.name,
                    description=task.description,
                    status=task.status,
                    tags=task.tags + (tag,),
                    url=task.url,
                    raw=task.raw,
                )
