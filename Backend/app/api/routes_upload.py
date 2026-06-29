"""Upload format discovery: the accepted-format spec + a downloadable CSV
template. Lets the client know exactly which file types and column names are
accepted (and which aliases auto-map) before they upload."""
from __future__ import annotations

from fastapi import APIRouter, Response

from app.upload_format import csv_template, format_spec

router = APIRouter(prefix="/v1/upload", tags=["upload"])


@router.get("/format")
def get_upload_format() -> dict:
    """Machine-readable description of accepted columns, types, file types,
    size limit, and auto-mapped header aliases."""
    return format_spec()


@router.get("/template.csv")
def get_upload_template() -> Response:
    """Download a ready-to-fill CSV template with the canonical headers + sample rows."""
    return Response(
        content=csv_template(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="ap_exception_template.csv"'},
    )
