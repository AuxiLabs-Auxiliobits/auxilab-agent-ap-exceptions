"""Vendor reliability sidecar endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.vendor import get_vendor_store

router = APIRouter(prefix="/v1/vendors", tags=["vendors"])


@router.get("")
def list_vendors() -> dict:
    """List all vendor profiles, sorted by total_invoices_seen DESC.

    Each profile is enriched with its computed ``reliability_score`` (a method
    on the model, so it isn't included by a plain ``model_dump``).
    """
    store = get_vendor_store()
    profiles = store.get_all()
    out = []
    for p in profiles:
        d = p.model_dump(mode="json")
        d["reliability_score"] = p.reliability_score()
        out.append(d)
    out.sort(key=lambda d: d.get("total_invoices_seen", 0), reverse=True)
    return {"profiles": out, "total_vendors": len(out)}


@router.get("/{vendor_name}")
def get_vendor(vendor_name: str) -> dict:
    store = get_vendor_store()
    profile = store.get(vendor_name)
    if profile is None:
        raise HTTPException(404, f"vendor not found: {vendor_name!r}")
    payload = profile.model_dump(mode="json")
    payload["reliability_score"] = profile.reliability_score()
    return payload
