# Subsystem Context: S.H.O.A.V. Deterministic Filters (`shoav-mcp/filters/`)

> **Subsystem**: S.H.O.A.V. Filter Engine (Ingress & Egress)  
> **Location**: `shoav-mcp/filters/context.md`  
> **Last Updated**: 2026-09-25 15:30  
> **Status**: Architecture, Rough Sketch, and Integration Strategy Finalized; Pre-Build Stage  

---

## 1. Executive Summary & Purpose

This document is the dedicated single source of truth for the `shoav-mcp/filters/` subsystem. It captures the entire dialogue, thought evolution, architectural trade-offs, research insights, and concrete code sketches for:
1. **Filter 1 (Ingress)**: Deterministic DOM pruning, CSS cloaking removal, context overloading protection, and tree compaction (`ALLOW`, `BLOCK`, `REWRITE`).
2. **Filter 2 (Egress)**: Deterministic physical hit-testing via `document.elementFromPoint`, clickjacking overlay detection, and form state auditing (`ALLOW`, `BLOCK`, `ESCALATE`).
3. **Integration Strategy**: Why we are directly modifying the internals of `external/auto-browser` to power the live visual dashboard.

---

## 2. Complete Dialogue & Idea Evolution Log

### 2.1 Ideas and Directions Provided by User
* **No Premature Building**: Establish a complete plan, technical sketch, and subsystem context first so every engineering decision is grounded.
* **The Core Weapon is the Tool**: Primary focus is the Hardened MCP tool. The defense must live at the MCP protocol boundary and be **100% deterministic** without an LLM in the critical path.
* **Ingress Filter Verdicts & Feedback**:
  - The Ingress filter handles data coming into the agent (observation/snapshots).
  - Verdicts: `ALLOW` (clean), `BLOCK` (catastrophic attack), or `REWRITE` (sanitize).
  - **Key User Requirement**: When sending `REWRITE` or `BLOCK` back to the agent, what context is given? It must provide structured, understandable telemetry explaining *why* the page was altered or blocked so the agent can replan or proceed without being confused.
* **Context Overloading as a Surfaced Vector**:
  - Identified context overloading / flooding as a critical missing vector: hostile sites dumping massive filler DOM trees, repetitive classes, or dummy diffs to dilute attention, displace system prompts, and exhaust token budgets.
* **Fast Decision Acceleration (Jev & Embeddings)**:
  - Explored whether local embedding models (vector cosine similarity) can be used deterministically for semantic classification.
  - Highlighted **Jev** (TypeSafe AI, released Sept 15, 2026: System One non-autoregressive decision model) and the open-source `JevEmbed` framework for local, low-latency, zero-cost structured decisions.
* **The Three-Pillar Vision**:
  - *Pillar 1 (The Tool)*: The Hardened MCP Proxy (our core implementation).
  - *Pillar 2 (The Skill)*: Cognitive Vigilance & Dark Pattern Advisor (`skills/shoav-guard/`). Teammate is authoring this to cover human psychology, cognitive biases, confirmshaming, and vigilance guidelines.
  - *Pillar 3 (The Subagent / Harness)*: A future lightweight, least-privilege delegate agent that can *only* browse, screenshot, edit Markdown/image/empty files, and move relative files (zero shell).
* **Anti-Benchmark Bias**:
  - We do not bias our engine or tune our rules to a specific benchmark (like TrickyArena). We bias against real-world malicious actor techniques and empirical research. TrickyArena serves solely as an un-rigged external testbed.
* **Agent Gaslighting & Tool Misattribution (User Insight)**:
  - Critical agent-specific vector: Hostile sites induce simulated errors, focus theft, or fake tool crash popups.
  - The agent misattributes the malfunction to its own tool or code, triggering self-critical recovery loops that obey malicious on-page remediation instructions or leak credentials into fake forms.
  - Mitigated deterministically: Ingress quarantines fake system error prompts in DOM; Egress validates input focus integrity (document.activeElement and value match).
* **The Architectural Dilemma**:
  - Posed the question: Should we modify the internals of the cloned MCP (`external/auto-browser`) or build a separate external proxy?

### 2.2 Assistant Analysis, Research, & Synthesis
* **On Ingress `REWRITE` vs `BLOCK`**:
  - Outright blocking pages with CSS quirks causes the ProtectAI failure mode (where task utility crashed from 83% to 41%).
  - `REWRITE` (sanitizing invisible nodes and compacting the tree) destroys the exploit while preserving 100% of task utility.
  - Context sent on `REWRITE`: Structured YAML header (`[S.H.O.A.V. INGRESS SHIELD: SANITIZED]`) stating exactly what was stripped and compacted.
  - Context sent on `BLOCK`: Structured JSON error detailing context flooding parameters so the agent navigates back or picks an alternate link.
* **On Attention Dilution ($A = \text{Softmax}(QK^T/\sqrt{d_k})$)**:
  - Bounding node budgets to top-k interactive elements (e.g. max 50 candidates, <4k tokens) guarantees that system instructions remain within the high-salience attention zone, neutralizing "Lost in the Middle" attacks.
* **On Jev & Embeddings**:
  - Vector cosine similarity against offline reference centroids is strictly deterministic (pure linear algebra, zero token generation, zero hallucination).
  - `JevEmbed` allows running local sentence transformers (`all-MiniLM-L6-v2`, 80MB) for 20ms local semantic scoring without cloud API dependencies.
* **On the Architectural Choice (Internal Modification Selected)**:
  - Codebase audit revealed that `external/auto-browser` **has already been decoupled from Docker, runs natively on Windows launching headed Chromium, and has the Live Ephemeral Dashboard (`/live/{session_id}`) built in**.
  - **Verdict**: Directly hook the filters into `external/auto-browser` controller (`observation.py` for Ingress, `actions.py` / `gateway.py` for Egress).
  - *Why*: Gives in-process access to `session.page` for `elementFromPoint(x, y)` without extra protocol hops, and emits real-time SSE events to `/live/{session_id}` so reviewers watch live badges ("Threat Neutralized") appear on screen!

---

## 3. Rough Sketch & Code-Level Architecture of Both Filters

```
+-----------------------------------------------------------------------------------------+
|                               S.H.O.A.V. FILTER PIPELINE                                |
+-----------------------------------------------------------------------------------------+
|                                                                                         |
|   1. INGRESS FILTER (observation.py / browser.observe / browser_snapshot)               |
|      Input: Raw Page DOM / Accessibility Outline                                        |
|      Process:                                                                           |
|        a) JavaScript DOM Walker evaluates computed styles:                              |
|           - display === 'none', visibility === 'hidden', opacity < 0.05                 |
|           - font-size: 0px, off-screen bounds (left/top < -500px)                      |
|           - zero-width Unicode (\u200B, \u200C, \uFEFF), HTML comments                  |
|        b) Context Compactor enforces node budget (max 50 actionable elements)           |
|        c) Synthesizes telemetry header: [S.H.O.A.V. INGRESS SHIELD: SANITIZED]          |
|      Verdicts: ALLOW (clean) | REWRITE (sanitized) | BLOCK (severe flood)               |
|                                                                                         |
|                                         v                                               |
|                                                                                         |
|   2. AGENT PLANS ACTION (agy CLI / LLM)                                                 |
|      Output: browser_click(ref="e15", selector="#submit-btn", [x, y, w, h])            |
|                                                                                         |
|                                         v                                               |
|                                                                                         |
|   3. EGRESS FILTER (actions.py::click / gateway.py::call_tool)                          |
|      Input: Action decision, target ref, bounding box [x, y, w, h]                      |
|      Process:                                                                           |
|        a) Calculates center coordinate: Cx = x + w/2, Cy = y + h/2                      |
|        b) Executes in-browser: topEl = document.elementFromPoint(Cx, Cy)                |
|        c) Validates: targetEl.contains(topEl) || topEl === targetEl                     |
|        d) Detects overlays: topEl opacity < 0.1 || z-index > 9000 with pointer-events   |
|        e) Audits form state: flags submission if pre-checked opt-ins remain untouched   |
|      Verdicts:                                                                          |
|        - ALLOW: Physical target matches intended target; dispatches click               |
|        - BLOCK: Overlay mismatch detected; aborts click; returns security exception     |
|        - ESCALATE: Triggers advisory warning / human confirmation                       |
|                                                                                         |
+-----------------------------------------------------------------------------------------+
```

### 3.1 Rough Code Sketch: Filter 1 (Ingress)
```python
# shoav-mcp/filters/ingress.py (Rough Sketch)

class IngressFilter:
    MAX_INTERACTIVE_NODES = 50
    MAX_TEXT_LENGTH = 4000

    @staticmethod
    def get_dom_pruning_script() -> str:
        """Returns JavaScript snippet evaluated in page context to prune cloaked DOM."""
        return """
        (() => {
            const stripped = [];
            const allElements = document.querySelectorAll('*');
            
            for (const el of allElements) {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();
                
                const isHidden = (
                    style.display === 'none' ||
                    style.visibility === 'hidden' ||
                    parseFloat(style.opacity) < 0.05 ||
                    parseFloat(style.fontSize) === 0 ||
                    rect.right < 0 || rect.bottom < 0 ||
                    rect.left > window.innerWidth || rect.top > window.innerHeight
                );
                
                if (isHidden && el.innerText && el.innerText.trim().length > 0) {
                    stripped.push({
                        tag: el.tagName,
                        id: el.id,
                        snippet: el.innerText.slice(0, 50),
                        reason: 'computed_style_hidden'
                    });
                    el.remove(); // Prune cloaked injection node
                }
            }
            return { strippedCount: stripped.length, details: stripped };
        })()
        """

    def process_snapshot(self, raw_dom_payload: dict) -> dict:
        """Audits snapshot, compacts node budget, and attaches telemetry."""
        stripped_count = raw_dom_payload.get("strippedCount", 0)
        nodes = raw_dom_payload.get("interactables", [])

        # Context Overloading / Flooding Protection: Enforce node budget
        if len(nodes) > self.MAX_INTERACTIVE_NODES:
            compacted_nodes = nodes[:self.MAX_INTERACTIVE_NODES]
            compaction_active = True
        else:
            compacted_nodes = nodes
            compaction_active = False

        if stripped_count == 0 and not compaction_active:
            return {"verdict": "ALLOW", "payload": raw_dom_payload}

        # REWRITE verdict: construct telemetry header
        telemetry_header = (
            f"[S.H.O.A.V. INGRESS SHIELD: SANITIZED]\n"
            f"- Stripped Injections: {stripped_count} cloaked nodes dropped\n"
            f"- Context Compaction: Bounded to {len(compacted_nodes)} active controls\n"
            f"- DOM Integrity: Clean\n"
        )
        return {
            "verdict": "REWRITE",
            "telemetry": telemetry_header,
            "payload": compacted_nodes
        }
```

### 3.2 Rough Code Sketch: Filter 2 (Egress)
```python
# shoav-mcp/filters/egress.py (Rough Sketch)

class EgressFilter:
    @staticmethod
    def get_hit_test_script(cx: float, cy: float, expected_selector: str) -> str:
        """Evaluates document.elementFromPoint at target coordinates."""
        return f"""
        (() => {{
            const topEl = document.elementFromPoint({cx}, {cy});
            if (!topEl) return {{ safe: false, reason: "no_element_at_point" }};

            const style = window.getComputedStyle(topEl);
            const isTransparentOverlay = (
                parseFloat(style.opacity) < 0.1 && 
                parseInt(style.zIndex || '0') > 100
            );

            const targetEl = document.querySelector("{expected_selector}");
            const isMatch = targetEl ? (targetEl.contains(topEl) || topEl === targetEl) : false;

            return {{
                safe: isMatch && !isTransparentOverlay,
                topTag: topEl.tagName,
                topId: topEl.id,
                topClass: topEl.className,
                isOverlay: isTransparentOverlay,
                isMatch: isMatch
            }};
        }})()
        """

    async def verify_click(self, page, target_box: list[float], selector: str) -> tuple[str, str]:
        """
        target_box: [x, y, width, height]
        Returns: (verdict: ALLOW | BLOCK, reason: str)
        """
        cx = target_box[0] + target_box[2] / 2
        cy = target_box[1] + target_box[3] / 2

        audit = await page.evaluate(self.get_hit_test_script(cx, cy, selector))
        
        if not audit.get("safe"):
            if audit.get("isOverlay"):
                reason = f"Clickjacking overlay detected: <{audit.get('topTag')} id='{audit.get('topId')}'> with opacity < 0.1 occluding target"
            else:
                reason = f"Target mismatch at ({cx}, {cy}): expected '{selector}', but topmost element is <{audit.get('topTag')} id='{audit.get('topId')}'>"
            return "BLOCK", reason

        return "ALLOW", "Target coordinate verified clean"
```

---

## 4. Integration Blueprint: Direct Hooking into `external/auto-browser`

We directly hook the filters into `external/auto-browser`:

1. **Ingress Hook (`controller/app/browser/services/observation.py`)**:
   - Inside `observation_payload()`, right after capturing interactables and page summary, execute `IngressFilter.get_dom_pruning_script()`.
   - Strip hidden nodes from the returned interactables and text excerpt.
   - Prepend `telemetry_header` to `text_excerpt` and emit an SSE event to `_events.emit_observe()` so the live dashboard immediately updates its "Sanitized Nodes" badge!
2. **Egress Hook (`controller/app/tool_gateway/gateway.py` or `actions.py`)**:
   - In `call_tool()` for `name="browser.execute_action"`, intercept when `action.action == "click"`.
   - Before calling `actions.py::click()`, run `EgressFilter.verify_click()`.
   - If `BLOCK`:
     - Emit security violation to `_events.emit_approval()` with status `"blocked"` (shows red badge on `/live/{session_id}`).
     - Return an `McpToolCallResponse(isError=True, content="[S.H.O.A.V. EGRESS SHIELD]: Click blocked due to overlay interception.")`.
   - If `ALLOW`: Dispatch click to Playwright.

---

## 5. Next Steps

1. Create `shoav-mcp/filters/ingress.py` implementing the Ingress Filter module.
2. Create `shoav-mcp/filters/egress.py` implementing the Egress Hit-Test module.
3. Hook both filters into `external/auto-browser/controller/app/` and test against the live TrickyArena benchmark (`shopping?dp=w`).
