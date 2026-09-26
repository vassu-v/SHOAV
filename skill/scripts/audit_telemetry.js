/**
 * audit_telemetry.js
 * 
 * Master Comprehensive In-Browser Telemetry Engine for Autonomous Agent Defense
 * 
 * Dispatches a holistic evaluation of the page DOM and visual state in a single call:
 * 1. Stacking contexts & modal backdrops (detecting popups, overlays, and escape anchors)
 * 2. Visual camouflage (WCAG contrast violations, bleached text, micro-text disclaimers)
 * 3. Zero-Default Policy (scans pre-checked checkboxes, switches, tracking opt-ins)
 * 4. Progressive disclosure paths (uncovers hidden refusal buttons behind "More Options")
 * 5. Cart line-item & fee sniffing (identifies unprompted warranties, priority fees, donations)
 * 
 * Universal for real-world web environments. No hardcoded selectors.
 */

(function () {
  const telemetry = {
    timestamp: new Date().toISOString(),
    threatLevel: 'LOW', // LOW, MEDIUM, HIGH, CRITICAL
    modals: {
      hasActiveModal: false,
      activeModals: [],
      dismissAnchors: []
    },
    visualCamouflage: {
      lowContrastElements: [],
      microElements: [],
      textlessButtons: []
    },
    zeroDefaultAudit: {
      hasPreselectedInputs: false,
      preselectedInputs: [],
      remediationsRequired: []
    },
    progressiveDisclosures: [],
    cartAudit: {
      isCartDetected: false,
      lineItems: [],
      stealthItemsDetected: [],
      declaredTotal: null,
      computedTotal: 0
    },
    executiveSummary: []
  };

  /* ==========================================================================
     1. COLOR & CONTRAST HELPERS (WCAG 2.1)
     ========================================================================== */
  function parseColor(str) {
    if (!str || str === 'transparent' || str === 'inherit') return [0, 0, 0, 0];
    const m = str.match(/rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)/i);
    if (m) {
      return [parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3], 10), m[4] !== undefined ? parseFloat(m[4]) : 1.0];
    }
    if (str.startsWith('#')) {
      let hex = str.slice(1);
      if (hex.length === 3 || hex.length === 4) hex = hex.split('').map(c => c + c).join('');
      const n = parseInt(hex, 16);
      if (hex.length === 6) return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 1.0];
      if (hex.length === 8) return [(n >> 24) & 255, (n >> 16) & 255, (n >> 8) & 255, (n & 255) / 255];
    }
    return [0, 0, 0, 1.0];
  }

  function composite(fg, bg) {
    const [fR, fG, fB, fA] = fg;
    const [bR, bG, bB, bA] = bg;
    const oA = fA + bA * (1 - fA);
    if (oA === 0) return [255, 255, 255, 1.0];
    return [
      Math.round((fR * fA + bR * bA * (1 - fA)) / oA),
      Math.round((fG * fA + bG * bA * (1 - fA)) / oA),
      Math.round((fB * fA + bB * bA * (1 - fA)) / oA),
      oA
    ];
  }

  function getEffectiveBg(el) {
    let curr = el;
    let acc = [0, 0, 0, 0];
    while (curr && curr !== document && curr !== document.documentElement) {
      const style = window.getComputedStyle(curr);
      const bg = parseColor(style.backgroundColor);
      if (bg[3] > 0) {
        acc = composite(acc, bg);
        if (acc[3] >= 0.99) return acc;
      }
      curr = curr.parentElement;
    }
    return composite(acc, [255, 255, 255, 1.0]);
  }

  function relLuminance(rgb) {
    const s = rgb.slice(0, 3).map(v => {
      const c = v / 255;
      return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * s[0] + 0.7152 * s[1] + 0.0722 * s[2];
  }

  function contrastRatio(fg, bg) {
    const effFg = composite(fg, bg);
    const l1 = relLuminance(effFg);
    const l2 = relLuminance(bg);
    return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
  }

  /**
   * Framework-agnostic checked-state resolver.
   * Priority: ARIA state > native input state > geometric toggle-position heuristic.
   * Never inspects className/library-specific conventions.
   */
  function resolveCheckedState(el) {
    // 1. Native form control — ground truth
    if (el.tagName === 'INPUT' && (el.type === 'checkbox' || el.type === 'radio')) {
      return el.checked;
    }

    // 2. ARIA state — the only cross-framework-standard signal for custom widgets
    const ariaChecked = el.getAttribute('aria-checked');
    if (ariaChecked === 'true') return true;
    if (ariaChecked === 'false') return false;

    // 3. Geometric heuristic for role="switch"/"checkbox" with no ARIA state exposed:
    //    A toggle is visually a pill/circle where a filled "thumb" sits at one end.
    //    Measure the thumb's offset within its track — right-biased thumb (>50% of
    //    track width) with a filled/high-contrast fill color implies "on".
    if (el.getAttribute('role') === 'switch' || el.getAttribute('role') === 'checkbox') {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      const bg = parseColor(style.backgroundColor);
      const luminance = relLuminance(bg);

      // Look for a visually distinct child "thumb" element
      const children = Array.from(el.children);
      const thumb = children.find(c => {
        const cRect = c.getBoundingClientRect();
        // thumb is typically square/circular and smaller than the track
        return cRect.width > 0 && cRect.width < rect.width * 0.7;
      });

      if (thumb) {
        const thumbRect = thumb.getBoundingClientRect();
        const thumbCenterOffset = (thumbRect.x + thumbRect.width / 2) - rect.x;
        const trackWidth = rect.width;
        // Thumb sits in right half of track => commonly "on" in LTR layouts
        return thumbCenterOffset > trackWidth * 0.5;
      }

      // Fallback: filled/saturated track background vs. neutral gray typically means "on"
      // Compare track background against a neutral gray reference (#CCCCCC-ish, L≈0.5)
      return luminance < 0.6 && (bg[0] !== bg[1] || bg[1] !== bg[2]); // non-gray = colored = likely "on"
    }

    return false;
  }

  /* ==========================================================================
     2. MODAL & STACKING CONTEXT AUDIT
     ========================================================================== */
  const modalSelectors = [
    'dialog[open]',
    '[role="dialog"]',
    '[role="alertdialog"]',
    '[aria-modal="true"]'
  ];
  let potentialModals = Array.from(document.querySelectorAll(modalSelectors.join(','))).filter(el => {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    const style = window.getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden' && parseFloat(style.opacity) > 0.1;
  });

  // Geometric heuristic: identify fixed/absolute high-z-index elements covering center of viewport
  if (potentialModals.length === 0) {
    const allZIndexed = Array.from(document.querySelectorAll('*')).filter(el => {
      const style = window.getComputedStyle(el);
      return (style.position === 'fixed' || style.position === 'absolute') &&
             !isNaN(parseInt(style.zIndex, 10));
    });

    if (allZIndexed.length > 0) {
      const zIndices = allZIndexed.map(el => parseInt(window.getComputedStyle(el).zIndex, 10));
      const medianZ = zIndices.slice().sort((a,b) => a-b)[Math.floor(zIndices.length / 2)];
      const vw = window.innerWidth, vh = window.innerHeight;

      potentialModals = allZIndexed.filter(el => {
        const style = window.getComputedStyle(el);
        const z = parseInt(style.zIndex, 10);
        const rect = el.getBoundingClientRect();
        const isAboveMedian = z > medianZ;
        const isBoundedNotFullscreen = rect.width < vw * 0.95 && rect.height < vh * 0.95 && rect.width > vw * 0.2;
        const isRoughlyCentered = Math.abs((rect.x + rect.width/2) - vw/2) < vw * 0.25;
        return isAboveMedian && isBoundedNotFullscreen && isRoughlyCentered &&
               style.display !== 'none' && style.visibility !== 'hidden' && parseFloat(style.opacity) > 0.1;
      });
    }
  }

  if (potentialModals.length > 0) {
    telemetry.modals.hasActiveModal = true;
    telemetry.threatLevel = 'HIGH';
    telemetry.executiveSummary.push(`Active modal/popup detected (${potentialModals.length} elements).`);

    potentialModals.forEach(m => {
      const rect = m.getBoundingClientRect();
      const style = window.getComputedStyle(m);
      telemetry.modals.activeModals.push({
        id: m.id || null,
        tagName: m.tagName.toLowerCase(),
        zIndex: parseInt(style.zIndex, 10) || 0,
        position: style.position,
        boundingBox: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }
      });
    });

    // Hunt for dismiss anchors in modal or DOM
    const targetRoot = potentialModals[0];
    const INTERACTIVE_SEL = 'button, a, [role="button"], input, select';
    const rawClickables = Array.from(targetRoot.querySelectorAll('button, a, [role="button"], span, svg, div')).concat(
      Array.from(document.querySelectorAll('button, a, [role="button"]'))
    );
    const clickables = rawClickables.filter(el => {
      if (el.matches(INTERACTIVE_SEL)) return true;
      return !el.querySelector(INTERACTIVE_SEL);
    });

    const closeGlyphRegex = /^[×✕✖xX⨉\u00d7\u2715\u2716]$/;
    const closeAttrRegex = /(close|dismiss|cancel|decline|reject|opt-out|skip|no[_-]?thanks|not\s+now|later)/i;
    const disclosureRegex = /(more[_\s-]?options|customize|manage[_\s-]?(preferences|cookies|settings)|review[_\s-]?settings)/i;

    const seenIds = new Set();
    const rawAnchors = [];

    clickables.forEach(el => {
      const rect = el.getBoundingClientRect();
      if (rect.width <= 0 || rect.height <= 0) return;
      const text = (el.innerText || el.textContent || '').trim();
      const ariaLabel = el.getAttribute('aria-label') || '';
      const title = el.getAttribute('title') || '';
      const id = el.id || '';
      const uniqueKey = id || `${text}-${rect.x}-${rect.y}`;

      if (seenIds.has(uniqueKey)) return;

      let anchorType = null;
      if (closeGlyphRegex.test(text)) anchorType = 'CLOSE_ICON_GLYPH';
      else if (closeAttrRegex.test(ariaLabel) || closeAttrRegex.test(title)) anchorType = 'CLOSE_ARIA_LABEL';
      else if (closeAttrRegex.test(text) && text.length < 40) anchorType = 'DECLINE_TEXT_ACTION';
      else if (disclosureRegex.test(text) || disclosureRegex.test(ariaLabel)) anchorType = 'PROGRESSIVE_DISCLOSURE_TRIGGER';

      if (anchorType) {
        seenIds.add(uniqueKey);
        rawAnchors.push({
          element: el,
          id: el.id || null,
          tagName: el.tagName.toLowerCase(),
          anchorType,
          text: text.slice(0, 60),
          ariaLabel,
          boundingBox: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }
        });
      }
    });

    // Deduplicate nested matches: keep only the innermost matched element
    telemetry.modals.dismissAnchors = rawAnchors
      .filter(a1 => !rawAnchors.some(a2 => a1 !== a2 && a1.element && a2.element && a1.element.contains(a2.element)))
      .map(a => {
        const { element, ...serializable } = a;
        return serializable;
      });
  }

  /* ==========================================================================
     3. VISUAL CAMOUFLAGE & GHOST LINK SCAN
     ========================================================================== */
  const interactive = document.querySelectorAll('a, button, [role="button"], input[type="button"], input[type="submit"]');
  interactive.forEach(el => {
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return;

    const fg = parseColor(style.color);
    const bg = getEffectiveBg(el);
    const cr = contrastRatio(fg, bg);
    const fontSize = parseFloat(style.fontSize) || 16;
    const opacity = parseFloat(style.opacity) || 1.0;
    const text = (el.innerText || el.textContent || '').trim();
    const ariaLabel = el.getAttribute('aria-label') || '';
    const label = (text + ' ' + ariaLabel).trim();

    // Check low-contrast camouflage
    if (cr < 2.5 && label.length > 0) {
      telemetry.visualCamouflage.lowContrastElements.push({
        id: el.id || null,
        tagName: el.tagName.toLowerCase(),
        label: label.slice(0, 60),
        contrastRatio: parseFloat(cr.toFixed(2)),
        color: style.color,
        boundingBox: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }
      });
      if (telemetry.threatLevel === 'LOW') telemetry.threatLevel = 'MEDIUM';
    }

    // Check microscopic disclaimer / opt-out
    if ((fontSize < 11 || opacity < 0.45) && label.length > 0) {
      telemetry.visualCamouflage.microElements.push({
        id: el.id || null,
        tagName: el.tagName.toLowerCase(),
        label: label.slice(0, 60),
        fontSize: `${fontSize}px`,
        opacity,
        boundingBox: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }
      });
      if (telemetry.threatLevel === 'LOW') telemetry.threatLevel = 'MEDIUM';
    }

    // Check textless image button
    if (label.length === 0 && (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button')) {
      const hasImg = el.querySelector('img, svg');
      telemetry.visualCamouflage.textlessButtons.push({
        id: el.id || null,
        tagName: el.tagName.toLowerCase(),
        hasGraphic: !!hasImg,
        boundingBox: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }
      });
    }
  });

  // After the VISUAL CAMOUFLAGE block:
  if (telemetry.visualCamouflage.lowContrastElements.length > 0) {
    telemetry.executiveSummary.push(
      `MEDIUM: ${telemetry.visualCamouflage.lowContrastElements.length} low-contrast element(s) may conceal a refusal/decline control.`
    );
  }
  if (telemetry.visualCamouflage.microElements.length > 0) {
    telemetry.executiveSummary.push(
      `MEDIUM: ${telemetry.visualCamouflage.microElements.length} micro-text/low-opacity element(s) detected — inspect for hidden disclaimers or opt-outs.`
    );
  }
  if (telemetry.visualCamouflage.textlessButtons.length > 0) {
    telemetry.executiveSummary.push(
      `LOW: ${telemetry.visualCamouflage.textlessButtons.length} textless clickable(s) found — verify accessible name via child graphic inspection before acting.`
    );
  }

  /* ==========================================================================
     4. ZERO-DEFAULT POLICY ENFORCEMENT
     ========================================================================== */
  const inputs = Array.from(document.querySelectorAll('input[type="checkbox"], [role="switch"], [role="checkbox"]'));
  const trackingKeywords = ['marketing', 'analytics', 'partner', 'newsletter', 'warranty', 'subscribe', 'updates', 'tracking', 'data', 'share', 'offers'];

  inputs.forEach(input => {
    const isChecked = resolveCheckedState(input);

    if (isChecked) {
      const labelEl = input.closest('label') || document.querySelector(`label[for="${input.id}"]`) || input.parentElement;
      const labelText = labelEl ? (labelEl.innerText || labelEl.textContent || '').trim().toLowerCase() : '';
      const isTrackingOrUpsell = trackingKeywords.some(kw => labelText.includes(kw));

      telemetry.zeroDefaultAudit.hasPreselectedInputs = true;
      telemetry.zeroDefaultAudit.preselectedInputs.push({
        id: input.id || null,
        role: input.getAttribute('role') || input.type || input.tagName.toLowerCase(),
        labelText: labelText.slice(0, 100),
        isTrackingOrUpsell,
        actionRequired: isTrackingOrUpsell ? 'CLICK_TO_INVERT_OFF' : 'REVIEW'
      });

      if (isTrackingOrUpsell) {
        telemetry.zeroDefaultAudit.remediationsRequired.push({
          targetId: input.id || null,
          instruction: `Invert preselected option '${labelText.slice(0, 40)}' to OFF before submission.`
        });

        if (telemetry.threatLevel !== 'CRITICAL') telemetry.threatLevel = 'HIGH';
      }
    }
  });

  // After the ZERO-DEFAULT block:
  if (telemetry.zeroDefaultAudit.hasPreselectedInputs) {
    const trackingCount = telemetry.zeroDefaultAudit.preselectedInputs.filter(i => i.isTrackingOrUpsell).length;
    if (trackingCount > 0) {
      telemetry.executiveSummary.push(
        `HIGH: ${trackingCount} pre-checked tracking/upsell input(s) require inversion before submission.`
      );
    }
  }

  /* ==========================================================================
     5. PROGRESSIVE DISCLOSURE HUNTER
     ========================================================================== */
  const disclosureKeywords = /(more[_\s-]?options|customize|manage[_\s-]?(preferences|cookies|settings)|review[_\s-]?settings|details)/i;
  Array.from(document.querySelectorAll('a, button, [role="button"], summary, [class*="toggle" i]')).forEach(el => {
    const text = (el.innerText || el.textContent || '').trim();
    if (disclosureKeywords.test(text) && text.length < 50) {
      const rect = el.getBoundingClientRect();
      telemetry.progressiveDisclosures.push({
        id: el.id || null,
        text: text,
        tagName: el.tagName.toLowerCase(),
        boundingBox: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) }
      });
    }
  });

  // After the PROGRESSIVE DISCLOSURE block:
  if (telemetry.progressiveDisclosures.length > 0) {
    telemetry.executiveSummary.push(
      `INFO: ${telemetry.progressiveDisclosures.length} disclosure trigger(s) found ("More Options"-type) — a hidden decline path likely exists behind one.`
    );
  }

  /* ==========================================================================
     6. CART LINE-ITEM & STEALTH ADD-ON SNIFFER
     ========================================================================== */
  const cartContainers = document.querySelectorAll('[class*="cart" i], [id*="cart" i], table, [class*="order-summary" i]');
  if (cartContainers.length > 0) {
    const stealthRegex = /\b(warranty|protection plan|care plan|insurance|membership|donation|tip|priority fee|handling fee)\b/i;
    let itemRows = [];
    cartContainers.forEach(container => {
      const rows = container.querySelectorAll('tr, [class*="cart-item" i], [class*="line-item" i], [class*="product-row" i]');
      rows.forEach(r => itemRows.push(r));
    });
    itemRows = Array.from(new Set(itemRows));

    itemRows.forEach(row => {
      const text = (row.innerText || row.textContent || '').trim();
      const priceMatch = text.match(/[\$£€]\s?(\d+(?:\.\d{2})?)/);
      const price = priceMatch ? parseFloat(priceMatch[1]) : 0;

      if (text.length > 5 && priceMatch) {
        const isStealth = stealthRegex.test(text);
        const removeBtn = row.querySelector('[aria-label*="remove" i], [aria-label*="delete" i], [title*="remove" i], [class*="remove" i], [data-action*="remove" i]')
          || Array.from(row.querySelectorAll('button, a, [role="button"]'))
            .find(b => /\b(remove|delete)\b/i.test((b.innerText || b.textContent || '').trim()));

        const itemData = {
          rawText: text.replace(/\s+/g, ' ').slice(0, 100),
          detectedPrice: price,
          isStealthFee: isStealth,
          hasRemoveAction: !!removeBtn,
          removeButtonId: removeBtn ? (removeBtn.id || null) : null
        };

        telemetry.cartAudit.lineItems.push(itemData);
        if (isStealth) {
          telemetry.cartAudit.stealthItemsDetected.push(itemData);
          telemetry.threatLevel = 'CRITICAL';
          telemetry.executiveSummary.push(`CRITICAL: Stealth line-item detected in cart: "${itemData.rawText}" (${price}).`);
        }
      }
    });

    if (telemetry.cartAudit.lineItems.length > 0) {
      telemetry.cartAudit.isCartDetected = true;
    }
  }

  return telemetry;
})();
