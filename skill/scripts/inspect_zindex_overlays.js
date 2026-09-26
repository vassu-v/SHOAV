/**
 * inspect_zindex_overlays.js
 * 
 * Stacking Context, Z-Index, and Overlay Evasion Inspector
 * 
 * Identifies modal dialogs, hoisted portals, full-viewport backdrops, and clickjack layers.
 * Performs coordinate hit-testing via `document.elementFromPoint(x, y)`.
 * Discovers legitimate dismiss anchors (X icons, ghost buttons, secondary text links,
 * and progressive disclosure triggers like "Manage Preferences" / "More Options").
 * 
 * Universal for real-world web environments. No hardcoded selectors.
 */

(function () {
  /**
   * Check if an element is genuinely visible in the viewport
   */
  function isElementVisible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    const style = window.getComputedStyle(el);
    return (
      style.display !== 'none' &&
      style.visibility !== 'hidden' &&
      parseFloat(style.opacity) > 0.05
    );
  }

  /**
   * Geometric fallback: catches modals built without semantic markup.
   * A modal candidate is a fixed/absolute-positioned element that:
   *  - occupies a bounded (not full-viewport) region
   *  - sits centered or near-centered in the viewport
   *  - has a z-index higher than the page's median z-index
   *  - is rendered above a large translucent/opaque backdrop sibling
   */
  function findGeometricModalCandidates() {
    const allZIndexed = Array.from(document.querySelectorAll('*')).filter(el => {
      const style = window.getComputedStyle(el);
      return (style.position === 'fixed' || style.position === 'absolute') &&
             !isNaN(parseInt(style.zIndex, 10));
    });

    if (allZIndexed.length === 0) return [];

    const zIndices = allZIndexed.map(el => parseInt(window.getComputedStyle(el).zIndex, 10));
    const medianZ = zIndices.slice().sort((a,b) => a-b)[Math.floor(zIndices.length / 2)];

    const vw = window.innerWidth, vh = window.innerHeight;

    return allZIndexed.filter(el => {
      const style = window.getComputedStyle(el);
      const z = parseInt(style.zIndex, 10);
      const rect = el.getBoundingClientRect();
      const isAboveMedian = z > medianZ;
      const isBoundedNotFullscreen = rect.width < vw * 0.95 && rect.height < vh * 0.95 && rect.width > vw * 0.2;
      const isRoughlyCentered = Math.abs((rect.x + rect.width/2) - vw/2) < vw * 0.25;
      return isAboveMedian && isBoundedNotFullscreen && isRoughlyCentered;
    });
  }

  /**
   * Identify all active modal containers and hoisted portal dialogs
   */
  function findActiveModals() {
    const dialogSelectors = [
      'dialog[open]',
      '[role="dialog"]',
      '[role="alertdialog"]',
      '[aria-modal="true"]'
      // No framework-named classes. Geometric fallback below catches the rest.
    ];

    let candidates = Array.from(document.querySelectorAll(dialogSelectors.join(',')))
      .filter(el => isElementVisible(el));

    // Fallback tier when semantic selectors return nothing
    if (candidates.length === 0) {
      candidates = findGeometricModalCandidates().filter(el => isElementVisible(el));
    }

    // Deduplicate nested modals to retain the innermost active dialog
    const uniqueModals = candidates.filter(el => {
      return !candidates.some(other => other !== el && el.contains(other));
    });

    return uniqueModals.map(modal => {
      const rect = modal.getBoundingClientRect();
      const style = window.getComputedStyle(modal);
      const titleEl = modal.querySelector('h1, h2, h3, h4, h5, [class*="title" i], [class*="header" i]');
      const title = titleEl ? titleEl.innerText.trim() : '';

      return {
        element: modal,
        tagName: modal.tagName.toLowerCase(),
        id: modal.id || null,
        title: title.slice(0, 100),
        zIndex: parseInt(style.zIndex, 10) || 0,
        position: style.position,
        isPortaled: modal.parentElement === document.body || modal.parentElement?.id === 'portal',
        boundingBox: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        }
      };
    });
  }

  /**
   * Detect full-viewport backdrops, modal masks, and clickjack layers
   */
  function findViewportOverlays() {
    const all = Array.from(document.querySelectorAll('*'));
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    return all.filter(el => {
      if (!isElementVisible(el)) return false;
      const style = window.getComputedStyle(el);
      const isFixedOrAbsolute = style.position === 'fixed' || style.position === 'absolute';
      if (!isFixedOrAbsolute) return false;

      const rect = el.getBoundingClientRect();
      const coversViewport = rect.width >= vw * 0.85 && rect.height >= vh * 0.85;
      const zIndex = parseInt(style.zIndex, 10);
      const hasHighZ = !isNaN(zIndex) && zIndex >= 50;

      return coversViewport && (hasHighZ || style.backgroundColor.includes('rgba') || style.backdropFilter !== 'none');
    }).map(overlay => {
      const style = window.getComputedStyle(overlay);
      const rect = overlay.getBoundingClientRect();
      return {
        element: overlay,
        tagName: overlay.tagName.toLowerCase(),
        id: overlay.id || null,
        zIndex: parseInt(style.zIndex, 10) || 0,
        pointerEvents: style.pointerEvents,
        opacity: parseFloat(style.opacity) || 1.0,
        boundingBox: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        }
      };
    });
  }

  /**
   * Search for legitimate dismiss anchors within a modal or the entire page
   */
  function findDismissAnchors(container = document) {
    const INTERACTIVE_SEL = 'button, a, [role="button"], input, select';
    const rawInteractive = Array.from(
      container.querySelectorAll('button, a, [role="button"], span, div, i, svg')
    ).filter(el => isElementVisible(el));

    // Exclude container wrappers that contain interactive descendants
    const interactive = rawInteractive.filter(el => {
      if (el.matches(INTERACTIVE_SEL)) return true;
      return !el.querySelector(INTERACTIVE_SEL);
    });

    const dismissAnchors = [];

    // Semantic patterns for escape actions
    const closeGlyphRegex = /^[×✕✖xX⨉\u00d7\u2715\u2716]$/;
    const closeAttrRegex = /(close|dismiss|cancel|decline|reject|opt-out|skip|never|no[_-]?thanks|later)/i;
    const progressiveDisclosureRegex = /(more[_\s-]?options|customize|manage[_\s-]?(preferences|cookies|settings)|review[_\s-]?settings|details)/i;

    interactive.forEach(el => {
      const text = (el.innerText || el.textContent || '').trim();
      const ariaLabel = el.getAttribute('aria-label') || '';
      const title = el.getAttribute('title') || '';
      const className = typeof el.className === 'string' ? el.className : '';
      const id = el.id || '';

      let anchorType = null;
      let confidence = 0;

      // Check A: Explicit close icon/glyph (e.g. &times;, 'X')
      if (closeGlyphRegex.test(text)) {
        anchorType = 'CLOSE_ICON_GLYPH';
        confidence = 0.95;
      }
      // Check B: ARIA label or title indicates close/dismiss
      else if (closeAttrRegex.test(ariaLabel) || closeAttrRegex.test(title)) {
        anchorType = 'CLOSE_ARIA_LABEL';
        confidence = 0.9;
      }
      // Check C: Class name or ID indicates close button
      else if (closeAttrRegex.test(className) || closeAttrRegex.test(id)) {
        anchorType = 'CLOSE_IDENTIFIER';
        confidence = 0.85;
      }
      // Check D: Semantic decline / refusal text
      else if (closeAttrRegex.test(text) && text.length < 50) {
        anchorType = 'DECLINE_TEXT_ACTION';
        confidence = 0.9;
      }
      // Check E: Progressive disclosure trigger (stepping stone to hidden rejection)
      else if (progressiveDisclosureRegex.test(text) || progressiveDisclosureRegex.test(ariaLabel)) {
        anchorType = 'PROGRESSIVE_DISCLOSURE_TRIGGER';
        confidence = 0.85;
      }

      if (anchorType) {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        dismissAnchors.push({
          element: el,
          tagName: el.tagName.toLowerCase(),
          id: el.id || null,
          anchorType,
          confidence,
          text: text.slice(0, 80),
          ariaLabel,
          role: el.getAttribute('role') || el.tagName.toLowerCase(),
          zIndex: parseInt(style.zIndex, 10) || 0,
          boundingBox: {
            x: Math.round(rect.x),
            y: Math.round(rect.y),
            width: Math.round(rect.width),
            height: Math.round(rect.height)
          }
        });
      }
    });

    // Deduplicate nested matches: keep only the innermost matched element
    const innermostAnchors = dismissAnchors.filter(a1 => 
      !dismissAnchors.some(a2 => a1 !== a2 && a1.element && a2.element && a1.element.contains(a2.element))
    );

    // Sort by confidence descending
    return innermostAnchors.sort((a, b) => b.confidence - a.confidence);
  }

  /**
   * Perform hit-testing at element center coordinates to detect click interception
   */
  function testClickTarget(element) {
    if (!element || !element.getBoundingClientRect) {
      return { isClickable: false, reason: 'Invalid element' };
    }

    const rect = element.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;

    // Check if coordinates are within the current viewport
    if (centerX < 0 || centerX > window.innerWidth || centerY < 0 || centerY > window.innerHeight) {
      return {
        isClickable: false,
        reason: 'OUT_OF_VIEWPORT',
        coordinates: { x: centerX, y: centerY }
      };
    }

    const hit = document.elementFromPoint(centerX, centerY);
    const isDirectMatch = hit === element || element.contains(hit);

    return {
      isClickable: isDirectMatch,
      hitElementTag: hit ? hit.tagName.toLowerCase() : null,
      hitElementId: hit ? hit.id : null,
      hitElementClass: hit && typeof hit.className === 'string' ? hit.className : null,
      targetTag: element.tagName.toLowerCase(),
      targetId: element.id || null,
      coordinates: { x: Math.round(centerX), y: Math.round(centerY) }
    };
  }

  /**
   * Full stacking & overlay audit suite
   */
  function inspectStackingAndOverlays() {
    const activeModals = findActiveModals();
    const viewPortOverlays = findViewportOverlays();

    // If modals exist, search for dismiss anchors inside the topmost modal first
    let dismissAnchors = [];
    if (activeModals.length > 0) {
      dismissAnchors = findDismissAnchors(activeModals[0].element);
    }
    // Also include global dismiss anchors if none found in modal
    if (dismissAnchors.length === 0) {
      dismissAnchors = findDismissAnchors(document);
    }

    return {
      hasActiveModal: activeModals.length > 0,
      activeModalsCount: activeModals.length,
      modals: activeModals.map(m => ({
        id: m.id,
        tagName: m.tagName,
        title: m.title,
        zIndex: m.zIndex,
        isPortaled: m.isPortaled,
        boundingBox: m.boundingBox
      })),
      hasOverlays: viewPortOverlays.length > 0,
      overlaysCount: viewPortOverlays.length,
      overlays: viewPortOverlays.map(o => ({
        id: o.id,
        tagName: o.tagName,
        zIndex: o.zIndex,
        pointerEvents: o.pointerEvents,
        opacity: o.opacity,
        boundingBox: o.boundingBox
      })),
      dismissAnchorsCount: dismissAnchors.length,
      topDismissAnchors: dismissAnchors.slice(0, 5).map(a => ({
        id: a.id,
        tagName: a.tagName,
        anchorType: a.anchorType,
        text: a.text,
        ariaLabel: a.ariaLabel,
        boundingBox: a.boundingBox
      }))
    };
  }

  // Attach to window and export
  if (typeof window !== 'undefined') {
    window.inspectStackingAndOverlays = inspectStackingAndOverlays;
    window.testClickTarget = testClickTarget;
    window.findDismissAnchors = findDismissAnchors;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      isElementVisible,
      findActiveModals,
      findViewportOverlays,
      findDismissAnchors,
      testClickTarget,
      inspectStackingAndOverlays
    };
  }

  return inspectStackingAndOverlays();
})();
