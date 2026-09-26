"""JS snippets the ingress engine needs evaluated in-page.

Nothing in this file runs here — these are string constants for a future
connector (browser.eval_js today, or a direct page.evaluate() once wired
into Auto Browser's internals per INTEGRATION.md) to execute and hand back
as plain dicts/lists. Keeping the JS out of the decision logic is what makes
rules.py testable without a browser: feed it the JS's *output* shape
directly as a fixture.

Design choice vs. the original rough sketch in PLAN_AND_ROUGH_SKETCH.md:
that sketch's script both inspects AND mutates the page (`el.remove()`)
in one pass, so the only thing Python ever sees is a stripped count. This
version reports facts only — the Python side decides what to strip — per
INTEGRATION.md's own recommendation for style_probe ("WITHOUT pre-filtering
... we want the invisible ones surfaced, not silently dropped"). This keeps
the mutation decision (which needs the benign-hidden-marker allowlist,
keyword heuristics, etc.) in testable Python instead of buried in a page.evaluate string.
"""

# Reports checkbox/switch/radio state with label text and a stable ref.
# Each entry: {element_id, tag, type, checked, label, ref}.
# element_id is data-operator-id when present, else the DOM id or null.
# ref uses the SAME window.__shoavSeq stamping as the interactables script
# (op-s<N> in base36, stored on data-operator-id via dataset.operatorId),
# so a form control ref equals the element_id the agent clicks. Elements
# that already carry data-operator-id keep it; only unstamped elements
# advance the shared counter. This sharing is what makes mark_touched
# correlation work across observe and egress.
# Label resolution order: aria-label, associated label[for=id], closest
# wrapping <label>, aria-labelledby text, name attribute, value, else "".
FORM_STATE_SCRIPT = """
(() => {
    window.__shoavSeq = window.__shoavSeq || 0;
    const out = [];
    const seen = new Set();
    const labelFor = (el) => {
        const aria = (el.getAttribute && el.getAttribute('aria-label')) || '';
        if (aria.trim()) return aria.trim().slice(0, 200);
        const id = el.id || '';
        if (id) {
            const lab = document.querySelector('label[for="' + id.replace(/"/g, '') + '"]');
            if (lab && lab.innerText && lab.innerText.trim()) return lab.innerText.trim().slice(0, 200);
        }
        const wrap = el.closest ? el.closest('label') : null;
        if (wrap && wrap.innerText && wrap.innerText.trim()) return wrap.innerText.trim().slice(0, 200);
        const labelledBy = (el.getAttribute && el.getAttribute('aria-labelledby')) || '';
        if (labelledBy.trim()) {
            const parts = labelledBy.split(/\\s+/).map(ref => {
                const n = document.getElementById(ref);
                return n && n.innerText ? n.innerText.trim() : '';
            }).filter(Boolean);
            if (parts.length) return parts.join(' ').slice(0, 200);
        }
        const name = el.getAttribute ? (el.getAttribute('name') || '') : '';
        if (name.trim()) return name.trim().slice(0, 200);
        const val = (el.value !== undefined && el.value !== null) ? String(el.value) : '';
        if (val.trim()) return val.trim().slice(0, 200);
        if (el.innerText && el.innerText.trim()) return el.innerText.trim().slice(0, 200);
        return '';
    };
    const stableRef = (el, elementId) => {
        if (elementId) return elementId;
        if (el.dataset && el.dataset.operatorId) return el.dataset.operatorId;
        window.__shoavSeq = (window.__shoavSeq || 0) + 1;
        const ref = 'op-s' + window.__shoavSeq.toString(36);
        try { if (el.dataset) el.dataset.operatorId = ref; } catch (e) {}
        return ref;
    };
    const push = (el, type, checked) => {
        if (seen.has(el)) return;
        seen.add(el);
        const elementId = (el.getAttribute && el.getAttribute('data-operator-id')) || el.id || null;
        out.push({
            element_id: elementId,
            tag: el.tagName,
            type: type,
            checked: !!checked,
            label: labelFor(el),
            ref: stableRef(el, elementId),
        });
    };
    const inputs = document.querySelectorAll('input[type="checkbox"], input[type="radio"]');
    for (const el of inputs) {
        push(el, (el.type || 'checkbox').toLowerCase(), !!el.checked);
    }
    const roles = document.querySelectorAll('[role="checkbox"], [role="switch"], [role="radio"]');
    for (const el of roles) {
        if (seen.has(el)) continue;
        const role = (el.getAttribute('role') || 'checkbox').toLowerCase();
        const ariaChecked = (el.getAttribute('aria-checked') || '').toLowerCase();
        push(el, role, ariaChecked === 'true');
    }
    return out;
})()
"""
# Walks ALL elements that own a direct non-empty text node (not only
# data-operator-id ones) and reports raw style/geometry facts, no filtering.
# textContent is used because display:none hides innerText. Hidden state is
# computed through the ancestor chain: display none if any ancestor is none,
# visibility hidden if any ancestor is hidden, opacity as the product up the
# chain. ref is data-operator-id when present, else a generated
# "path:body>div:nth-of-type(2)>span" selector path.
STYLE_PROBE_SCRIPT = """
(() => {
    const results = [];
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'HEAD', 'TITLE', 'META', 'LINK', 'BASE']);
    const MAX_RESULTS = 2000;

    const pathFor = (el) => {
        const parts = [];
        let cur = el;
        while (cur && cur.nodeType === 1 && cur !== document.documentElement) {
            const tag = cur.tagName.toLowerCase();
            if (cur === document.body) { parts.unshift(tag); break; }
            let idx = 1;
            let sib = cur.previousElementSibling;
            while (sib) { if (sib.tagName === cur.tagName) idx++; sib = sib.previousElementSibling; }
            parts.unshift(tag + ':nth-of-type(' + idx + ')');
            cur = cur.parentElement;
        }
        return 'path:' + parts.join('>');
    };

    const effectiveStyle = (el) => {
        const own = window.getComputedStyle(el);
        let display = own.display;
        let visibility = own.visibility;
        let opacity = 1;
        for (let cur = el; cur && cur.nodeType === 1; cur = cur.parentElement) {
            const st = window.getComputedStyle(cur);
            if (st.display === 'none') display = 'none';
            if (st.visibility === 'hidden' || st.visibility === 'collapse') visibility = 'hidden';
            const o = parseFloat(st.opacity);
            if (!isNaN(o)) opacity *= o;
        }
        return { display, visibility, opacity, fontSize: parseFloat(own.fontSize) };
    };

    const all = document.querySelectorAll('*');
    for (const el of all) {
        if (results.length >= MAX_RESULTS) break;
        if (SKIP.has(el.tagName)) continue;
        let own = '';
        for (const child of el.childNodes) {
            if (child.nodeType === 3) own += child.nodeValue;
        }
        const text = own.trim();
        if (!text) continue;
        const eff = effectiveStyle(el);
        const rect = el.getBoundingClientRect();
        results.push({
            ref: el.getAttribute('data-operator-id') || pathFor(el),
            tag: el.tagName,
            class_name: (typeof el.className === 'string' ? el.className : '') || '',
            text_snippet: text.slice(0, 200),
            display: eff.display,
            visibility: eff.visibility,
            opacity: eff.opacity,
            font_size: eff.fontSize,
            rect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom },
            viewport,
        });
    }
    return results;
})()
"""

# Installs a page-lifetime MutationObserver that counts DOM mutations.
# Idempotent: reinstalling disconnects the previous observer and restarts
# the count and clock. Returns {installed: true, started_at: <ms epoch>}.
# No filtering here; the Python rate helper decides flood vs normal.
MUTATION_OBSERVER_INSTALL_SCRIPT = """
(() => {
    try {
        if (window.__shoavMutObserver) { window.__shoavMutObserver.disconnect(); }
    } catch (e) {}
    window.__shoavMutCount = 0;
    window.__shoavMutStart = Date.now();
    const target = document.documentElement || document.body;
    if (!target) return { installed: false };
    window.__shoavMutObserver = new MutationObserver((mutations) => {
        window.__shoavMutCount += mutations.length;
    });
    window.__shoavMutObserver.observe(target, {
        childList: true, subtree: true, attributes: true, characterData: true,
    });
    return { installed: true, started_at: window.__shoavMutStart };
})()
"""

# Reads the counter started by MUTATION_OBSERVER_INSTALL_SCRIPT.
# Returns {count, seconds, rate} where rate is mutations per second.
# If the observer was never installed, returns {count: 0, seconds: 0, rate: 0}.
MUTATION_OBSERVER_READ_SCRIPT = """
(() => {
    const count = window.__shoavMutCount || 0;
    const start = window.__shoavMutStart || Date.now();
    const seconds = (Date.now() - start) / 1000;
    return { count: count, seconds: seconds, rate: seconds > 0 ? count / seconds : 0 };
})()
"""

# Raw flood probe (Target 4, F-E): element count plus text volume BEFORE any
# caps. No filtering, no truncation; the Python flood rule decides. Returns
# {element_count, text_chars} where text_chars is the length of
# document.body.innerText (0 when body is missing). Run before compaction so
# a filler flood cannot hide behind the node budget.
FLOOD_PROBE_SCRIPT = """
(() => {
    let elementCount = 0;
    try { elementCount = document.querySelectorAll('*').length; } catch (e) { elementCount = 0; }
    let textChars = 0;
    try { textChars = (document.body && document.body.innerText ? document.body.innerText.length : 0); } catch (e) { textChars = 0; }
    return { element_count: elementCount, text_chars: textChars };
})()
"""
