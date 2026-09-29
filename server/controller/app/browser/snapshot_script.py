"""In-page tree builder for browser.snapshot.

Playwright 1.62 removed page.accessibility, and Locator.aria_snapshot() output is far too big
to hand to a model (459k chars for one Wikipedia article). This script walks the DOM once,
computes role, name and visibility itself, prunes generic wrappers and returns compact text
lines. Interactive elements get the same `data-operator-id` that observe's interactables use,
so a ref works as `element_id` in execute_action with no pipeline change.

Deterministic: no randomness, no time. New refs come from a per-page counter
(`op-s1`, `op-s2`, ...); elements that already have an id keep it.
"""

from __future__ import annotations

SNAPSHOT_SCRIPT = r"""
(opts) => {
  const ALL = opts.include === 'all';
  const SCOPED = !!opts.selector;
  const MAX_DEPTH = opts.depth;
  const VIEWPORT_ONLY = !!opts.viewportOnly;
  const RUN_TEXT = ALL ? 1000 : 240;
  const NAME_MAX = 80;
  let ROW_CAP = ALL ? 100 : 25;
  const stats = {nodes: 0, interactive: 0, hidden: 0, outside_viewport: 0, tables: 0, deeper_omitted: 0, iframes: 0};
  const vw = window.innerWidth, vh = window.innerHeight;
  const sx = window.scrollX, sy = window.scrollY;
  let seq = window.__shoavSeq || 0;

  const SKIP = new Set(['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','HEAD','META','LINK','SVG','CANVAS','VIDEO','AUDIO','MAP','AREA','DATALIST','OPTION','OPTGROUP','BR','WBR']);
  const INTERACTIVE = new Set(['link','button','textbox','searchbox','checkbox','radio','combobox','listbox','tab','menuitem','menuitemcheckbox','menuitemradio','switch','slider','spinbutton','treeitem','clickable']);
  const KEEP_BLOCK = new Set(['heading','list','listitem','paragraph','blockquote','pre','navigation','main','banner','contentinfo','complementary','search','form','dialog','alertdialog','alert','status','tablist','toolbar','menu','region','group']);
  const NAMED_ONLY = new Set(['region','group']);
  const LABELS = {navigation:'nav', banner:'header', contentinfo:'footer', complementary:'aside', paragraph:'p', listitem:'-', blockquote:'quote'};

  const norm = (s) => String(s == null ? '' : s).replace(/\s+/g, ' ').trim();
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s);
  const cs = (el) => window.getComputedStyle(el);

  function hiddenKind(el, style, rect) {
    if (style.display === 'none') return 'hidden';
    if (style.visibility === 'hidden' || style.visibility === 'collapse') return 'hidden';
    if (el.getAttribute('aria-hidden') === 'true' || el.hasAttribute('inert')) return 'hidden';
    if (style.opacity === '0') return 'hidden';
    if (parseFloat(style.fontSize) === 0) return 'hidden';
    if (style.display === 'contents') return null;
    if (rect.width === 0 && rect.height === 0) return 'zero';
    if (rect.width <= 1 && rect.height <= 1 && style.overflow !== 'visible') return 'hidden';
    if (rect.right + sx <= 0 || rect.bottom + sy <= 0) return 'hidden';
    if (parseFloat(style.textIndent) <= -500) return 'hidden';
    if (style.position === 'absolute' && style.clip === 'rect(0px, 0px, 0px, 0px)') return 'hidden';
    if (style.clipPath === 'inset(100%)') return 'hidden';
    return null;
  }
  function isHidden(el) {
    const st = cs(el);
    const k = hiddenKind(el, st, el.getBoundingClientRect());
    return k === 'hidden' || (k === 'zero' && el.children.length === 0);
  }

  function childNodesOf(el) {
    if (el.tagName === 'SLOT') {
      const assigned = el.assignedNodes({flatten: true});
      return assigned.length ? assigned : Array.from(el.childNodes);
    }
    return Array.from(el.shadowRoot ? el.shadowRoot.childNodes : el.childNodes);
  }

  function textOf(el, limit) {
    const parts = [];
    let len = 0;
    (function rec(n) {
      if (len > limit) return;
      if (n.nodeType === 3) {
        const t = n.nodeValue;
        if (t && t.trim()) { parts.push(t); len += t.length; }
        return;
      }
      if (n.nodeType !== 1) return;
      const tag = n.tagName;
      if (tag === 'BR') { parts.push(' '); return; }
      if (SKIP.has(tag)) return;
      const st = cs(n);
      const hk = hiddenKind(n, st, n.getBoundingClientRect());
      if (hk === 'hidden' || (hk === 'zero' && n.children.length === 0)) return;
      if (tag === 'IMG') {
        const a = n.getAttribute('alt');
        if (a && a.trim()) { parts.push(' ' + a + ' '); len += a.length; }
        return;
      }
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      const spaced = st.display.indexOf('inline') !== 0 || tag === 'LI' || tag === 'DT' || tag === 'DD';
      if (spaced) parts.push(' ');
      for (const c of childNodesOf(n)) rec(c);
      if (spaced) parts.push(' ');
    })(el);
    return norm(parts.join(''));
  }

  function refOf(el) {
    let id = el.getAttribute('data-operator-id');
    if (!id) {
      seq += 1;
      id = 'op-s' + seq.toString(36);
      el.setAttribute('data-operator-id', id);
    }
    return id;
  }

  function inputRole(el) {
    const t = (el.getAttribute('type') || 'text').toLowerCase();
    if (t === 'hidden') return 'hidden';
    if (t === 'checkbox') return 'checkbox';
    if (t === 'radio') return 'radio';
    if (t === 'submit' || t === 'button' || t === 'reset' || t === 'image' || t === 'file') return 'button';
    if (t === 'range') return 'slider';
    if (t === 'number') return 'spinbutton';
    if (t === 'search') return 'searchbox';
    return 'textbox';
  }

  function roleOf(el) {
    const tag = el.tagName;
    const explicit = norm(el.getAttribute('role')).split(' ')[0].toLowerCase();
    if (explicit && explicit !== 'presentation' && explicit !== 'none' && explicit !== 'generic') return explicit;
    if (explicit === 'presentation' || explicit === 'none') return '';
    switch (tag) {
      case 'A': return el.hasAttribute('href') ? 'link' : '';
      case 'BUTTON': case 'SUMMARY': return 'button';
      case 'INPUT': return inputRole(el);
      case 'TEXTAREA': return 'textbox';
      case 'SELECT': return (el.multiple || el.size > 1) ? 'listbox' : 'combobox';
      case 'H1': case 'H2': case 'H3': case 'H4': case 'H5': case 'H6': return 'heading';
      case 'NAV': return 'navigation';
      case 'MAIN': return 'main';
      case 'ASIDE': return 'complementary';
      case 'FORM': return 'form';
      case 'TABLE': return 'table';
      case 'UL': case 'OL': case 'MENU': return 'list';
      case 'LI': return 'listitem';
      case 'P': return 'paragraph';
      case 'BLOCKQUOTE': return 'blockquote';
      case 'PRE': return 'pre';
      case 'DIALOG': return 'dialog';
      case 'FIELDSET': return 'group';
      case 'SECTION': return (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby')) ? 'region' : '';
      case 'HEADER': return el.closest('article,aside,main,nav,section') ? '' : 'banner';
      case 'FOOTER': return el.closest('article,aside,main,nav,section') ? '' : 'contentinfo';
      case 'IMG': return 'img';
      case 'IFRAME': return 'iframe';
      default: break;
    }
    if (el.isContentEditable && el.getAttribute('contenteditable') !== null) return 'textbox';
    const ti = el.getAttribute('tabindex');
    if ((ti !== null && parseInt(ti, 10) >= 0) || el.hasAttribute('onclick')) return 'clickable';
    return '';
  }

  function labelText(el) {
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      const t = norm(by.split(/\s+/).map((id) => { const r = document.getElementById(id); return r ? textOf(r, 200) : ''; }).join(' '));
      if (t) return t;
    }
    return norm(el.getAttribute('aria-label'));
  }

  function accName(el, role) {
    let n = labelText(el);
    if (n) return n;
    const tag = el.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
      if (el.labels && el.labels.length) { n = textOf(el.labels[0], 200); if (n) return n; }
      const type = (el.getAttribute('type') || '').toLowerCase();
      if (type === 'submit' || type === 'button' || type === 'reset') { n = norm(el.value); if (n) return n; }
      if (type === 'image') { n = norm(el.getAttribute('alt')); if (n) return n; }
      n = norm(el.getAttribute('placeholder')) || norm(el.getAttribute('title'));
      if (n) return n;
      return norm(el.getAttribute('name')) || norm(el.id);
    }
    n = textOf(el, 300);
    if (n) return n;
    return norm(el.getAttribute('title'));
  }

  function hrefOf(el) {
    const raw = el.getAttribute('href');
    if (!raw) return '';
    if (raw.charAt(0) === '#' || raw.toLowerCase().indexOf('javascript:') === 0) return raw.slice(0, 30);
    try {
      const u = new URL(raw, document.baseURI);
      return clip(u.origin === location.origin ? u.pathname + u.search : u.href, 70);
    } catch (e) { return clip(raw, 70); }
  }

  function stateOf(el, role) {
    const s = [];
    if (role === 'checkbox' || role === 'radio' || role === 'switch' || role === 'menuitemcheckbox') {
      const c = el.checked !== undefined ? el.checked : el.getAttribute('aria-checked') === 'true';
      s.push(c ? 'checked' : 'unchecked');
    }
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') s.push('disabled');
    const ex = el.getAttribute('aria-expanded');
    if (ex !== null) s.push(ex === 'true' ? 'expanded' : 'collapsed');
    if (el.getAttribute('aria-selected') === 'true') s.push('selected');
    if (el.getAttribute('aria-current') && el.getAttribute('aria-current') !== 'false') s.push('current');
    if (role === 'textbox' || role === 'searchbox' || role === 'spinbutton') {
      const type = (el.getAttribute('type') || '').toLowerCase();
      const v = type === 'password' ? '' : norm(el.value !== undefined ? el.value : el.textContent);
      if (v) s.push('value="' + clip(v, 40) + '"');
      if (type === 'password') s.push('password');
    }
    if (role === 'combobox' && el.tagName === 'SELECT') {
      const o = el.selectedOptions && el.selectedOptions[0];
      if (o) s.push('value="' + clip(norm(o.textContent), 40) + '"');
    }
    return s;
  }

  function interactiveItem(el, role) {
    const item = {k: 'i', role, name: clip(accName(el, role), NAME_MAX), ref: refOf(el), state: stateOf(el, role)};
    if (role === 'link') item.href = hrefOf(el);
    stats.nodes += 1; stats.interactive += 1;
    return item;
  }

  function isDataTable(el) {
    const r = (el.getAttribute('role') || '').toLowerCase();
    if (r === 'presentation' || r === 'none') return false;
    if (el.querySelector('table')) return false;
    if (r === 'table' || r === 'grid') return true;
    return !!(el.querySelector('th') || el.querySelector('caption') || el.querySelector('thead'));
  }

  function cellRefs(cell) {
    const found = [];
    for (const c of cell.querySelectorAll('a[href],button,input,select,textarea,[role=button],[role=link]')) {
      if (c.tagName === 'INPUT' && (c.getAttribute('type') || '').toLowerCase() === 'hidden') continue;
      if (isHidden(c)) continue;
      found.push(c);
    }
    if (!found.length) return '';
    const ids = found.slice(0, 2).map(refOf);
    stats.interactive += found.length;
    return ' {' + ids.join(',') + (found.length > 2 ? ',+' + (found.length - 2) : '') + '}';
  }

  function tableItem(el, level) {
    stats.tables += 1;
    const cap = el.querySelector('caption');
    let name = labelText(el) || (cap ? textOf(cap, 200) : '');
    const rows = Array.from(el.rows || []);
    let maxCols = 0;
    for (const r of rows) maxCols = Math.max(maxCols, r.cells.length);
    const cellLimit = maxCols <= 2 ? 120 : (maxCols <= 3 ? 60 : 40);
    const colCap = 12;
    const out = [];
    let shown = 0, omitted = 0;
    for (const r of rows) {
      const rst = cs(r);
      if (rst.display === 'none' || rst.visibility === 'hidden') { stats.hidden += 1; continue; }
      if (shown >= ROW_CAP) { omitted += 1; continue; }
      const cells = [];
      let allTh = r.cells.length > 0;
      for (const c of Array.from(r.cells)) {
        if (c.tagName !== 'TH') allTh = false;
        if (cells.length >= colCap) continue;
        const cst = cs(c);
        if (cst.display === 'none' || cst.visibility === 'hidden' || c.getAttribute('aria-hidden') === 'true') { stats.hidden += 1; cells.push(''); continue; }
        cells.push(clip(textOf(c, cellLimit * 2), cellLimit) + cellRefs(c));
      }
      const extra = r.cells.length > colCap ? ' | …+' + (r.cells.length - colCap) + ' cols' : '';
      out.push((allTh ? 'head: ' : 'row: ') + cells.join(' | ') + extra);
      shown += 1;
    }
    stats.nodes += 1 + shown;
    return {k: 'tbl', name: clip(name, NAME_MAX), rows: out, omitted, nrows: rows.length, ncols: maxCols};
  }

  function isBlockDisplay(st) { return st.display.indexOf('inline') !== 0 && st.display !== 'contents'; }

  function walk(el, level) {
    const tag = el.tagName;
    if (SKIP.has(tag)) return [];
    const st = cs(el);
    const rect = el.getBoundingClientRect();
    const hk = hiddenKind(el, st, rect);
    if (hk === 'hidden') { stats.hidden += 1; return []; }
    if (hk === 'zero' && el.children.length === 0) {
      if (norm(el.textContent)) stats.hidden += 1;
      return [];
    }
    if (VIEWPORT_ONLY && rect.width > 0 && (rect.bottom < 0 || rect.top > vh || rect.right < 0 || rect.left > vw)) {
      stats.outside_viewport += 1; return [];
    }
    const role = roleOf(el);
    if (role === 'hidden') return [];
    if (role === 'iframe') {
      stats.iframes += 1; stats.nodes += 1;
      return [{k: 'g', text: 'iframe' + (el.getAttribute('title') ? ' "' + clip(norm(el.getAttribute('title')), 60) + '"' : '') + ' (content not included)'}];
    }
    if (role === 'img') {
      const alt = norm(el.getAttribute('alt'));
      // Scoped snapshots (e.g. selector "table.infobox") keep image alt text even
      // with include="interactive" so portrait/caption facts are not lost.
      return (ALL || SCOPED) && alt ? [{k: 'g', text: 'img "' + clip(alt, 100) + '"'}] : [];
    }
    if (tag === 'TABLE' && isDataTable(el)) {
      if (level >= MAX_DEPTH) { stats.deeper_omitted += 1; return [{k: 'deep'}]; }
      return [tableItem(el, level)];
    }
    if (INTERACTIVE.has(role)) return [interactiveItem(el, role)];

    const named = labelText(el) || (tag === 'FIELDSET' && el.querySelector('legend') ? textOf(el.querySelector('legend'), 100) : '');
    let isBlock = KEEP_BLOCK.has(role) && !(NAMED_ONLY.has(role) && !named);
    const generic = !isBlock;
    const blockish = isBlockDisplay(st);
    if (generic && ALL && blockish && el.children.length > 0 && tag !== 'BODY' && tag !== 'HTML') isBlock = true;
    if (isBlock && level >= MAX_DEPTH) { stats.deeper_omitted += 1; return [{k: 'deep'}]; }

    const flexParent = st.display.indexOf('flex') >= 0 || st.display.indexOf('grid') >= 0;
    const kids = [];
    let pendingSpace = false;
    for (const n of childNodesOf(el)) {
      if (n.nodeType === 3) {
        if (hk === 'zero') { if (n.nodeValue && n.nodeValue.trim()) stats.hidden += 1; continue; }
        const raw = n.nodeValue || '';
        const s = norm(raw);
        if (!s) {
          if (kids.length) kids[kids.length - 1].t = true;
          pendingSpace = true;
          continue;
        }
        const item = {k: 't', s, l: /^\s/.test(raw) || pendingSpace, t: /\s$/.test(raw)};
        pendingSpace = false;
        kids.push(item);
      } else if (n.nodeType === 1) {
        const sub = walk(n, isBlock ? level + 1 : level);
        if (!sub.length) continue;
        if (flexParent) { sub[0].l = true; sub[sub.length - 1].t = true; }
        if (pendingSpace && (sub[0].k === 't' || sub[0].k === 'i')) sub[0].l = true;
        pendingSpace = false;
        for (const x of sub) kids.push(x);
      }
    }
    if (isBlock) {
      stats.nodes += 1;
      const b = {k: 'b', role, name: named, kids};
      if (role === 'heading') b.level = parseInt(tag.charAt(1), 10) || parseInt(el.getAttribute('aria-level') || '2', 10);
      if (ALL && generic) { b.role = tag.toLowerCase(); }
      return [b];
    }
    if (blockish && !flexParent) return [{k: 'br'}, ...kids, {k: 'br'}];
    return kids;
  }

  // ---- rendering -----------------------------------------------------------------------
  function seg(item) {
    if (item.k === 't') return item.s;
    const st = item.state.length ? ' ' + item.state.join(' ') : '';
    if (item.role === 'link') return '[' + (item.name || item.href || 'link') + '|' + item.ref + st + ']';
    return '[' + item.role + (item.name ? ' ' + item.name : '') + '|' + item.ref + st + ']';
  }

  function runString(items) {
    const segs = [];
    // drop text that only repeats the neighbouring control's name
    for (let i = 0; i < items.length; i++) {
      const it = items[i];
      if (it.k === 't') {
        const low = it.s.toLowerCase();
        const p = items[i - 1], n = items[i + 1];
        if ((p && p.k === 'i' && p.name && p.name.toLowerCase() === low) || (n && n.k === 'i' && n.name && n.name.toLowerCase() === low)) continue;
        const prev = segs[segs.length - 1];
        if (prev && prev.k === 't' && prev.s === it.s) continue;
      }
      segs.push(it);
    }
    let out = '';
    let budget = RUN_TEXT;
    let elided = false;
    let prev = null;
    for (const it of segs) {
      let piece;
      if (it.k === 't') {
        if (budget <= 0) { if (!elided) { out += ' …'; elided = true; } prev = it; continue; }
        piece = it.s.length > budget ? it.s.slice(0, budget) + '…' : it.s;
        budget -= it.s.length;
      } else piece = seg(it);
      let space = ' ';
      if (!out) space = '';
      else if (prev && (prev.k === 't' || prev.k === 'i') && (it.k === 't' || it.k === 'i')) {
        const glue = !(prev.t || it.l) && !(prev.k === 'i' && it.k === 'i');
        if (glue) space = '';
      }
      out += space + piece;
      prev = it;
    }
    return out;
  }

  function standalone(item) {
    const st = item.state.length ? ' ' + item.state.join(' ') : '';
    return item.role + (item.name ? ' "' + item.name + '"' : '') + ' [' + item.ref + ']' + st + (item.href ? ' ' + item.href : '');
  }

  const lines = [];
  function emit(indent, text) { lines.push('  '.repeat(indent) + text); }

  function renderItems(items, indent) {
    let run = [];
    let lastDeep = false;
    const flush = () => {
      if (!run.length) return;
      const has = run.some((x) => x.k === 't' || x.k === 'i');
      if (has) {
        const only = run.length === 1 && run[0].k === 'i';
        const txt = only ? standalone(run[0]) : 'text: ' + runString(run);
        if (only || txt.length > 6) emit(indent, txt);
      }
      run = [];
    };
    for (const it of items) {
      if (it.k === 't' || it.k === 'i') { run.push(it); lastDeep = false; continue; }
      if (it.k === 'br') { flush(); continue; }
      flush();
      if (it.k === 'deep') {
        if (!lastDeep) emit(indent, '… deeper structure omitted (raise depth or scope with selector)');
        lastDeep = true; continue;
      }
      lastDeep = false;
      if (it.k === 'g') { emit(indent, it.text); continue; }
      if (it.k === 'tbl') { renderTable(it, indent); continue; }
      if (it.k === 'b') renderBlock(it, indent);
    }
    flush();
  }

  function renderTable(t, indent) {
    emit(indent, 'table' + (t.name ? ' "' + t.name + '"' : '') + ' [' + t.nrows + ' rows x ' + t.ncols + ' cols]');
    for (const r of t.rows) emit(indent + 1, r);
    if (t.omitted > 0) emit(indent + 1, '… ' + t.omitted + ' more rows (scope with selector to read them)');
  }

  function renderBlock(b, indent) {
    const label = b.role === 'heading' ? 'h' + b.level : (LABELS[b.role] || b.role);
    const inline = b.kids.every((x) => x.k === 't' || x.k === 'i' || x.k === 'br');
    const nameStr = b.name && b.role !== 'heading' && b.role !== 'paragraph' && b.role !== 'listitem' ? ' "' + clip(b.name, NAME_MAX) + '"' : '';
    if (inline) {
      const parts = b.kids.filter((x) => x.k !== 'br');
      const txt = runString(parts);
      if (!txt) { if (nameStr) emit(indent, label + nameStr); return; }
      emit(indent, label + nameStr + (label === '-' ? ' ' : ': ') + txt);
      return;
    }
    const before = lines.length;
    // A leading run of text and controls goes on the block's own line.
    let n = 0;
    while (n < b.kids.length && (b.kids[n].k === 't' || b.kids[n].k === 'i')) n += 1;
    const lead = n ? runString(b.kids.slice(0, n)) : '';
    emit(indent, label + nameStr + (lead ? (label === '-' ? ' ' : ': ') + lead : ''));
    const mark = lines.length;
    renderItems(b.kids.slice(n), indent + 1, b.role === 'listitem');
    if (lines.length === mark) lines.splice(before, 1); // block with no renderable content
  }

  let root = null;
  if (opts.selector) {
    try { root = document.querySelector(opts.selector); } catch (e) { return {error: 'invalid selector: ' + String(e.message || e)}; }
    if (!root) return {error: 'selector matched nothing: ' + opts.selector};
  } else root = document.body || document.documentElement;
  if (root.closest && root.closest('table')) ROW_CAP = 300;
  const items = walk(root, 0);
  renderItems(items, 0);
  // Scoped-table fallback: infobox-style tables can yield refs but almost no text
  // (cells clipped to empty by row/cell caps). Emit a flat textOf(table) run so
  // facts survive; paging still happens Python-side via offset/max_chars.
  if (SCOPED && root.tagName === 'TABLE') {
    const bodyChars = norm(lines.join('\n')).replace(/[\[\]{}]/g, '').length;
    if (bodyChars < 40) {
      const flat = norm(textOf(root, RUN_TEXT * 4));
      if (flat) lines.push('text: ' + clip(flat, RUN_TEXT * 4));
    }
  }
  window.__shoavSeq = seq;
  return {lines, stats, title: document.title, url: location.href, scoped: !!opts.selector};
}
"""
