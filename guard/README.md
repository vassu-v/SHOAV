# Guard

The deterministic part of S.H.O.A.V. Pure Python, standard library only, no model calls. Any LLM in the wider design is
advisory and can only raise suspicion, never clear it.

| Folder | What it is |
|---|---|
| `filters/` | The rules. Ingress filters rewrite or block what the agent reads. Egress filters check clicks and form submits before they run. Also the probes (JS run in the page), per-session state and the tests |
| `connectors/` | Adapters between the MCP server's payloads and the filter inputs (observe and snapshot payloads, egress arguments, rewrite, session cache). Dict in, dict out, no server imports |

Other files: [`DETERMINISTIC_TARGETS.md`](DETERMINISTIC_TARGETS.md) (the target spec), [`filters/README.md`](filters/README.md)
(rules, limits and tests in depth, some of its older path references predate the restructure), `filters/plan.md` and
`filters/PLAN_AND_ROUGH_SKETCH.md` (design notes).

## Verdicts

| Verdict | Meaning |
|---|---|
| ALLOW | Nothing found, the result passes unchanged |
| REWRITE | Dangerous parts are removed and the cleaned result is returned with a `_shoav` note |
| ESCALATE | Suspicious but not provable. The action is held and the agent is told to re-check or ask a human |
| BLOCK | Unsafe. The action is aborted or the page is refused, with the reason |

## What it checks

| Trap | Where | Check |
|---|---|---|
| Hidden text injection | Ingress | Computed visibility and geometry, zero-width and instruction patterns. Hidden nodes are stripped |
| Invisible overlay over the real button | Egress | `document.elementFromPoint` at the click target against the element the agent meant |
| Pre-checked consent boxes | Egress | Form state at read time against submit time. An untouched pre-ticked box holds the submit |
| Context flooding | Ingress | Node and text budgets. Over the trigger the page is capped or blocked |

## Modes

The server switches the guard with `SHOAV_GUARD_MODE`: `off` (no guard), `observe` (checks run and are logged, results are
never changed), `enforce` (rewrites and blocks apply). A crashing filter fails open unless `SHOAV_GUARD_FAIL=closed`. The server
finds this folder by default, or from `SHOAV_FILTERS_PATH`. See [`../server/SHOAV.md`](../server/SHOAV.md).

## Run the unit tests

From this folder (`guard/`):

```bash
python -m unittest discover -s filters/tests -t .
python -m unittest discover -s connectors/tests -t .
```

No install is needed. One filters test drives a real Chromium through Playwright and is skipped if it is not available.
The end to end matrix against a running server is in [`../e2e/README.md`](../e2e/README.md).

## Limits

Thresholds are heuristics until tuned on real traffic. Iframe and Shadow DOM hit testing, a live mutation-rate feed, text
inside images and site specific cart checks are not covered. Wording tricks such as confirmshaming are left to the
[defence skill](../skills/defense/README.md). See [`../docs/DESIGN.md`](../docs/DESIGN.md).
