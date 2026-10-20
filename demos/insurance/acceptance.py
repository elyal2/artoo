"""Run the acceptance questions in questions.txt against a running ARTOO API.

Usage: python demos/insurance/acceptance.py [questions.txt] [api_url]
Exit code is non-zero if any question fails to produce SQL + rows.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path


def main() -> int:
    qfile = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("questions.txt"))
    url = (sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000") + "/api/query"
    failures = 0
    for q in (ln.strip() for ln in qfile.read_text(encoding="utf-8").splitlines()):
        if not q:
            continue
        t0 = time.time()
        req = urllib.request.Request(
            url, json.dumps({"question": q}).encode(), {"Content-Type": "application/json"}
        )
        try:
            r = json.load(urllib.request.urlopen(req, timeout=180))
            ok = bool(r.get("sql")) and bool(r.get("rows") or r.get("data"))
        except Exception as exc:  # noqa: BLE001
            ok, r = False, {"sql": f"ERROR {exc}"}
        failures += 0 if ok else 1
        print(
            f"{'OK  ' if ok else 'FAIL'} {time.time() - t0:5.1f}s  {q}\n      {str(r.get('sql'))[:160]}"
        )
    print(f"\n{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
