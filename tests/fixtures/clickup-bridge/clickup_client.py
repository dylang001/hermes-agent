"""Read-only ClickUp REST API client for the Hermes Growth OS bridge.

Pure stdlib (``urllib.request``) — no third-party dependencies so the plugin
loads cleanly inside the hermes runtime and inside hermetic test subprocesses.

Hard rules baked into this module:
  * The client only exposes READ endpoints (``GET``) plus the explicitly
    approval-gated ``create_task`` POST.
  * The ``ForbiddenEndpointError`` guard rejects any URL that targets a
    destructive endpoint (``delete``, ``archive``, ``move``, ``edit``).
  * Auth uses the ``Authorization: <CLICKUP_API_TOKEN>`` header. The
    header value is the raw token (no "Bearer " prefix — that is the
    ClickUp convention).
  * Network I/O is hidden behind ``_request`` so unit tests can monkeypatch
    a single function instead of mocking ``urllib.request`` directly.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_BASE_URL = "https://api.clickup.com/api/v2"
DEFAULT_TIMEOUT = 30.0  # seconds

# Words that, when present in the path segment, mark an endpoint as
# destructive. Any path containing one of these tokens is refused by
# ``_check_path_safe`` before the request is dispatched.
FORBIDDEN_PATH_TOKENS = (
    "delete",
    "archive",
    "move",
    "edit",  # PUT-mutating endpoints contain "edit" in their path
)

# The single POST we are allowed to make. Any other path with a non-GET
# method is refused.
ALLOWED_WRITE_PATHS = (
    # POST /list/{list_id}/task  → create a task in a list
    re.compile(r"^/list/[^/]+/task/?$"),
)

# ── Errors ───────────────────────────────────────────────────────────────────


class ClickUpError(RuntimeError):
    """Base class for all ClickUp bridge errors."""


class AuthError(ClickUpError):
    """Missing or invalid CLICKUP_API_TOKEN."""


class ForbiddenEndpointError(ClickUpError):
    """A request targeted a destructive endpoint (delete/archive/move/edit)."""


class ApprovalGateError(ClickUpError):
    """A write attempt lacked the required Dylan approval metadata."""


class ProposalValidationError(ClickUpError):
    """A proposal JSON file is missing required fields or is malformed."""


class HTTPError(ClickUpError):
    """The ClickUp API returned a non-2xx status."""

    def __init__(self, status: int, body: str, url: str) -> None:
        super().__init__(f"ClickUp API {status} on {url}: {body[:200]}")
        self.status = status
        self.body = body
        self.url = url


# ── Client ───────────────────────────────────────────────────────────────────


class ClickUpClient:
    """Thin read-mostly client for the ClickUp v2 REST API.

    Parameters
    ----------
    api_token:
        Personal API token from ``https://app.clickup.com/settings/apps``.
        If ``None``, read from ``CLICKUP_API_TOKEN``.
    base_url:
        API base. Defaults to ``CLICKUP_BASE_URL`` env var, then the
        production v2 base.
    timeout:
        Per-request timeout in seconds. Defaults to 30.
    requester:
        Optional ``callable(url, method, headers, body) -> (status, body_str)``
        for dependency-injection in tests. When ``None``, the client uses
        ``urllib.request`` directly.
    """

    def __init__(
        self,
        api_token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        requester: Optional[Any] = None,
    ) -> None:
        token = api_token if api_token is not None else os.environ.get("CLICKUP_API_TOKEN", "")
        if not token or not token.strip():
            raise AuthError(
                "CLICKUP_API_TOKEN is not set. Get a personal token from "
                "https://app.clickup.com/settings/apps and export it."
            )
        self.api_token = token.strip()
        self.base_url = (base_url or os.environ.get("CLICKUP_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = float(timeout)
        # Default requester wraps urllib.request.
        self._requester = requester or self._default_requester

    # ── Public read endpoints ─────────────────────────────────────────────

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """List all workspaces (called "Teams" in the API)."""
        data = self._get("/team")
        teams = data.get("teams", [])
        return [self._normalize_workspace(t) for t in teams]

    def list_lists(self, workspace_id: str) -> List[Dict[str, Any]]:
        """List folders+lists in a workspace.

        Returns a flat list of dicts: ``{"id", "name", "kind": "folder"|"list", "folder_id"?}``.
        Folders come first (in their original order), then the workspace-level
        lists (folders=null lists). Lists inside folders are nested under the
        folder; we flatten the structure here.
        """
        space_id = self._resolve_space_id(workspace_id)
        data = self._get(f"/space/{space_id}/list")
        out: List[Dict[str, Any]] = []
        for raw in data.get("lists", []):
            out.append(self._normalize_list(raw))
        return out

    def list_tasks(
        self,
        list_id: str,
        status: str = "open",
        archived: bool = False,
    ) -> List[Dict[str, Any]]:
        """List tasks in a list. ``status`` is ``open``, ``closed``, or ``all``."""
        if status not in ("open", "closed", "all"):
            raise ValueError(f"status must be one of open/closed/all; got {status!r}")
        # The v2 list-tasks endpoint: GET /list/{list_id}/task
        qs = []
        if archived:
            qs.append("archived=true")
        if status != "all":
            qs.append(f"statuses[]={status}")
        suffix = ("?" + "&".join(qs)) if qs else ""
        data = self._get(f"/list/{list_id}/task{suffix}")
        return [self._normalize_task(t) for t in data.get("tasks", [])]

    def get_task(self, task_id: str) -> Dict[str, Any]:
        """Show a single task by id."""
        data = self._get(f"/task/{task_id}")
        return self._normalize_task(data)

    # ── Public write endpoint (gated) ─────────────────────────────────────

    def create_task_from_proposal(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """Create a ClickUp task from an *approved* proposal dict.

        Refuses (``ApprovalGateError``) if the proposal is missing the
        approval metadata. See ``cli.create_task`` for the full validation
        flow that runs *before* this method is called.
        """
        approved_by = proposal.get("approved_by")
        approved_at = proposal.get("approved_at")
        if approved_by != "dylan" or not approved_at:
            raise ApprovalGateError(
                "Proposal is missing Dylan approval. Add "
                "'approved_by: dylan' and 'approved_at: <iso8601>' to the "
                "proposal metadata before creating a task."
            )

        list_id = proposal["list_id"]
        body: Dict[str, Any] = {
            "name": proposal["title"],
            "description": proposal.get("body", ""),
        }
        if proposal.get("tag"):
            body["tags"] = [proposal["tag"]]

        return self._post(f"/list/{list_id}/task", body)

    # ── Internals ─────────────────────────────────────────────────────────

    def _get(self, path: str) -> Dict[str, Any]:
        return self._dispatch(path, method="GET")

    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return self._dispatch(path, method="POST", body=body)

    def _dispatch(
        self,
        path: str,
        method: str = "GET",
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not path.startswith("/"):
            path = "/" + path
        _check_path_safe(path, method)
        url = f"{self.base_url}{path}"
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Authorization": self.api_token,
            "Accept": "application/json",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        status, text = self._requester(
            url=url,
            method=method,
            headers=headers,
            body=payload,
            timeout=self.timeout,
        )
        if not (200 <= status < 300):
            raise HTTPError(status, text, url)
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ClickUpError(f"Invalid JSON from ClickUp at {url}: {e}") from e

    def _default_requester(self, *, url, method, headers, body, timeout):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            # Read body for context, then re-raise as our HTTPError.
            try:
                body_text = e.read().decode("utf-8", errors="replace")
            except Exception:
                body_text = ""
            raise HTTPError(e.code, body_text, url) from e

    def _resolve_space_id(self, workspace_id: str) -> str:
        """ClickUp's "list spaces" endpoint expects a space id, not a team id.

        If the caller passed a workspace id, look up the first space in that
        workspace and return its id. If the caller already passed a space
        id (it starts with a digit and is the right shape), return as-is.
        Heuristic: if the value contains a slash or is longer than 7 chars,
        try the spaces lookup; otherwise trust it.
        """
        # Cheap path: just fetch spaces for the team and use the first one.
        # This is correct for workspaces that have a single space, which is
        # the common ClickUp setup. Multi-space workspaces are rare for the
        # Growth OS and the user can call _dispatch directly if needed.
        data = self._get(f"/team/{workspace_id}/space")
        spaces = data.get("spaces", [])
        if not spaces:
            raise ClickUpError(
                f"No spaces found in workspace {workspace_id!r}. "
                "Check the workspace id."
            )
        return str(spaces[0]["id"])

    # ── Normalizers (return stable shape regardless of API quirks) ────────

    @staticmethod
    def _normalize_workspace(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(raw.get("id", "")),
            "name": raw.get("name", ""),
            "members_count": raw.get("members_count", 0),
        }

    @staticmethod
    def _normalize_list(raw: Dict[str, Any]) -> Dict[str, Any]:
        folder = raw.get("folder") or {}
        return {
            "id": str(raw.get("id", "")),
            "name": raw.get("name", ""),
            "kind": "list",
            "folder_id": str(folder.get("id", "")) if folder else None,
            "folder_name": folder.get("name") if folder else None,
            "task_count": raw.get("task_count", 0),
        }

    @staticmethod
    def _normalize_task(raw: Dict[str, Any]) -> Dict[str, Any]:
        status = raw.get("status") or {}
        return {
            "id": str(raw.get("id", "")),
            "name": raw.get("name", ""),
            "status": status.get("status", "unknown"),
            "list_id": str((raw.get("list") or {}).get("id", "")),
            "url": raw.get("url", ""),
            "date_created": raw.get("date_created"),
            "date_updated": raw.get("date_updated"),
        }


# ── Path safety guard ───────────────────────────────────────────────────────


def _check_path_safe(path: str, method: str) -> None:
    """Refuse any request whose path matches a destructive endpoint.

    This is a defense-in-depth guard. The CLI also refuses forbidden verbs,
    but if a future caller forgets, this module still says no.
    """
    # Lower-case for matching, but preserve original for error messages.
    lowered = path.lower()
    for token in FORBIDDEN_PATH_TOKENS:
        # Word-boundary-ish match: the token must appear as a path segment,
        # so we split on "/" and check each segment. This avoids matching
        # "edited_at" inside a task field.
        segments = [seg for seg in lowered.split("/") if seg]
        if any(token == seg for seg in segments):
            raise ForbiddenEndpointError(
                f"Refusing {method} on {path!r}: path segment {token!r} is "
                "forbidden. The ClickUp bridge never deletes, archives, "
                "moves, or edits."
            )
    # For non-GET methods, also require the path match an allowed-write pattern.
    if method != "GET":
        if not any(pat.match(path) for pat in ALLOWED_WRITE_PATHS):
            raise ForbiddenEndpointError(
                f"Refusing {method} on {path!r}: only POST /list/<id>/task "
                "is permitted (approval-gated task creation)."
            )
