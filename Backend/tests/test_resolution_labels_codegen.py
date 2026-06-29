"""Guards the resolution-label single source of truth.

The labels live in ``app/schemas/resolution_labels.json``; the backend loads it
directly and the frontend's ``resolutionLabels.ts`` is generated from it by
``scripts/gen_resolution_labels.py``. These tests fail if the enum and the JSON
drift apart, or if the committed TS is stale (edited JSON without regenerating).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_GEN_PATH = Path(__file__).resolve().parents[1] / "scripts" / "gen_resolution_labels.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_resolution_labels", _GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_json_labels_cover_exactly_the_enum():
    from app.schemas import ResolutionPath
    from app.schemas.resolution import RESOLUTION_PATH_LABELS

    assert set(RESOLUTION_PATH_LABELS) == {p.value for p in ResolutionPath}


def test_frontend_ts_is_not_stale():
    gen = _load_generator()
    expected = gen.render_ts(gen.load_labels())
    actual = gen.TS_PATH.read_text(encoding="utf-8")
    assert actual == expected, (
        "Frontend/src/lib/resolutionLabels.ts is out of date — run "
        "`python Backend/scripts/gen_resolution_labels.py` and commit the result."
    )
