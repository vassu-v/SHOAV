# S.H.O.A.V. Deterministic MCP Guard: Core Targets & Engineering Goals

This document specifies the exact subset of dark patterns and adversarial web manipulation techniques that are **computationally and deterministically solvable** at the browser protocol / MCP layer without relying on an LLM or psychological interpretation.

Psychological, framing, and linguistic manipulation patterns (confirmshaming, fake urgency countdowns, social proof, trick wording) are intentionally routed to the **Cognitive Vigilance Skill** (`skills/shoav-guard/`).

---

## 1. Primary Deterministic Targets (The Computational Core)

```
+-----------------------------------------------------------------------------------------+
|                               DETERMINISTIC TARGET MATRIX                               |
+-----------------------------------------------------------------------------------------+
| Target Family               | Physical / DOM Mechanism      | Deterministic Check       |
+-----------------------------+-------------------------------+---------------------------+
| 1. Hidden / Invisible Text   | display:none, opacity:0,      | Computed style inspection |
|    (Ingress Prompt Hijack)  | font-size:0, off-screen       | bounding rect calculation |
+-----------------------------+-------------------------------+---------------------------+
| 2. Clickjacking & Overlays  | Transparent div overlay,      | document.elementFromPoint |
|    (Egress Target Mismatch) | z-index layering, pointer fake| at bounding-box center    |
+-----------------------------+-------------------------------+---------------------------+
| 3. Pre-Checked States       | checked=true on opt-ins,      | Initial DOM form-state    |
|    (Sneaking / Data Sharing)| aria-checked=true toggles     | snapshot before action    |
+-----------------------------+-------------------------------+---------------------------+
| 4. Context Overloading      | Massive repetitive DOM filler,| Node budget bounding,     |
|    & Dummy Diffs (Ingress)  | rapid irrelevant mutations    | subtree compaction        |
+-----------------------------+-------------------------------+---------------------------+
| 5. Cart Sneaking (Egress)   | Unsolicited item injection    | Action-to-state causal    |
|                             | into transaction session      | diffing                   |
+-----------------------------+-------------------------------+---------------------------+
```

---

## 2. Target Specifications

### Target 1: Hidden & Cloaked Ingress Injections
* **Why it is deterministic**: Text is either rendered to the viewport or it is not. No language interpretation is required to determine that an element has `opacity: 0` or sits at `left: -9999px`.
* **Triggers**:
  - `getComputedStyle(el).display === 'none'`
  - `getComputedStyle(el).visibility === 'hidden'`
  - `parseFloat(getComputedStyle(el).opacity) < 0.05`
  - `parseFloat(getComputedStyle(el).fontSize) === 0`
  - Bounding box outside viewport: `rect.right < 0 || rect.bottom < 0 || rect.left > window.innerWidth || rect.top > window.innerHeight`
  - Zero-width Unicode characters (`\u200B`, `\u200C`, `\u200D`, `\uFEFF`)
  - Raw HTML comments (`<!-- ... -->`) and `<meta>` prompt injections.
* **MCP Action**: Prune / rewrite the DOM snapshot before the agent receives it.

### Target 2: Clickjacking & Target Coordinate Mismatch
* **Why it is deterministic**: Physical geometry dictates which element receives pointer dispatch. If element $A$ is targeted, but the browser compositor resolves element $B$ at the target coordinates $(x, y)$, a physical obstruction exists.
* **Triggers**:
  - Agent requests `browser_click` on selector $S$ or ref $R$ with bounding box $[x, y, w, h]$.
  - Compute target center: $C_x = x + w/2$, $C_y = y + h/2$.
  - Evaluate `topEl = document.elementFromPoint(Cx, Cy)`.
  - Condition: `!targetEl.contains(topEl) && topEl !== targetEl`.
  - Secondary check: `parseFloat(getComputedStyle(topEl).opacity) < 0.1` or `topEl` has `z-index > 9000` with `pointer-events: auto`.
* **MCP Action**: Abort the tool call immediately; return `isError: true` with physical overlay telemetry.

### Target 3: Pre-Checked / Default-On Manipulative Form State
* **Why it is deterministic**: A checkbox or toggle is a boolean DOM property (`el.checked === true` or `el.getAttribute('aria-checked') === 'true'`).
* **Triggers**:
  - Checkboxes, radio buttons, or toggle switches delivered with initial state `checked === true` that correspond to opt-in services, recurring fees, or third-party data-sharing permissions without explicit prior user direction.
* **MCP Action**: Ingress flags pre-checked defaults; Egress alerts if form submission is initiated without user interaction on that toggle.

### Target 4: Context Overloading & Dummy DOM Diffs
* **Why it is deterministic**: Token length and node counts are scalar numbers.
* **Triggers**:
  - DOM snapshot exceeds maximum node ceiling (e.g. $> 150$ interactive elements or $> 4,000$ tokens).
  - Rapid background mutations ($> 50$ DOM mutations/second unrelated to user actions).
* **MCP Action**: Deterministic subtree pruning: strip non-interactive layout containers, discard `<script>`, `<style>`, `<svg>`, and retain only prioritized interactive candidates (`a`, `button`, `input`, `select`).

### Target 5: Cart Sneaking
* **Why it is deterministic**: Set delta arithmetic. If cart item set at $T_1$ contains item $I_{new}$ which was not present at $T_0$, and no click event was targeted at $I_{new}$'s add-button between $T_0$ and $T_1$, item $I_{new}$ was sneaked.
* **MCP Action**: Reject checkout action; surface sneaked item identity.

---

## 3. Deliberate Exclusions (Handled Exclusively by the Skill)

The following patterns are **not** solved in this MCP because they depend on natural language semantics and psychological framing:
* **Confirmshaming**: Symmetrical buttons where manipulation is pure copy ("No thanks, I hate saving money").
* **Bait and Switch**: Contextual mismatch between advertised intent and subsequent demands.
* **Fake Urgency / Countdowns**: Clocks and countdown numbers that look structurally valid.
* **Double Negatives**: Syntax comprehension ("Do NOT uncheck if you wish NOT to receive...").
* **Aesthetic Manipulation**: Highlighting "Best Value" via colors and styling without geometric obstruction.
