"""Offline tombstone for the removed Nous Portal billing client.

The Portal billing endpoints (charges, subscription preview/change, pending
changes) were removed with the Nous integration. Every network operation in
this module now raises :class:`BillingError` so the billing/subscription TUI
screens degrade to their existing fail-open handling.

The typed-exception hierarchy and the HTTP→exception mapping
(:func:`_raise_for_error`) are preserved verbatim because the gateway/TUI
serialization layers (still in the tree) catch and render these exceptions.
No network calls are made from this module.
"""

from __future__ import annotations

import os
import urllib.parse
from typing import Any, Optional

DEFAULT_PORTAL_BASE_URL = "https://portal.nousresearch.com"


# =============================================================================
# Typed errors
# =============================================================================


class BillingError(Exception):
    """A billing HTTP call failed.

    Carries everything a surface needs to render the right message + affordance:
    the server ``error`` code, HTTP ``status``, an optional human ``message``, the
    ``portalUrl`` deep-link (present on every gate denial), and ``retry_after``
    seconds (429/503). ``payload`` is the full parsed JSON body when available.
    """

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        error: Optional[str] = None,
        portal_url: Optional[str] = None,
        retry_after: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
        actor: Optional[str] = None,
        code: Optional[str] = None,
        recovery: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error = error
        self.portal_url = portal_url
        self.retry_after = retry_after
        self.payload = payload or {}
        self.actor = actor
        self.code = code
        self.recovery = recovery


class BillingScopeRequired(BillingError):
    """``403 insufficient_scope`` — the held token lacks ``billing:manage``."""


class BillingAuthError(BillingError):
    """``401`` — missing/invalid bearer token (not logged in / expired)."""


class BillingRemoteSpendingRevoked(BillingError):
    """``403 remote_spending_revoked`` — this terminal's spending was revoked."""


class BillingSessionRevoked(BillingAuthError):
    """``401 session_revoked`` — the whole session was logged out."""


class BillingTransient(BillingError):
    """A deterministic non-charge outcome — safe to retry after backoff."""


class BillingRateLimited(BillingTransient):
    """``429 rate_limited`` or ``503 temporarily_unavailable``. NOT a payment
    failure. Carries ``retry_after`` (seconds)."""


class BillingStripeUnavailable(BillingTransient):
    """``503 stripe_unavailable`` — Stripe itself is down (not rate limiting)."""


class BillingUpgradeCapExceeded(BillingTransient):
    """``429 upgrade_cap_exceeded`` — the org hit its plan-change cap."""


# =============================================================================
# Base-URL resolution (offline)
# =============================================================================


def resolve_portal_base_url(state: Optional[dict[str, Any]] = None) -> str:
    """Resolve the portal base URL: env override → stored state → default."""
    env = os.getenv("HERMES_PORTAL_BASE_URL") or os.getenv("NOUS_PORTAL_BASE_URL")
    if env and env.strip():
        return env.strip().rstrip("/")
    if state:
        stored = state.get("portal_base_url")
        if isinstance(stored, str) and stored.strip():
            return stored.strip().rstrip("/")
    return DEFAULT_PORTAL_BASE_URL


def _absolutize_portal_url(portal_url: Optional[str]) -> Optional[str]:
    """Resolve a (possibly relative) server portalUrl to an absolute URL."""
    if not (isinstance(portal_url, str) and portal_url.strip()):
        return portal_url
    base = resolve_portal_base_url()
    return urllib.parse.urljoin(base.rstrip("/") + "/", portal_url)


def _retry_after_seconds(headers: Any) -> Optional[int]:
    """Parse a ``Retry-After`` header (integer seconds) — None if absent/bad."""
    from agent.retry_utils import parse_retry_after_seconds

    seconds = parse_retry_after_seconds(headers)
    return None if seconds is None else int(seconds)


def _raise_for_error(
    status: int, payload: dict[str, Any], headers: Any = None
) -> None:
    """Map an HTTP error response to the right typed :class:`BillingError`."""
    error = payload.get("error") if isinstance(payload, dict) else None
    message = payload.get("message") if isinstance(payload, dict) else None
    code = payload.get("code") if isinstance(payload, dict) else None
    actor = payload.get("actor") if isinstance(payload, dict) else None
    recovery = payload.get("recovery") if isinstance(payload, dict) else None
    portal_url = _absolutize_portal_url(
        payload.get("portalUrl") if isinstance(payload, dict) else None
    )
    retry_after = _retry_after_seconds(headers)

    common = {
        "status": status,
        "error": error,
        "portal_url": portal_url,
        "retry_after": retry_after,
        "payload": payload if isinstance(payload, dict) else None,
        "actor": actor,
        "code": code,
        "recovery": recovery,
    }

    if error == "stripe_unavailable":
        raise BillingStripeUnavailable(
            message or "Stripe is temporarily unavailable — try again shortly.",
            **common,
        )
    if error == "upgrade_cap_exceeded":
        raise BillingUpgradeCapExceeded(
            message or "Daily plan-change limit reached — try again tomorrow.",
            **common,
        )

    if status == 401:
        if error == "session_revoked":
            raise BillingSessionRevoked(
                message or "Your session was logged out — log in again.", **common
            )
        raise BillingAuthError(message or "Authentication required.", **common)
    if status == 403:
        if error == "remote_spending_revoked":
            raise BillingRemoteSpendingRevoked(
                message or "Remote spending was stopped for this terminal.",
                **common,
            )
        if error == "insufficient_scope":
            raise BillingScopeRequired(
                message or "This action needs the billing:manage scope.", **common
            )
        raise BillingError(message or error or "Billing request denied.", **common)
    if status in (429, 503):
        raise BillingRateLimited(
            message or "Rate limited — try again shortly.", **common
        )
    raise BillingError(message or error or f"Billing request failed ({status}).", **common)


# =============================================================================
# Removed Portal operations — every call raises
# =============================================================================


def _removed(name: str):
    def _call(*_args: Any, **_kwargs: Any) -> Any:
        raise BillingError(f"{name}: Nous Portal billing was removed in this build.")

    return _call


get_billing_state = _removed("get_billing_state")
get_subscription_state = _removed("get_subscription_state")
post_subscription_preview = _removed("post_subscription_preview")
post_subscription_change = _removed("post_subscription_change")
post_subscription_upgrade = _removed("post_subscription_upgrade")
post_charge = _removed("post_charge")
put_subscription_pending_change = _removed("put_subscription_pending_change")
delete_subscription_pending_change = _removed("delete_subscription_pending_change")
step_up_nous_billing_scope = _removed("step_up_nous_billing_scope")
