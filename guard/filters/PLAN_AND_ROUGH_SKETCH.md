# S.H.O.A.V. Filter Architecture: Master Plan & Rough Sketch

## 1. Context, Dialogue Synthesis, & Evolution of Ideas

This document records the complete conceptual design, architectural trade-offs, and engineering blueprint for the deterministic filter engine powering S.H.O.A.V. (Shield for Hostile Operations & Agent Vulnerability).

### 1.1 Ideas Introduced by User
1. **The Primary Focus - The Tool (Hardened MCP)**:
   - The security mechanism must sit at the Model Context Protocol (MCP) browser layer.
   - Must be **completely deterministic** (no LLM in the loop for the core security decision).
   - Split into two physical filters:
     - **Ingress Filter**: Audits incoming browser observations/snapshots (CSS opacity, display hiding, dummy diffs, and context overloading). Can emit three verdicts: `ALLOW`, `BLOCK`, or `REWRITE`. When rewriting or blocking, it must provide structured explanatory context to the agent so the agent understands why the DOM was altered or blocked.
     - **Egress Filter**: Audits outgoing agent actions (e.g. `browser_click`). Physically verifies what the action will actually trigger in the live DOM (hit-testing, overlay mismatch, form state verification). Can emit `ALLOW`, `BLOCK`, or `ESCALATE`.
2. **Context Overloading as an Attack Vector**:
   - A newly surfaced, critical attack vector: hostile sites deliberately flood the context window with massive filler DOM trees, repetitive tags, or rapid dummy diff mutations to dilute agent attention, displace system prompts ("lost in the middle"), or burn token quotas. The ingress filter must actively compact and prune this bloat.
3. **The Role of Fast Specialized Models (Jev & Embeddings)**:
   - Can we leverage local embedding models or specialized "System One" decision models like **Jev** (TypeSafe AI, released Sept 15, 2026: 70-500ms, non-autoregressive, 200-400x cheaper than LLMs)?
   - Using local embeddings for vector cosine similarity against dark pattern phrasing is 100% deterministic (mathematical vector math, zero generation, zero prompt injection risk).
   - Running something like Jev or the open-source `JevEmbed` framework locally would be a notable novelty.
4. **Agent Gaslighting / Fault Injection / Tool Misattribution (User Insight)**:
   - A critical, agent-specific attack: A hostile or malfunctioning site deliberately deflects user inputs (focus stealing, silent event interception) or renders fake system/tool error popups.
   - The agent is tricked into believing the error is within its own tool or code rather than on the malicious page.
   - The agent's ReAct self-correction loop is hijacked: it begins "fixing" a non-existent tool error by following malicious recovery instructions or retrying with sensitive fallbacks.
5. **The Three-Pillar Product Vision**:
   - **Pillar 1 (The Tool)**: The Hardened MCP Proxy with dual deterministic filters.
   - **Pillar 2 (The Skill)**: A standalone educational and operational skill (`skills/shoav-guard/`) covering dark patterns, human cognitive heuristics (loss aversion, default bias), agent reasoning over-rationalization, and advisory second-opinion classifiers. Teammate owns this skill.
   - **Pillar 3 (The Subagent / Harness)**: A future lightweight, least-privilege delegate agent that can *only* browse, screenshot, edit Markdown files, create/edit empty files, edit images, and move files relatively within its directory (zero shell execution).
6. **Anti-Benchmark Bias**:
   - We must not bias our detector or tune our rules to a specific benchmark (like TrickyArena). We bias against real-world malicious actor techniques and empirical security literature. TrickyArena serves only as an un-rigged external testbed.

### 1.2 Assistant Evaluation & Technical Synthesis
* **On Ingress `REWRITE` vs `BLOCK`**: Outright blocking legitimate pages that contain slight CSS quirks causes the ProtectAI failure mode (where task utility crashed from 83% to 41%). Deterministic `REWRITE` (sanitizing invisible nodes and compacting the tree) is vastly superior because it destroys the exploit while preserving 100% of task utility.
* **On Attention Dilution ($A = \text{Softmax}(QK^T/\sqrt{d_k})$)**: Context flooding degrades attention mathematically. Bounding the node budget to top-k interactive elements (e.g., max 50 candidates, <4k tokens) guarantees that system instructions remain within the high-salience primacy/recency attention zone.
* **On Ingress & Egress Contextual Feedback**: The agent must receive structured telemetry headers (`[SECURITY TELEMETRY: Ingress Sanitized]`) so it remains informed of why specific elements were pruned, preventing disorientation.
* **On Jev & Embeddings**: Vector cosine similarity against offline reference centroids is strictly deterministic. JevEmbed allows binding local sentence transformers to typed decision schemas at 30ms latency with zero API cost.
* **On Agent Gaslighting & Tool Misattribution (User Insight)**: Malicious pages exploit the agent's ReAct self-correction reflex by rendering fake tool error banners or deflecting keystroke focus. The agent assumes its tool malfunctioned and triggers harmful self-repair fallbacks. S.H.O.A.V. neutralizes this on both fronts: Ingress quaranteens synthetic system errors in the DOM, while Egress verifies input focus integrity (`document.activeElement` and target value propagation) to authoritatively validate that the tool worked and flag website tampering.

---

## 2. The Architectural Dilemma: Internal MCP Modification vs. External Stdio Proxy

The user posed a foundational architectural question:
> *"Should we change the internals of the cloned MCP (`external/auto-browser`) or should we work with an external proxy wrapper?"*

Here is the deep-dive analysis of both options:

```
+-----------------------------------------------------------------------------------------+
| OPTION A: INTERNAL GATEWAY PATCH                        OPTION B: STDIO REVERSE PROXY   |
| (Modify external/auto-browser source)                  (Standalone shoav_proxy.py)      |
+-----------------------------------------------------------------------------------------+
|                                                         [ agy CLI / Any MCP Client ]    |
|   [ agy CLI ] -> [ HTTP / Docker :8000/mcp ]                          | stdio (JSON-RPC)|
|                        |                                              v                 |
|   [ controller/app/tool_gateway/gateway.py ]            [ shoav_proxy.py (Middleware) ] │
|   └─> PATCH McpToolGateway.call_tool()                  ├── Ingress Filter (prune/clean)│
|       ├── Inspects arguments & live session.page        └── Egress Filter (hit-test)    |
|       └── Calls actions.py / observation.py                           | stdio (JSON-RPC)|
|                                                                       v                 |
|                                                         [ @playwright/mcp or auto-br ]  |
|                                                                       |                 |
|                                                                       v                 |
|                                                         [ Playwright Chromium Engine ]  |
+-----------------------------------------------------------------------------------------+
```

### Option A: Internal Modification of `external/auto-browser`
* **How it works**: We directly modify `external/auto-browser/controller/app/tool_gateway/gateway.py` (`call_tool()`), `actions.py`, and `observation.py`.
* **Advantages**:
  1. *Direct Page Access*: Inside `gateway.py`, we already have `session = await self.manager.get_session(session_id)` and direct access to `session.page`. We can call `await session.page.evaluate(...)` in-process without an extra protocol hop.
  2. *Witness Schema Reuse*: Auto Browser already defines `WitnessConcern` (`code`, `severity`, `enforced`, `details`) in `witness.py`. We can natively populate these audit records.
* **Severe Drawbacks & Risks**:
  1. *Heavy Execution Stack*: Requires running the full Auto Browser stack (Docker Compose or manual Python 3.12 uvicorn controller + Node `browser-node` sidecar).
  2. *Raw Mouse Event Vulnerability*: Auto Browser's `actions.py::click()` resolves element bounding-box centers and dispatches raw `mouse.move(x, y)` and `mouse.down()`. It bypasses Playwright's native actionability checks. To fix this internally, we would have to rewrite their action dispatcher.
  3. *Git & Upstream Friction*: Modifying git-ignored third-party code in `external/` risks merge conflicts and is harder to package as an independent deliverable.

### Option B: External Stdio Reverse Proxy (`shoav_proxy.py`)
* **How it works**: A standalone Python process that sits between `agy` and the browser MCP server (e.g. `bun x @playwright/mcp@latest --image-responses=allow --snapshot-boxes`). It intercepts standard input and output (JSON-RPC 2.0).
* **Advantages**:
  1. *Universal Compatibility*: Works with *any* agent (`agy`, Claude Desktop, Cursor) and *any* browser MCP server without changing a single line of third-party source code.
  2. *Zero Docker Overhead*: Runs natively on Windows 11 with Node/Bun and Python. Instant startup, zero container networking bugs.
  3. *Clean Packaging*: Lives cleanly in our own directory (`shoav-mcp/`), fully version-controlled in git.
* **The Challenge**:
  - The proxy receives JSON-RPC tool calls. For Ingress (`browser_snapshot`), it can inspect and rewrite the response JSON directly. But for Egress (`browser_click`), to run `document.elementFromPoint(x, y)`, the proxy needs a mechanism to evaluate JavaScript in the browser. In `@playwright/mcp`, this can be done via `browser_evaluate` or by attaching a lightweight CDP/Playwright handle.

### The Recommended Decision: The Unified Adapter Pattern (Golden Path)
We should **not** lock ourselves into either extreme. Instead:
1. Implement the core filters as **pure, framework-agnostic Python modules** in `shoav-mcp/filters/`:
   - `shoav-mcp/filters/ingress.py`: Pure DOM/text sanitizer, node compactor, and telemetry formatter.
   - `shoav-mcp/filters/egress.py`: Pure geometric hit-tester, coordinate calculator, and overlay checker.
2. Provide **two lightweight adapters**:
   - `shoav-mcp/proxy.py`: Stdio MCP reverse proxy for `agy` + `@playwright/mcp` (primary demo vehicle).
   - `shoav-mcp/gateway_patch.py`: A clean decorator/subclass for `McpToolGateway.call_tool()` if the teammate or other users want to run `external/auto-browser`.
*Why this wins*: The core logic is written once, 100% unit-tested, and works under both runtimes!

---

## 3. Rough Sketch of Filter Mechanics

### 3.1 Ingress Filter Pipeline

```
Raw Snapshot Response from Browser MCP (HTML / Accessibility Tree / Interactables)
                                │
                                ▼
               [ Step 1: Token & Node Budget Check ]
                 Is node count > 150 or tokens > 4,000?
                 ├─ YES: Trigger Compaction (drop layout divs, SVGs, non-interactive tags)
                 └─ NO: Proceed to Step 2
                                │
                                ▼
               [ Step 2: Computed Style & Visibility Probe ]
                 For each text-bearing or interactive node:
                 - Is display === 'none' or visibility === 'hidden'?
                 - Is opacity < 0.05 or fontSize === 0?
                 - Is bounding box off-screen (left < -500px)?
                 - Does it contain zero-width Unicode or comment prompt tags?
                 ├─ FOUND: Mark node for excision; increment stripped_count
                 └─ CLEAN: Retain node
                                │
                                ▼
               [ Step 3: Fast Semantic Verification (Optional Jev/Embedding) ]
                 Compare interactive text against known dark pattern centroids.
                 - Cosine similarity > 0.85 on confirmshaming/scarcity cluster?
                 ├─ YES: Attach Advisory Warning Tag to element
                 └─ NO: Keep neutral
                                │
                                ▼
               [ Step 4: Verdict Synthesis ]
                 - IF stripped_count == 0 AND uncompacted -> ALLOW (forward raw)
                 - IF stripped_count > 0 OR compacted -> REWRITE (return sanitized DOM + Telemetry)
                 - IF mutation_rate > 50/sec OR payload > 10MB -> BLOCK (return diagnostic error)
```

#### Exact Ingress Telemetry Contract:
```yaml
[S.H.O.A.V. INGRESS SHIELD: SANITIZED]
status: rewritten
stripped_injections: 3
  - node_id: "e12" (display:none - prompt hijack payload dropped)
  - node_id: "e29" (left: -9999px - off-screen injection dropped)
context_compaction:
  raw_nodes: 1420
  compacted_nodes: 42
  token_reduction: "84%"
advisory_flags:
  - ref: "e15" (heuristic: pre-selected add-on toggle detected)
```

---

### 3.2 Egress Filter Pipeline

```
Agent Requests Action: browser_click(ref="e15", selector="#submit-btn")
                                │
                                ▼
               [ Step 1: Target Resolution & Coordinate Calculation ]
                 Retrieve target bounding box: [x, y, width, height]
                 Calculate center point: Cx = x + width/2, Cy = y + height/2
                                │
                                ▼
               [ Step 2: In-Browser Hit-Test (elementFromPoint) ]
                 Execute: topElement = document.elementFromPoint(Cx, Cy)
                                │
                                ▼
               [ Step 3: Topmost Identity & Overlay Validation ]
                 - Does targetElement.contains(topElement) || topElement === targetElement?
                 - Does topElement have opacity < 0.1?
                 - Does topElement have z-index > 9000 with pointer-events: auto?
                 ├─ MISMATCH / OVERLAY DETECTED:
                 │    VERDICT: BLOCK
                 │    Action: Abort tool call immediately.
                 │    Return: isError: true with physical coordinate telemetry.
                 └─ TARGET MATCHES TOP ELEMENT:
                      Proceed to Step 4
                                │
                                ▼
               [ Step 4: Form State Audit ]
                 - Is the action submitting a form containing unprompted pre-checked opt-ins?
                 ├─ YES: VERDICT: ESCALATE (warn agent before dispatch)
                 └─ NO: Proceed to Step 5
                                │
                                ▼
                [ Step 5: Input & Focus Integrity Verification (Anti-Gaslighting) ]
                  For text input / fill actions:
                  - Does document.activeElement match the target element?
                  - Did targetElement.value update with the provided string?
                  ├─ NO (Focus stolen or input diverted elsewhere):
                  │    VERDICT: BLOCK
                  │    Action: Abort tool call immediately.
                  │    Return: isError: true with Focus Deflection Telemetry.
                  └─ YES: VERDICT: ALLOW (dispatch click/type to browser engine)
```

#### Exact Egress Error Contract on Block:
```json
{
  "isError": true,
  "content": [{
    "type": "text",
    "text": "[S.H.O.A.V. EGRESS SHIELD: ACTION BLOCKED]\nViolation: Clickjacking / Overlay Interception detected.\nIntended Target: <button id='submit-btn'> (ref=e15) at (450, 620)\nActual Topmost Element: <div class='transparent-overlay' style='opacity:0; z-index:99999'>\nExecution was aborted before pointer dispatch. The target is physically occluded."
  }]
}
```

#### Egress Telemetry on Input Deflection / Agent Gaslighting Block:
```json
{
  "isError": true,
  "content": [{
    "type": "text",
    "text": "[S.H.O.A.V. EGRESS SHIELD: INPUT HIJACK BLOCKED]\nViolation: Input Focus Deflection / Synthetic Gaslighting detected.\nIntended Input Field: <input id='search-box' name='q'>\nActual Active Element: <input id='hidden-telemetry-sniffer' style='opacity:0'>\nDiagnosis: The target website hijacked input focus to misroute data and simulate tool failure. Tool execution is intact; website tamper detected."
  }]
}
```

---

## 4. Open Questions & Implementation Tasks

1. **Egress Hit-Test Execution Bridge in Proxy Mode**:
   - When running as `shoav_proxy.py` over `@playwright/mcp`, how does the proxy trigger `document.elementFromPoint` before allowing `browser_click`?
   - *Resolution*: `@playwright/mcp` exposes `browser_evaluate` (or CDP session). Before forwarding `browser_click`, the proxy issues an internal `browser_evaluate` request with our hit-test JS snippet, reads the boolean verdict, and then either forwards the original click or returns the block error.
2. **Local Jev / JevEmbed Integration**:
   - Can we package `JevEmbed` with an ultra-lightweight sentence transformer (`all-MiniLM-L6-v2`, 80MB) inside `shoav-mcp/`?
   - *Resolution*: Yes. We will make it an optional acceleration module (`shoav-mcp/filters/fast_classifier.py`). If installed, it provides 20ms local semantic scoring; if omitted, the deterministic structural core functions with zero dependencies.
3. **Preserving Form State History**:
   - The Ingress filter will cache the initial state of forms (`checked`, `value`) upon navigation so the Egress filter can diff form state prior to submission.
