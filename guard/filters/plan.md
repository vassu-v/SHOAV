# filters/plan.md

Status of the deterministic filter core and what remains inside `shoav-mcp/filters/`.
The integration plan is in `../MCP/plan.md`.

## Scope decision

Target 5 (cart sneaking) is out of scope. Cart and add-to-cart detection is site specific and cannot be
hardcoded. The `diff_cart_state` code stays as is, untouched and unwired. Targets 1 to 4 are the demo scope.

## Done in this pass (fixer wrote code, tester wrote tests separately, human review by the lead)

| Fix | What changed | Where |
|---|---|---|
| F1 | REWRITE now really removes text: hidden-node text, zero-width characters, and each sentence containing an injection keyword (replaced by `[removed by S.H.O.A.V.: suspected injected instruction]`). Runs before truncation. | `ingress/rules.py` (`sanitize_text`), `ingress/engine.py` |
| F2 | Style probe walks every element with its own text, not only stamped interactables. Effective hidden state through ancestors (display, visibility, opacity product). Cap 2000, path selector fallback ref. | `ingress/scripts.py` |
| F3 | Hit test returns `inside_target` (`target.contains(topEl)`), so a click landing on a child span is ALLOW. Backwards compatible. | `egress/scripts.py`, `egress/rules.py` |
| F4 | `mark_touched` on the state and the store. Ingress prefers `ref`, then `element_id`, then name. | `session_state.py`, `ingress/engine.py` |
| F6 | Focus check skips the value comparison for password fields. | `egress/scripts.py`, `egress/rules.py` |

Verification: 90 tests pass (37 original plus 53 new), including 13 tests that run the JS in a real Chromium
against tiny inline fixtures. This is the first time the JS has executed in a browser.

## Known gaps still inside the core

1. Modals: `looks_like_decoy` BLOCKs any different top element with z-index above the threshold. A legitimate
   consent dialog can trip it. Needs tuning data (or ESCALATE instead of BLOCK for opaque elements).
2. Hidden text longer than 200 characters is only removed for its 200 character prefix.
3. A hidden node whose text also appears visibly elsewhere loses that visible copy too. Rare, accepted.
4. Keyword lists are patterns, not understanding. Paraphrased injections pass. That belongs to the skill layer.
5. Mutation rate has a decision function but no observation feed. Needs a MutationObserver in the connector.
6. Iframes and Shadow DOM: `elementFromPoint` returns the host or iframe element. Not handled.
7. Thresholds are guesses until there is attack and benign data from the test site.
8. `IngressFilter` still reads `accessibility_outline`, which is always unavailable in MCP/auto-browser. The connector
   supplies `form_controls` from a form probe instead (see MCP plan, task C2). The engine should accept
   `form_controls` directly. Small change, listed as task F-1 below.

## Remaining tasks in this folder

- F-1: `IngressFilter.process(..., form_controls=None)` accepts controls directly (ref is `element_id`).
- F-2: hit test: when the top element is opaque and a plausible modal, ESCALATE not BLOCK (needs a decision).
- F-3: `FORM_STATE_SCRIPT` (checkbox, switch, radio state with label and stable ref). Lives in `ingress/scripts.py`.
- F-4: `MUTATION_OBSERVER_SCRIPT` install and read pair, plus a rate helper.
- F-5: rule tests written by a different agent than the one writing the rule (repo rule).

## Rules for anyone editing here

- Whoever writes a detector does not write its test.
- Pure functions, plain dicts in and out, no controller imports, no network.
- Synthetic data only. Do not build attack sites; the teammate owns those. Tiny inline fixtures for unit tests are fine.
- No em dashes in docs.
