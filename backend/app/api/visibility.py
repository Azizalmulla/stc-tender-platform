"""
Public vs admin tender visibility (quality gating).

Customer / public reads must only ever see `clean` tenders. Internal/admin
callers (authenticated with ADMIN_TOKEN, or CRON_SECRET as a fallback) can widen
the view with a `?view=` toggle: clean | needs_review | failed | all.

Mechanics: `get_visibility` is attached as a router-level dependency on the
PUBLIC routers in main.py. It records the allowed status set in a contextvar for
the duration of the request; a `do_orm_execute` event in app.db.session reads
that contextvar and transparently adds `extraction_quality_status IN (...)` to
every ORM SELECT that touches the Tender entity (lists, detail, stats, search,
vector-join RAG, exports — all at once).

Routers WITHOUT this dependency (cron/admin) and any code path using SessionLocal
outside a request (scrape, reprocess, scripts, background jobs) never set the
contextvar, so they are unaffected and continue to see every row.
"""
from __future__ import annotations

import contextvars
from typing import Optional, Set, Tuple
from urllib.parse import parse_qs

from fastapi import Header, Query

from app.core.config import settings

PUBLIC_STATUS = "clean"
KNOWN_STATUSES = {"clean", "needs_review", "failed"}

# None  -> no filter (admin "all" / internal paths)
# set() -> restrict extraction_quality_status to these values
_statuses_ctx: contextvars.ContextVar[Optional[Set[str]]] = contextvars.ContextVar(
    "tender_visibility_statuses", default=None
)


def current_statuses() -> Optional[Set[str]]:
    """Allowed statuses for the current request, or None for 'no filter'."""
    return _statuses_ctx.get()


class Visibility:
    def __init__(self, is_admin: bool, statuses: Optional[Set[str]]):
        self.is_admin = is_admin
        self.statuses = statuses  # None == all

    @property
    def view(self) -> str:
        if self.statuses is None:
            return "all"
        return ",".join(sorted(self.statuses))


def _admin_token() -> Optional[str]:
    return getattr(settings, "ADMIN_TOKEN", None) or getattr(settings, "CRON_SECRET", None)


def _supplied_token(authorization: Optional[str], x_admin_token: Optional[str]) -> Optional[str]:
    if x_admin_token:
        return x_admin_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def resolve_statuses(
    view: Optional[str], authorization: Optional[str], x_admin_token: Optional[str]
) -> Tuple[Optional[Set[str]], bool]:
    """(statuses, is_admin). statuses None => no filter (admin 'all')."""
    admin_token = _admin_token()
    supplied = _supplied_token(authorization, x_admin_token)
    is_admin = bool(admin_token and supplied and supplied == admin_token)

    if not is_admin:
        return {PUBLIC_STATUS}, False
    v = (view or "all").strip().lower()
    if v in ("all", ""):
        return None, True
    chosen = {s.strip() for s in v.split(",") if s.strip() in KNOWN_STATUSES}
    return (chosen or {PUBLIC_STATUS}), True


def get_visibility(
    view: str = Query(
        "all",
        description="Admin-only status toggle: clean | needs_review | failed | all. "
        "Ignored for non-admin callers, who always see `clean` only.",
    ),
    authorization: Optional[str] = Header(None),
    x_admin_token: Optional[str] = Header(None),
) -> Visibility:
    statuses, is_admin = resolve_statuses(view, authorization, x_admin_token)
    return Visibility(is_admin, statuses)


class VisibilityMiddleware:
    """Pure-ASGI middleware: records the request's allowed tender statuses in a
    contextvar so the do_orm_execute event in app.db.session can transparently
    gate every Tender SELECT. Pure ASGI (not BaseHTTPMiddleware) so the contextvar
    propagates into the endpoint and its threadpool DB query.

    Default = public => clean only. A valid ADMIN_TOKEN / CRON_SECRET (Bearer or
    X-Admin-Token) unlocks the full set (or a ?view= subset). Admin/cron endpoints
    already authenticate with that token, so they remain unfiltered.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}
        qs = parse_qs(scope.get("query_string", b"").decode("latin1"))
        view = qs.get("view", [None])[0]
        statuses, _ = resolve_statuses(view, headers.get("authorization"), headers.get("x-admin-token"))

        token = _statuses_ctx.set(statuses)
        try:
            await self.app(scope, receive, send)
        finally:
            _statuses_ctx.reset(token)
