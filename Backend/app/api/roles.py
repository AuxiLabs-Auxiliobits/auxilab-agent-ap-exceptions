"""Role-based access control (RBAC) for the API.

A small, centralized authorization model layered on top of the Clerk JWT auth in
``app.api.auth``. Authentication answers *who are you*; this module answers *what
may you do*.

The product is designed around the AP personas documented in the user guide
(AP Clerk, AP Manager, Finance Controller, Auditor, Procurement) plus an Admin.
Each role maps to a set of permissions; sensitive mutations (create a run, edit a
draft, send communications, approve a run) are gated on a permission, and the
read paths stay open to every authenticated role. This enforces a basic
segregation of duties — e.g. an Auditor can read everything but mutate nothing.

The whole matrix lives here on purpose: it is the single source of truth, mirrored
to the browser verbatim via ``GET /v1/me`` so the UI never re-derives it. To change
who can do what, edit ``ROLE_PERMISSIONS`` and nothing else.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Permissions — the verbs the API gates on.                                    #
# --------------------------------------------------------------------------- #
RUN_READ = "run:read"
RUN_CREATE = "run:create"
DRAFT_EDIT = "draft:edit"
COMMS_SEND = "comms:send"
RUN_APPROVE = "run:approve"
# Manage per-org integrations (BYOK keys, email/Slack). Admin-only.
CONFIG_WRITE = "config:write"

ALL_PERMISSIONS: tuple[str, ...] = (
    RUN_READ,
    RUN_CREATE,
    DRAFT_EDIT,
    COMMS_SEND,
    RUN_APPROVE,
    CONFIG_WRITE,
)

# --------------------------------------------------------------------------- #
# Roles — the application personas.                                            #
# --------------------------------------------------------------------------- #
ADMIN = "admin"
MANAGER = "manager"
CLERK = "clerk"
CONTROLLER = "controller"
AUDITOR = "auditor"
PROCUREMENT = "procurement"

# Who can do what. Auditor is deliberately read-only (segregation of duties).
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ADMIN: frozenset(ALL_PERMISSIONS),
    MANAGER: frozenset({RUN_READ, RUN_CREATE, DRAFT_EDIT, COMMS_SEND, RUN_APPROVE}),
    CLERK: frozenset({RUN_READ, RUN_CREATE, DRAFT_EDIT, COMMS_SEND}),
    CONTROLLER: frozenset({RUN_READ, DRAFT_EDIT, COMMS_SEND, RUN_APPROVE}),
    PROCUREMENT: frozenset({RUN_READ, COMMS_SEND}),
    AUDITOR: frozenset({RUN_READ}),
}

ALL_ROLES: tuple[str, ...] = tuple(ROLE_PERMISSIONS.keys())

# Accept common spellings of a role coming from a Clerk custom role key or a
# custom claim, and normalize them to our canonical role names.
_ROLE_ALIASES: dict[str, str] = {
    "administrator": ADMIN,
    "owner": ADMIN,
    "ap_manager": MANAGER,
    "ap-manager": MANAGER,
    "ap_clerk": CLERK,
    "ap-clerk": CLERK,
    "finance_controller": CONTROLLER,
    "finance-controller": CONTROLLER,
    "financecontroller": CONTROLLER,
    "procurement_team": PROCUREMENT,
}


def can(role: str | None, permission: str) -> bool:
    """True if ``role`` is granted ``permission``."""
    return permission in ROLE_PERMISSIONS.get(role or "", frozenset())


def permissions_for(role: str | None) -> list[str]:
    """The sorted permission list for a role (empty for an unknown role)."""
    return sorted(ROLE_PERMISSIONS.get(role or "", frozenset()))


def _normalize(value: str) -> str | None:
    """Map an arbitrary role string to a canonical role name, or None."""
    key = value.strip().lower().replace(" ", "_")
    # Strip a Clerk-style "org:" prefix (org roles arrive as e.g. "org:admin").
    if ":" in key:
        key = key.split(":", 1)[-1]
    if key in ROLE_PERMISSIONS:
        return key
    return _ROLE_ALIASES.get(key)


def role_from_claims(claims: dict, default_role: str) -> str:
    """Resolve an application role from a verified Clerk JWT's claims.

    Precedence (first match wins):
      1. An explicit application-role claim — ``ap_role`` / ``role``, or
         ``public_metadata.role`` (Clerk surfaces user public metadata here).
      2. The Clerk organization role (``org_role``, e.g. ``org:admin``):
         ``org:admin`` → admin; a custom org role whose key matches a known role
         (e.g. ``org:controller``) maps through; a plain member falls through.
      3. ``default_role`` (configurable via ``AUTH_DEFAULT_ROLE``).

    Always returns a valid role name; an unrecognized ``default_role`` collapses
    to the least-privileged sensible default (``clerk``).
    """
    # 1. Explicit application role claim.
    explicit = claims.get("ap_role") or claims.get("role")
    if not explicit:
        meta = claims.get("public_metadata") or claims.get("metadata")
        if isinstance(meta, dict):
            explicit = meta.get("role")
    if isinstance(explicit, str):
        norm = _normalize(explicit)
        if norm:
            return norm

    # 2. Clerk organization role.
    org_role = claims.get("org_role")
    if not org_role:
        o = claims.get("o")
        if isinstance(o, dict):
            org_role = o.get("rol")
    if isinstance(org_role, str):
        norm = _normalize(org_role)
        if norm:
            return norm
        # A generic org member ("org:member"/"org:basic_member") has no mapped
        # role — fall through to the configured default.

    # 3. Configured fallback.
    return default_role if default_role in ROLE_PERMISSIONS else CLERK
