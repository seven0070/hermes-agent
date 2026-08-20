"""Offline tombstone for the removed Nous Portal account helpers.

The Portal account/entitlement API was removed with the Nous integration.
The dataclasses below are preserved (byte-compatible shapes) because the
billing/subscription/credits view modules and gateway serialization code
still type against them; every network operation in this module returns a
logged-out / empty result. No network calls are made from this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional

NousAccountInfoSource = Literal["jwt", "account_api", "inference_key", "none", "error"]

# Free tool-pool coverage categories (kept for shape compatibility).
TOOL_COVERAGE_CATEGORIES = (
    "firecrawl",
    "fal",
    "fal-video",
    "openai-audio",
    "browser-use",
    "modal",
)


@dataclass(frozen=True)
class NousPortalSubscriptionInfo:
    plan: Optional[str] = None
    tier: Optional[int] = None
    monthly_charge: Optional[float] = None
    monthly_credits: Optional[float] = None
    current_period_end: Optional[str] = None
    credits_remaining: Optional[float] = None
    rollover_credits: Optional[float] = None


@dataclass(frozen=True)
class NousPaidServiceAccessInfo:
    allowed: Optional[bool] = None
    paid_access: Optional[bool] = None
    reason: Optional[str] = None
    organisation_id: Optional[str] = None
    effective_at_ms: Optional[int] = None
    has_active_subscription: Optional[bool] = None
    active_subscription_is_paid: Optional[bool] = None
    subscription_tier: Optional[int] = None
    subscription_monthly_charge: Optional[float] = None
    subscription_credits_remaining: Optional[float] = None
    purchased_credits_remaining: Optional[float] = None
    total_usable_credits: Optional[float] = None
    member_spend_cap_exceeded: Optional[bool] = None
    member_spend_cap_usd: Optional[float] = None
    member_spend_usd: Optional[float] = None
    member_spend_cap_remaining_usd: Optional[float] = None


@dataclass(frozen=True)
class NousToolAccessInfo:
    """Free tool-pool entitlement, decoupled from paid/billing access."""

    enabled: bool = False
    coverage: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class NousPortalAccountInfo:
    logged_in: bool
    source: NousAccountInfoSource
    fresh: bool
    user_id: Optional[str] = None
    org_id: Optional[str] = None
    org_slug: Optional[str] = None
    org_name: Optional[str] = None
    client_id: Optional[str] = None
    product_id: Optional[str] = None
    nous_client: Optional[str] = None
    portal_base_url: Optional[str] = None
    inference_base_url: Optional[str] = None
    inference_credential_present: bool = False
    credential_source: Optional[str] = None
    expires_at: Optional[datetime] = None
    email: Optional[str] = None
    privy_did: Optional[str] = None
    subscription: Optional[NousPortalSubscriptionInfo] = None
    paid_service_access: Optional[bool] = None
    paid_service_access_info: Optional[NousPaidServiceAccessInfo] = None
    tool_access: Optional[NousToolAccessInfo] = None
    raw_claims: Optional[dict[str, Any]] = None
    raw_account: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def is_paid(self) -> bool:
        return self.paid_service_access is True


def _logged_out() -> NousPortalAccountInfo:
    return NousPortalAccountInfo(logged_in=False, source="none", fresh=True)


def get_nous_portal_account_info(*_args: Any, **_kwargs: Any) -> NousPortalAccountInfo:
    """Nous Portal removed — always reports logged out."""
    return _logged_out()


def format_nous_portal_entitlement_message(*_args: Any, **_kwargs: Any) -> str:
    """Nous Portal removed — no entitlement guidance to render."""
    return ""


def nous_portal_billing_url(account_info: Optional[NousPortalAccountInfo] = None) -> str:
    """Return the billing URL for a (test-provided) account snapshot."""
    try:
        from hermes_cli.nous_billing import DEFAULT_PORTAL_BASE_URL
    except Exception:
        DEFAULT_PORTAL_BASE_URL = "https://portal.nousresearch.com"

    base = None
    if account_info is not None:
        base = account_info.portal_base_url
    if not isinstance(base, str) or not base.strip():
        base = DEFAULT_PORTAL_BASE_URL
    return f"{base.rstrip('/')}/billing"


def nous_portal_topup_url(account_info: Optional[NousPortalAccountInfo] = None) -> str:
    """Return the portal top-up URL that auto-opens the top-up modal."""
    base_billing = nous_portal_billing_url(account_info)  # {base}/billing
    base = base_billing[: -len("/billing")]  # strip the trailing /billing

    slug = getattr(account_info, "org_slug", None) if account_info is not None else None
    if isinstance(slug, str) and slug.strip():
        from urllib.parse import quote

        return f"{base}/orgs/{quote(slug.strip(), safe='')}/billing?topup=open"
    return f"{base}/billing?topup=open"
