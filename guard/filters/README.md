# S.H.O.A.V. Deterministic Filter Core (`shoav-mcp/filters/`)

**Status: independent core built and unit-tested. Not wired into any MCP yet — see "What's still open" below.**

This directory holds the deterministic (no-LLM) ingress/egress filter logic
for S.H.O.A.V. It is pure Python, zero third-party dependencies, and does
not touch `external/auto-browser` or any live browser. That's a deliberate
scoping choice, not an oversight — see "Why independent-first" below.

---

## 1. Research basis — what this is built on

Everything here traces back to prior work already in this repo, not new
research done while coding:

- **`docs/research/04-mitigations/FINDINGS.md`** — establishes the core design
  thesis: deterministic/structural detection is well-precedented for
  hidden-text (PhantomLint), and an LLM must never be the sole/final gate,
  because LLM guards are themselves attackable through the content they
  inspect (up to 100% guardrail-evasion rates measured [M-03], JudgeDeceiver
  and Comparative Undermining Attack against LLM-as-judge [M-04][M-09]).
  That's why nothing in this package calls a model.
- **`docs/research/08-synthesis/DETECTION_TARGETS.md`** and
  **`docs/research/07-trickyarena/FINDINGS.md`** — the priority ranking (build
  the fully-structural targets first; explicitly skip confirmshaming,
  bait-and-switch, aesthetic manipulation — those need language
  understanding and are out of scope for this core by design, routed to
  the separate cognitive-vigilance skill instead).
- **`shoav-mcp/DETERMINISTIC_TARGETS.md`** — the exact 5-target spec this
  package implements against (table below).
- **`shoav-mcp/filters/context.md`** and **`PLAN_AND_ROUGH_SKETCH.md`** —
  the architectural decisions (Ingress ALLOW/REWRITE/BLOCK, Egress
  ALLOW/BLOCK/ESCALATE, the "unified adapter" pattern: pure core now,
  connectors later) and the original rough code sketches this package
  refines.
- **`docs/research/06-autobrowser/FINDINGS.md`** and **`INTEGRATION.md`** — the
  actual Auto Browser payload shapes (`interactables`, `accessibility_outline`)
  the fixtures in `tests/fixtures.py` mirror, and the recommended
  interception points for when connectors get written.
- **`docs/research/08-synthesis/OPEN_QUESTIONS.md`** — the honesty constraint
  this whole package tries to respect: question 1 says structural detection
  against general deceptive UI is "plausible and partially precedented, not
  proven"; question 2 says no false-positive rate has been measured for
  rules like these. Nothing below claims otherwise — see "Known
  limitations."

## 2. Why independent-first

The user's design question was: build inside `external/auto-browser`
directly, or build the logic standalone and connect later? This package is
the answer already recommended in `PLAN_AND_ROUGH_SKETCH.md` §2 (the
"Unified Adapter Pattern"): write the detection/decision logic once as
plain Python functions over plain dicts, test it with fixtures shaped like
Auto Browser's real payloads, and only afterward write a thin connector
that feeds it live data. Nothing here imports Playwright, FastAPI, or
anything from `external/`.

## 3. Target coverage vs. `shoav-mcp/DETERMINISTIC_TARGETS.md`

| # | Target | Status | Where |
|---|---|---|---|
| 1 | Hidden/Invisible Text | **Done, and now actually sanitizing** (`sanitize_text` removes hidden-node text, zero-width chars, and whole sentences containing injection keywords from `text_excerpt`, replacing them with a removal marker, before truncation). Both halves: style-based (`find_hidden_textful_nodes`, needs the not-yet-wired `STYLE_PROBE_SCRIPT`, which now walks every element with its own text and resolves hidden state through ancestors) and text-based (`find_text_injections` — zero-width Unicode + comment/keyword scan, works from data Auto Browser already returns) | `ingress/rules.py` |
| 2 | Clickjacking & Overlays | **Done** (hit-test script takes `expected_ref` and reports `inside_target`, so a click landing on a child of the target is ALLOWed) — `evaluate_hit_test`, with one deliberate refinement over the original sketch (see §5) | `egress/rules.py` |
| 3 | Pre-Checked States | **Done** — `flag_prechecked_toggles` (ingress, at observation time) + `audit_form_state` (egress, at submission time). Works **today** from Auto Browser's existing `accessibility_outline` payload, whose AX nodes already carry a `checked` field — no new capability needed for this one | `ingress/rules.py`, `egress/rules.py` |
| 4 | Context Overloading & Dummy Diffs | **Done, three sub-checks**: node-count budget (`compact_node_budget`), text/token budget (`truncate_text_excerpt` — this was missing in the first pass, added after review, see §6), and a mutation-rate flood decision (`evaluate_mutation_rate`). The *decision* logic for all three is implemented; the mutation-rate *observation* (a live MutationObserver feed) is connector-layer work, not yet built | `ingress/rules.py`, `ingress/engine.py` |
| 5 | Cart Sneaking | **Intentionally out of scope for now** (logic exists, untouched, not being extended) — `diff_cart_state`, using the per-session state cache to hold the T0 cart snapshot | `egress/rules.py`, `session_state.py` |

All 5 targets from the spec have real logic and real test coverage. Nothing
was silently skipped. What's *not* covered is everything the research
explicitly put out of scope for the deterministic core (confirmshaming,
bait-and-switch, aesthetic manipulation, fake urgency) — those need
language understanding and were never meant to live here; they're the
cognitive-vigilance skill's job.

## 4. What was actually built

```
shoav-mcp/filters/
├── constants.py       every threshold/keyword list, one place, each with
│                       a one-line note of which doc it came from
├── types.py            Verdict enum: ALLOW / REWRITE / BLOCK / ESCALATE
├── session_state.py     per-session cache (SessionState + SessionStateStore)
│                       for the two checks that need a T0-vs-T1 diff
│                       (pre-checked-at-load vs. pre-checked-at-submit,
│                       cart-before vs. cart-after)
├── ingress/
│   ├── scripts.py       STYLE_PROBE_SCRIPT — a JS string, not executed by
│   │                    anything here yet (see §6, open item 1)
│   ├── rules.py          7 pure functions, each independently testable
│   └── engine.py         IngressFilter.process() — orchestrates the rules
│                        into one verdict + telemetry + a possibly-modified
│                        payload
├── egress/
│   ├── scripts.py       hit-test + focus-check JS, same "not executed
│   │                    here" status
│   ├── rules.py          4 pure decision functions
│   └── engine.py         EgressFilter with 4 entry points: verify_click,
│                        verify_input, verify_submission, verify_cart
└── tests/               37 unit tests, see §5
```

Design decisions worth flagging (not just "what," but "why," since some of
these diverge from the original rough sketches):

- **JS reports facts, Python decides.** The original sketch in
  `PLAN_AND_ROUGH_SKETCH.md` had the in-page JavaScript both inspect *and*
  mutate the DOM (`el.remove()`) in one pass, so Python only ever saw a
  count. `INTEGRATION.md` independently recommended the opposite —
  `style_probe` should report facts "WITHOUT pre-filtering... we want the
  invisible ones surfaced, not silently dropped." This package follows that
  recommendation: `scripts.py` only gathers facts; every decision (is this
  benign-hidden, is this a real injection) is in testable Python.
- **Benign-hidden allowlist.** `find_hidden_textful_nodes` skips
  `sr-only`/`visually-hidden`-style nodes instead of stripping everything
  hidden, because naive hidden=malicious over-fires on ordinary
  accessibility markup (a stated risk in `DETECTION_TARGETS.md` Target 1).
- **Keyword-gated pre-checked-toggle flagging.** Only `checkbox`/`toggle`/
  `switch` types are eligible (never `radio`/`select`, which usually need
  *some* default), and only when the label matches a consent/marketing/
  add-on keyword list — otherwise a "remember me" default or a required
  shipping-method radio would false-positive on every ordinary commercial
  site.
- **Egress ESCALATE, not just BLOCK.** The design defines three egress
  verdicts, but the original hit-test sketch only ever produced two. Here,
  a topmost-element mismatch only **BLOCK**s when it looks like an actual
  decoy (near-zero opacity or absurd z-index); an ordinary, visible,
  different element on top (e.g. a cookie banner that genuinely just
  appeared) gets **ESCALATE** instead — it might mean the page changed
  under the agent, not that it's under attack.

## 5. Tests — what they check and how to run them

37 tests, stdlib `unittest` (no `pytest` installed in this environment; no
pip install needed either way — matches the project's own "zero
dependencies for the deterministic core" philosophy from
`PLAN_AND_ROUGH_SKETCH.md` §4).

```bash
cd shoav-mcp && python3 -m unittest discover -s filters/tests -t . -v
```

`tests/fixtures.py` is the important file to read first: it's data shaped
like Auto Browser's **real** payloads — `interactables` entries look like
`INTERACTABLES_SCRIPT`'s output (`{element_id, tag, type, role, label,
bbox}`), `accessibility_outline.nodes` entries look like Playwright's
native `accessibility.snapshot()` nodes — per what
`docs/research/06-autobrowser/FINDINGS.md` documented from the actual source.
That's what testing "against the MCP's own internal data types" means with
no live browser available: fixtures shaped like the real thing, not an
invented format.

Every rule is tested with **both** an attack case and a false-positive
trap in the same test, not just the happy path:

| Rule | Attack case | False-positive trap it must NOT fire on |
|---|---|---|
| hidden-textful nodes | injected `display:none` instruction node | `sr-only` skip-link span |
| pre-checked toggles | "share my data with marketing partners" | "remember me" checkbox, shipping-method radio |
| hit-test | near-zero-opacity high-z-index overlay | a legitimate different element genuinely on top (→ ESCALATE, not BLOCK) |
| focus integrity | value typed into a hidden decoy field | — (exact-match by design, see §6) |
| cart diff | item appears with no logged add-click | item appears whose click *was* logged |
| node/token budget | 750-node flood page | 10-node ordinary page (no-op) |

`test_session_state.py` covers the cache itself (same-session identity,
cross-session isolation, mutation persistence, reset) — this had zero
coverage in the first pass and was added after re-review (§6).

## 6. Known limitations — read this before trusting any of it

Being direct about this, per the project's own "report-safety" norm
(`docs/research/09-verification-closeout/CLOSEOUT.md`) and because it was asked
directly: **no**, this is not the complete wired thing yet, and yes, it has
real, documented gaps — not bugs that crash it (all 37 tests pass), but
scope and design limitations worth knowing before demoing it:

1. **Nothing here has executed against a real browser.** `scripts.py`'s JS
   strings are written but never run. Every test feeds pre-computed fixture
   data standing in for what that JS *would* return. This is real, but it
   is simulated-real, not live-verified.
2. **The mutation-rate flood check has a decision function
   (`evaluate_mutation_rate`) but no observation mechanism.** A per-second
   rate isn't a single `page.evaluate()` call, it's a subscription over
   time — that's connector-layer work, explicitly not started.
3. **Pre-checked-toggle refs are a real correlation weakness, partly mitigated.** Ingress now prefers a node's `ref` or `element_id` when present, and `SessionState.mark_touched` / `SessionStateStore.mark_touched` record agent interactions. Remaining weakness: Playwright's
   native `accessibility.snapshot()` nodes (what Auto Browser's
   `accessibility_outline` actually returns, per `FINDINGS.md` §1a) have no
   stable element id — this package uses the accessible **name/label
   text** as a pseudo-ref. That's fine for flagging ("this toggle looks
   pre-checked") but fragile for later re-identifying the exact same
   control to let the agent un-check it (two controls with identical
   labels would collide). Wiring this properly likely means correlating
   against the separate `interactables` list by bounding-box proximity, or
   getting Auto Browser's AX-tree output extended with a stable ref — an
   open integration question, not something fixable in this pure layer.
4. **Focus-integrity value comparison is exact-string** (skipped for `type == "password"`, where only the ref must match). A legitimate
   autocomplete/autofill that alters the typed value slightly could produce
   a false BLOCK. A fuzzy/prefix match would reduce this but adds its own
   tuning surface — left as exact-match deliberately rather than guessing
   at a fuzz threshold with no data to tune it against.
5. **Every threshold is a heuristic parameter, not a measured one** — this
   is the literature's own stated gap (`OPEN_QUESTIONS.md` #2), not
   something this package resolves. They're collected in `constants.py`
   specifically so they can be tuned once real false-positive/attack data
   exists, instead of guessed once and forgotten.
6. **Keyword lists (injection phrases, consent keywords) are pattern
   matching, not language understanding.** Documented in `constants.py`
   itself: a paraphrased injection or a consent toggle with unrelated
   wording will slip through. This is intentional scope, not a bug — that
   gap belongs to the semantic/skill layer, not the deterministic core.
7. **The `eval_js` governance question from the design discussion is still
   open.** Auto Browser requires `workflow_profile=governed` (with a human-
   approval gate) for `eval_js`, the tool that would run `scripts.py`'s
   JS today. Not blocking for this layer, since nothing here calls it yet
   — but it's the first thing to resolve when writing the proxy connector.

Update since first pass: ingress previously only reported findings and left
`text_excerpt` untouched; it now rewrites it. Remaining limits of that
rewrite: sentence-level removal is keyword-based (paraphrases survive), hidden
text is matched by exact string (the style probe keeps only 200 chars per
node, so longer hidden text is removed only in that prefix), and Target 5
(cart sneaking) is intentionally out of scope for now.

## 7. Next version — connectors

The whole point of building this independently was to defer the
integration decision, not skip it. Two connectors, not written yet:

- **`shoav-mcp/connectors/gateway_patch.py`** — an in-process wrapper
  around `McpToolGateway.call_tool()` inside `external/auto-browser`. Calls
  `session.page.evaluate()` directly, bypassing the `eval_js`
  governed-approval gate entirely since it never goes through that tool
  call. The internals work you're doing separately is exactly what this
  connector will eventually sit on top of.
- **`shoav-mcp/connectors/proxy_adapter.py`** — an external stdio/HTTP MCP
  proxy in front of Auto Browser, for running the guard against a stock,
  unmodified install. Needs the `eval_js` auto-approve dance (call → 409 →
  self-approve via `browser.approve_approval` → retry) worked out first.

Neither connector is needed to keep developing or testing the core in
`ingress/` and `egress/` — they're additive, wired in whenever the Auto
Browser internals side is ready.
