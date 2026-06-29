"""Manual verification: POST returns fast, polling reflects live progress.

Run with: ANTHROPIC_API_KEY="" GEMINI_API_KEY="" AZURE_OPENAI_API_KEY="" \
          AZURE_CHAT_OPENAI_ENDPOINT="" python tests/_manual_verify_async.py
"""
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings
get_settings.cache_clear()

from app.api.main import app

SAMPLE = Path(__file__).parent.parent / "sample_data" / "exception_queue.csv"

c = TestClient(app)

with open(SAMPLE, "rb") as f:
    t0 = time.perf_counter()
    resp = c.post(
        "/v1/runs",
        files={"file": ("exception_queue.csv", f, "text/csv")},
        data={"tenant_id": "acme"},
    )
    dt_ms = (time.perf_counter() - t0) * 1000

summary = resp.json()
rid = summary["run_id"]
print(f"\n>>> POST returned in {dt_ms:.1f}ms")
print(f">>> initial status: {summary['status']}")
print(f">>> run_id:         {rid}")
print()

seen = []
deadline = time.perf_counter() + 30
i = 0
while time.perf_counter() < deadline:
    i += 1
    s = c.get(f"/v1/runs/{rid}").json()
    node = s.get("current_node")
    status = s.get("status")
    if not seen or seen[-1] != (status, node):
        seen.append((status, node))
        print(f"  poll #{i}: status={status:<18} node={node:<22} accepted={s.get('rows_accepted')}")
    if status in ("AWAITING_REVIEW", "COMPLETED", "FAILED"):
        break
    time.sleep(0.01)  # tight loop to catch transient nodes

print()
print(">>> transitions observed:")
for status, node in seen:
    print(f"     {status:<18} @ {node}")
