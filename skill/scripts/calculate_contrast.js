/**
 * calculate_contrast.js
 * 
 * WCAG 2.1 Mathematical Contrast Calculator & Camouflage Detector
 * 
 * Calculates exact relative luminance and contrast ratios between foreground text/icons
 * and effective background colors (accounting for opacity and multi-layer DOM inheritance).
 * Detects low-contrast ghost links (e.g. #DDD on #FFF), micro-text (<10px or opacity < 0.45),
 * and textless clickable elements.
 * 
 * Designed for headless browser execution via Playwright `page.evaluate()` or browser MCP `eval_js`.
 * Completely generalized for the open web.
 */

(function () {
  /**
   * Parse RGB/RGBA or Hex string into [r, g, b, a] (0-255 for RGB, 0-1 for Alpha)
   */
  function parseColor(colorStr) {
    if (!colorStr || colorStr === 'transparent' || colorStr === 'inherit') {
      return [0, 0, 0, 0];
    }

    // Handle rgb(r, g, b) or rgba(r, g, b, a)
    const rgbaMatch = colorStr.match(/rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)/i);
    if (rgbaMatch) {
      return [
        parseInt(rgbaMatch[1], 10),
        parseInt(rgbaMatch[2], 10),
        parseInt(rgbaMatch[3], 10),
        rgbaMatch[4] !== undefined ? parseFloat(rgbaMatch[4]) : 1.0
      ];
    }

    // Handle Hex colors (#RGB, #RGBA, #RRGGBB, #RRGGBBAA)
    if (colorStr.startsWith('#')) {
      let hex = colorStr.slice(1);
      if (hex.length === 3 || hex.length === 4) {
        hex = hex.split('').map(c => c + c).join('');
      }
      const num = parseInt(hex, 16);
      if (hex.length === 6) {
        return [(num >> 16) & 255, (num >> 8) & 255, num & 255, 1.0];
      } else if (hex.length === 8) {
        return [(num >> 24) & 255, (num >> 16) & 255, (num >> 8) & 255, ((num & 255) / 255)];
      }
    }

    return [0, 0, 0, 1.0];
  }

  /**
   * Alpha blend foreground color over background color
   */
  function compositeColors(fg, bg) {
    const [fgR, fgG, fgB, fgA] = fg;
    const [bgR, bgG, bgB, bgA] = bg;
    const outA = fgA + bgA * (1 - fgA);
    if (outA === 0) return [255, 255, 255, 1.0]; // Default to white backdrop

    const outR = Math.round((fgR * fgA + bgR * bgA * (1 - fgA)) / outA);
    const outG = Math.round((fgG * fgA + bgG * bgA * (1 - fgA)) / outA);
    const outB = Math.round((fgB * fgA + bgB * bgA * (1 - fgA)) / outA);

    return [outR, outG, outB, outA];
  }

  /**
   * Traverse DOM parents to determine effective solid background color
   */
  function getEffectiveBackgroundColor(element) {
    let curr = element;
    let accumulated = [0, 0, 0, 0];

    while (curr && curr !== document && curr !== document.documentElement) {
      const style = window.getComputedStyle(curr);
      const bg = parseColor(style.backgroundColor);
      if (bg[3] > 0) {
        accumulated = compositeColors(accumulated, bg);
        if (accumulated[3] >= 0.99) {
          return accumulated;
        }
      }
      curr = curr.parentElement;
    }

    // Fallback: Default browser viewport background is white #FFFFFF
    return compositeColors(accumulated, [255, 255, 255, 1.0]);
  }

  /**
   * Calculate WCAG 2.1 Relative Luminance L:
   * L = 0.2126 * R + 0.7152 * G + 0.0722 * B
   */
  function calculateRelativeLuminance(rgb) {
    const sRGB = rgb.slice(0, 3).map(val => {
      const c = val / 255;
      return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * sRGB[0] + 0.7152 * sRGB[1] + 0.0722 * sRGB[2];
  }

  /**
   * Calculate WCAG 2.1 Contrast Ratio CR:
   * CR = (L1 + 0.05) / (L2 + 0.05)
   */
  function calculateContrastRatio(fgRgba, bgRgba) {
    const effectiveFg = compositeColors(fgRgba, bgRgba);
    const l1 = calculateRelativeLuminance(effectiveFg);
    const l2 = calculateRelativeLuminance(bgRgba);
    const lighter = Math.max(l1, l2);
    const darker = Math.min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
  }

  /**
   * Main audit routine: Scan interactive elements for visual camouflage
   * @param {Element|Document} container - Root DOM node to inspect
   */
  function auditContrastAndVisualAnomalies(container = document) {
    const candidates = container.querySelectorAll('a, button, [role="button"], input[type="button"], input[type="submit"], [onclick]');
    const results = [];

    candidates.forEach(el => {
      const rect = el.getBoundingClientRect();
      // Ignore non-rendered or zero-dimension elements
      if (rect.width <= 0 || rect.height <= 0) return;

      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') return;

      const fgColor = parseColor(style.color);
      const bgColor = getEffectiveBackgroundColor(el);
      const contrastRatio = calculateContrastRatio(fgColor, bgColor);
      const fontSize = parseFloat(style.fontSize) || 16;
      const opacity = parseFloat(style.opacity) || 1.0;

      const innerText = (el.innerText || el.textContent || '').trim();
      const ariaLabel = el.getAttribute('aria-label') || '';
      const title = el.getAttribute('title') || '';
      const combinedLabel = (innerText + ' ' + ariaLabel + ' ' + title).trim();

      // WCAG Thresholds: normal text requires 4.5:1, large text (>=18pt or >=14pt bold) requires 3.0:1
      const isLargeText = fontSize >= 24 || (fontSize >= 18.5 && (parseInt(style.fontWeight, 10) >= 700 || style.fontWeight === 'bold'));
      const minRequiredContrast = isLargeText ? 3.0 : 4.5;

      const isLowContrast = contrastRatio < minRequiredContrast;
      const isSevereCamouflage = contrastRatio < 2.5; // E.g., #DDD on #FFF has ratio ~1.37
      const isMicroscopic = fontSize < 11 || opacity < 0.45;
      const isTextless = combinedLabel.length === 0 && (el.tagName === 'BUTTON' || el.getAttribute('role') === 'button' || el.tagName === 'A');

      if (isLowContrast || isMicroscopic || isTextless) {
        results.push({
          tagName: el.tagName.toLowerCase(),
          id: el.id || null,
          role: el.getAttribute('role') || el.tagName.toLowerCase(),
          label: combinedLabel,
          contrastRatio: parseFloat(contrastRatio.toFixed(2)),
          requiredMinRatio: minRequiredContrast,
          fontSizePx: fontSize,
          opacity: opacity,
          isLowContrast,
          isSevereCamouflage,
          isMicroscopic,
          isTextless,
          boundingBox: {
            x: Math.round(rect.x),
            y: Math.round(rect.y),
            width: Math.round(rect.width),
            height: Math.round(rect.height)
          },
          computedStyles: {
            color: style.color,
            backgroundColor: `rgb(${bgColor[0]},${bgColor[1]},${bgColor[2]})`
          }
        });
      }
    });

    return results;
  }

  // Attach to window and export
  if (typeof window !== 'undefined') {
    window.auditContrastAndVisualAnomalies = auditContrastAndVisualAnomalies;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      parseColor,
      compositeColors,
      getEffectiveBackgroundColor,
      calculateRelativeLuminance,
      calculateContrastRatio,
      auditContrastAndVisualAnomalies
    };
  }
  return auditContrastAndVisualAnomalies();
})();
