#!/usr/bin/env python
"""E2E: a long, fully visible article must not be rewritten in enforce mode.

Usage: python e2e/test_benign_long_page.py --controller http://127.0.0.1:18600 --fixture-port 18690
Asserts browser.observe and browser.snapshot on fixtures/benign_article.html return
verdict none (not REWRITE) and that the last paragraph survives in the observe text.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_t5 import (FIXTURE_DIR, blob_of, call_tool, close_sid, serve_fixtures,  # noqa: E402
                    session_id_of, verdict_of)

LATE_PARAGRAPH = "Apprentices copied older pages by hand"
LAST_PARAGRAPH = "This closing note repeats that the page is a plain public article"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--controller", required=True)
    ap.add_argument("--fixture-port", type=int, required=True)
    args = ap.parse_args()
    if not 18690 <= args.fixture_port <= 18699:
        print("fixture port must be 18690-18699")
        return 2

    rows = []

    def rec(name, ok, detail=""):
        rows.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} {name} -- {detail}")

    with serve_fixtures(FIXTURE_DIR, "127.0.0.1", args.fixture_port) as base:
        resp = call_tool(args.controller, "browser.create_session",
                         {"start_url": base + "/benign_article.html"})
        sid = session_id_of(resp)
        rec("create_session", bool(sid), f"sid={sid}")
        if sid:
            try:
                obs = call_tool(args.controller, "browser.observe",
                                {"session_id": sid, "preset": "rich", "limit": 200})
                snap = call_tool(args.controller, "browser.snapshot", {"session_id": sid})
                for label, r in (("observe", obs), ("snapshot", snap)):
                    v = verdict_of(r)
                    rec(f"{label} verdict none", v == "none" and not r.get("isError"),
                        f"verdict={v} isError={r.get('isError')}")
                # observe text_excerpt is capped (2000 chars text, 4000 rich) and this article
                # is about 4250 chars, so the closing note only fits in the uncapped snapshot.
                rec("late paragraph present in observe", LATE_PARAGRAPH in blob_of(obs),
                    "paragraph past the first screen survives")
                rec("last paragraph present in snapshot", LAST_PARAGRAPH in blob_of(snap),
                    "closing note text")
            finally:
                close_sid(args.controller, sid)

    failed = rows.count(False)
    print(f"result: {'PASS' if not failed else 'FAIL'} ({len(rows) - failed}/{len(rows)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
