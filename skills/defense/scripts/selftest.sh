#!/bin/sh
# Runs every SHOAV skill script on built-in sample data. Exit 0 = all good, non-zero = a check failed.
# Usage: sh skills/defense/scripts/selftest.sh from the repo, or sh scripts/selftest.sh inside an
# installed copy (for example .claude/skills/shoav). Paths resolve from this file, so any cwd works.
# Needs node and python3 or python on PATH.
DIR=$(cd "$(dirname "$0")" && pwd)
PY=$(command -v python3 || command -v python) || { echo "FAIL: python not found"; exit 1; }
command -v node >/dev/null || { echo "FAIL: node not found"; exit 1; }
fail() { echo "FAIL: $1"; exit 1; }

"$PY" "$DIR/cart_invariants_auditor.py" >/dev/null || fail "cart_invariants_auditor.py self test"
"$PY" "$DIR/semantic_normalizer.py" >/dev/null || fail "semantic_normalizer.py self test"
"$PY" "$DIR/semantic_normalizer.py" "No thanks, I hate saving money" | grep -q '"NEGATIVE"' || fail "semantic_normalizer.py CLI"

# The JS files are browser scripts; outside a browser they must load cleanly and export their helpers.
node -e '
const c = require(process.argv[1] + "/calculate_contrast.js");
const r = c.calculateContrastRatio([221, 221, 221, 1], [255, 255, 255, 1]);
if (Math.abs(r - 1.36) > 0.02) throw new Error("contrast #DDD on #FFF = " + r);
if (Math.round(c.calculateContrastRatio([0, 0, 0, 1], [255, 255, 255, 1])) !== 21) throw new Error("black on white");
const z = require(process.argv[1] + "/inspect_zindex_overlays.js");
if (typeof z.inspectStackingAndOverlays !== "function") throw new Error("overlay exports");
' "$DIR" || fail "JS contrast/overlay scripts"
node "$DIR/audit_telemetry.js" 2>&1 | grep -q "browser page" || fail "audit_telemetry.js outside browser message"
echo "OK: all skill scripts passed"
