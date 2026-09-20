"""OpenAPI document: metadata, tag descriptions, and the security model.

Everything here is description, never behavior. The document is assembled from
the live route table, so it cannot drift from what the service actually serves;
what this module adds is the context a route signature cannot carry — how
authentication works, what an error body looks like, which status vocabularies
exist, and which conventions hold across every endpoint.

Two things are done programmatically rather than by editing every route:

* **Security.** Each router would otherwise have to repeat a `security` block.
  Instead, every operation under `/api/admin/` is marked as requiring the
  Administrator session here, because that is exactly the rule `require_admin`
  enforces — one place to read, and it cannot fall out of step route by route.
* **Tag flattening.** Admin routers carry both a generic `admin` tag and a
  specific one (`orders`, `landings`, …). Left alone, a reference renderer shows
  every admin endpoint twice: once in its real group and once in a 54-entry
  `admin` pile. The generic tag is dropped from operations that have a more
  specific one, so navigation has a single obvious home for each endpoint.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

API_TITLE = "Easy Funnel API"

API_SUMMARY = (
    "Cash-on-delivery commerce API for a single merchant: public landing "
    "delivery and checkout, plus the authenticated Administrator surface."
)

# Rendered as the landing section of the published reference.
API_DESCRIPTION = """
Easy Funnel is a single-merchant, cash-on-delivery (COD) commerce platform for
the Colombian market. A buyer arrives on a product landing page — usually from a
paid ad, usually on a phone — reads the offer, and submits an order form. No
payment is taken online: the merchant collects cash when the product is
delivered, which is why so much of this API is about deciding whether an order
is worth dispatching.

This document describes **the API as deployed**. It is generated from the
running route table rather than written by hand, so an endpoint listed here
exists and a parameter shown here is the parameter the service reads.

## The two surfaces

**Public** (`/api/public/*`) is what a buyer's browser talks to. It is
unauthenticated by design: it serves a published landing, records a view or a
call-to-action click, lists delivery locations, and accepts an order. Nothing
here can read or modify the catalog.

**Administrator** (`/api/admin/*`) is the merchant's operational surface:
products, landings and their conversion components, orders, fraud controls,
analytics, and storefront settings. Every one of these requires a session. There
is exactly one role — there is no user management, because the platform is built
for one merchant operating their own store.

## Authentication

`POST /api/auth/login` verifies credentials and replies with a `session` cookie:
`HttpOnly`, `SameSite=Strict`, and `Secure` everywhere except local development.
A browser needs nothing else — send subsequent requests with credentials
included and the cookie authorizes them.

For non-browser clients the same token is accepted as
`Authorization: Bearer <token>`.

Every rejection — missing token, expired, tampered, wrong issuer, wrong audience,
wrong algorithm — returns the **same** generic `401` with
`{"detail": "Authentication required."}`. This is deliberate: a caller learns
that it is not authorized and nothing further.

Login is rate limited per client address. Exceeding it returns `429`; the
credentials themselves are never revealed to be right or wrong in that state.

## Error format

Errors use a single envelope, and the `detail` value has two shapes.

A plain message, for errors that concern the request as a whole:

```json
{ "detail": "Authentication required." }
```

A field error, for a value the caller can correct — this is what validation
failures in business rules return, and it is what lets a client attach the
message to the input that produced it:

```json
{ "detail": { "field": "phone", "message": "Enter a valid Colombian mobile number." } }
```

Schema-level validation performed before a handler runs (a missing body field, a
wrong type) returns FastAPI's standard `422` with a `detail` array instead.

## Conventions

**Money** is Colombian pesos (COP). Amounts are exact decimals and are never
floats in storage; totals that a buyer owes are always computed server-side and
returned ready to display, so a client never adds up a price itself.

**Timestamps** are UTC, ISO-8601. Analytics is the one place that deliberately
does not use UTC: daily figures are bucketed on Colombia's calendar day
(`America/Bogota`), because a merchant reading yesterday's orders means their
yesterday.

**Identifiers** are integers. Image and video assets are addressed by an opaque
random key, never by a filename or anything derived from client input.

**Language.** Buyer-facing copy stored through this API is Spanish, and
delivery locations come from the bundled Colombian DIVIPOLA catalogue, which is
authoritative: a department and municipality must match it exactly, and
`GET /api/public/locations` is the list a client should populate from.

## Order lifecycle

A submitted order is **never silently rejected**. It is persisted exactly once,
in a single transaction together with any fraud flags it raised, and it lands in
one of two states:

| Status | Meaning |
| --- | --- |
| `pending` | Accepted, awaiting the merchant's confirmation. |
| `flagged_fraud` | Accepted and held for review; one or more fraud rules matched. |

Fraud evaluation runs synchronously during submission — duplicate detection,
phone and address blacklists, per-phone and per-IP rate limits, and GeoIP rules.
Rate limiting on the public order endpoint *flags* an order rather than refusing
it, so a real buyer behind a shared connection is reviewed rather than turned
away.

From there the merchant moves the order through a fixed set of transitions:

| From | To |
| --- | --- |
| `pending` | `confirmed`, `cancelled` |
| `confirmed` | `shipped`, `cancelled` |
| `shipped` | `delivered`, `cancelled` |
| `flagged_fraud` | `pending`, `cancelled` |

`delivered` and `cancelled` are terminal. Any other transition is refused.

## Other status vocabularies

* **Products** — `active`, `paused`, `retired`. Only an `active` product's
  landing can be published, and retirement is a soft delete that preserves the
  historical evidence attached to past orders.
* **Landings** — `draft`, `published`. Only a `published` landing is reachable
  through the public API.

## Fulfillment hand-off

When a fulfillment provider is configured, the hand-off runs **after** the order
has been committed locally. Accepting an order never depends on a third party
being reachable; a failed hand-off is recorded as a durable, retryable row that
the merchant can inspect and retry. Endpoints that mention MasterShop are inert
while `FULFILLMENT_PROVIDER` is `none`.

## Scope of this document

Only endpoints backed by a working implementation are published here. An
operational endpoint that currently returns a fixed placeholder is excluded
rather than documented as if it worked.
"""

# Ordered as a reader should meet them: sign in, then the buyer's surface, then
# the merchant's day-to-day, then the supporting controls.
OPENAPI_TAGS: list[dict[str, Any]] = [
    {
        "name": "auth",
        "description": (
            "Administrator sign-in, sign-out, and session introspection. "
            "`GET /api/auth/session` answers `401` when there is no valid "
            "session, which is the normal way for a client to discover that it "
            "needs to authenticate."
        ),
    },
    {
        "name": "public",
        "description": (
            "The buyer's surface: unauthenticated and safe to call from a "
            "browser. Serves a published landing with its banners, conversion "
            "components, offers and fully derived colors; records views and "
            "call-to-action clicks; lists delivery locations; and accepts COD "
            "orders. Everything a landing needs to paint correctly on first "
            "load is computed server-side and included in the response."
        ),
    },
    {
        "name": "products",
        "description": (
            "Catalog management and lifecycle (`active`, `paused`, `retired`), "
            "including per-variant mappings used by fulfillment providers."
        ),
    },
    {
        "name": "landings",
        "description": (
            "Landing pages and everything placed on them: banner upload, "
            "ordering and alternative text, call-to-action placement, colors, "
            "quantity offers, publication state, and the conversion components "
            "(with their videos and per-offer images) positioned between "
            "rendered elements."
        ),
    },
    {
        "name": "landing-templates",
        "description": (
            "Reusable landing configurations. A template captures layout, copy "
            "and components — not images — so it can be applied to another "
            "landing. Templates outlive the landing they were saved from."
        ),
    },
    {
        "name": "orders",
        "description": (
            "Order review and fulfillment: listing and filtering, detail with "
            "fraud flags, CSV export, status transitions, delivery details, and "
            "retrying a failed fulfillment hand-off."
        ),
    },
    {
        "name": "fraud",
        "description": (
            "The controls that decide whether an order is held for review: "
            "duplicate-window and rate-limit configuration, phone and address "
            "blacklists, and GeoIP allow/block rules. Changes take effect on the "
            "next submission without a redeploy."
        ),
    },
    {
        "name": "analytics",
        "description": (
            "Aggregated operational figures: orders per day, per-landing traffic "
            "and conversion, and fraud-flag breakdowns. Daily buckets follow "
            "Colombia's calendar day (`America/Bogota`), not UTC."
        ),
    },
    {
        "name": "store",
        "description": (
            "Storefront identity: branding, contact details, homepage copy, SEO "
            "and tracking identifiers, and brand image uploads. The public "
            "read-only view is what a storefront renders from; the "
            "Administrator view is where the merchant edits it."
        ),
    },
    {
        "name": "ops",
        "description": (
            "Operational read-only endpoints for monitoring: dependency "
            "reachability and the deployed version. These expose state only — "
            "never customer data, credentials, payloads or stack detail."
        ),
    },
]

_SESSION_COOKIE_SCHEME = "sessionCookie"
_BEARER_SCHEME = "bearerAuth"

_SECURITY_SCHEMES: dict[str, Any] = {
    _SESSION_COOKIE_SCHEME: {
        "type": "apiKey",
        "in": "cookie",
        "name": "session",
        "description": (
            "Session cookie issued by `POST /api/auth/login`. `HttpOnly`, "
            "`SameSite=Strict`, and `Secure` outside local development, so a "
            "browser sends it automatically and page scripts cannot read it. "
            "This is the transport browser clients should use."
        ),
    },
    _BEARER_SCHEME: {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "The same session token supplied as `Authorization: Bearer <token>`, "
            "for clients that cannot hold cookies. Accepted everywhere the "
            "cookie is."
        ),
    },
}

# Attached to every authenticated operation so the failure mode is visible in
# the reference, not only in prose.
_UNAUTHORIZED_RESPONSE: dict[str, Any] = {
    "description": (
        "No valid Administrator session. Returned identically for a missing, "
        "expired, tampered or otherwise invalid token."
    ),
    "content": {
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {"detail": {"type": "string"}},
            },
            "example": {"detail": "Authentication required."},
        }
    },
}

_ADMIN_PREFIX = "/api/admin/"


def _requires_session(path: str) -> bool:
    """Whether `require_admin` guards this path (see `core/auth_dependencies`)."""
    return path.startswith(_ADMIN_PREFIX)


def _flatten_tags(operation: dict[str, Any]) -> None:
    """Drop the umbrella `admin` tag when a specific one is present."""
    tags = operation.get("tags") or []
    if len(tags) > 1 and "admin" in tags:
        operation["tags"] = [tag for tag in tags if tag != "admin"]


def build_openapi(app: FastAPI) -> dict[str, Any]:
    """Return the enriched OpenAPI document, caching it on the application."""
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=API_TITLE,
        version=app.version,
        summary=API_SUMMARY,
        description=API_DESCRIPTION,
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )

    schema.setdefault("components", {})["securitySchemes"] = _SECURITY_SCHEMES

    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            _flatten_tags(operation)
            if _requires_session(path):
                # Either transport authorizes the request, so they are listed as
                # alternatives rather than as a combined requirement.
                operation["security"] = [
                    {_SESSION_COOKIE_SCHEME: []},
                    {_BEARER_SCHEME: []},
                ]
                operation.setdefault("responses", {}).setdefault(
                    "401", _UNAUTHORIZED_RESPONSE
                )

    app.openapi_schema = schema
    return schema
