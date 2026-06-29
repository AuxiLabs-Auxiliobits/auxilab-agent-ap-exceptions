"""Vendor directory management — per-tenant vendor → email (F1-5).

  GET    /v1/vendor-contacts      list this org's vendor contacts
  PUT    /v1/vendor-contacts      create/update a vendor's email + contact
  DELETE /v1/vendor-contacts      remove a vendor's contact

Set up once, then a mixed-vendor upload routes each invoice to its vendor (and
with bulk consolidation, each vendor gets one email for all their invoices).
Reads need run:read; mutations are admin-only (config:write). Tenant-scoped.
A distinct /v1/vendor-contacts prefix avoids colliding with /v1/vendors/{name}.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, field_validator

from app.api import vendor_directory
from app.api.auth import Principal
from app.api.deps import require_permission
from app.api.roles import CONFIG_WRITE, RUN_READ

log = logging.getLogger("ap_agent.routes_vendor_contacts")

router = APIRouter(prefix="/v1/vendor-contacts", tags=["vendors"])


class VendorContactInput(BaseModel):
    vendor_name: str
    email: str
    contact_name: str | None = None

    @field_validator("vendor_name")
    @classmethod
    def _name_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("vendor_name is required")
        return v

    @field_validator("email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        v = (v or "").strip()
        if "@" not in v or "." not in v.rsplit("@", 1)[-1]:
            raise ValueError("email must be a valid address")
        return v


class VendorContactDelete(BaseModel):
    vendor_name: str


@router.get("")
def list_vendor_contacts(
    principal: Principal = Depends(require_permission(RUN_READ)),
) -> dict:
    return {"contacts": vendor_directory.list_contacts(principal.tenant_id)}


@router.put("")
def put_vendor_contact(
    body: VendorContactInput = Body(...),
    principal: Principal = Depends(require_permission(CONFIG_WRITE)),
) -> dict:
    vendor_directory.upsert(
        tenant_id=principal.tenant_id,
        vendor_name=body.vendor_name,
        email=body.email,
        contact_name=body.contact_name,
        actor=principal.subject,
    )
    return {"ok": True, "vendor_name": body.vendor_name.strip(), "email": body.email}


@router.delete("")
def delete_vendor_contact(
    body: VendorContactDelete = Body(...),
    principal: Principal = Depends(require_permission(CONFIG_WRITE)),
) -> dict:
    deleted = vendor_directory.delete(principal.tenant_id, body.vendor_name)
    if not deleted:
        raise HTTPException(404, f"no vendor contact for '{body.vendor_name}'")
    return {"deleted": True, "vendor_name": body.vendor_name.strip()}
