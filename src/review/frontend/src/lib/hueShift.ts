/**
 * Client-side mirror of `_hue_shift_palette` in src/generator/effect_placer.py,
 * so the Theme screen's "Color Shift" slider can show a live preview of the
 * same rotation the generator will actually apply, instead of no feedback at
 * all (user request, 2026-07-26). Uses HSV (not HSL) to match Python's
 * `colorsys.rgb_to_hsv`/`hsv_to_rgb` exactly -- the two models compute
 * saturation/brightness differently, so an HSL-based rotation of the same
 * hex would land on a visibly different color than what actually gets
 * exported.
 */

interface Hsv {
  h: number; // 0-1
  s: number; // 0-1
  v: number; // 0-1
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '');
  const r = parseInt(clean.slice(0, 2), 16) / 255;
  const g = parseInt(clean.slice(2, 4), 16) / 255;
  const b = parseInt(clean.slice(4, 6), 16) / 255;
  return [r, g, b];
}

function rgbToHex(r: number, g: number, b: number): string {
  const toByte = (c: number) => Math.round(Math.max(0, Math.min(1, c)) * 255)
    .toString(16)
    .padStart(2, '0')
    .toUpperCase();
  return `#${toByte(r)}${toByte(g)}${toByte(b)}`;
}

// Port of Python's colorsys.rgb_to_hsv.
function rgbToHsv(r: number, g: number, b: number): Hsv {
  const maxc = Math.max(r, g, b);
  const minc = Math.min(r, g, b);
  const v = maxc;
  if (minc === maxc) {
    return { h: 0, s: 0, v };
  }
  const s = (maxc - minc) / maxc;
  const rc = (maxc - r) / (maxc - minc);
  const gc = (maxc - g) / (maxc - minc);
  const bc = (maxc - b) / (maxc - minc);
  let h: number;
  if (r === maxc) {
    h = bc - gc;
  } else if (g === maxc) {
    h = 2.0 + rc - bc;
  } else {
    h = 4.0 + gc - rc;
  }
  h = (h / 6.0) % 1.0;
  if (h < 0) h += 1.0;
  return { h, s, v };
}

// Port of Python's colorsys.hsv_to_rgb.
function hsvToRgb(h: number, s: number, v: number): [number, number, number] {
  if (s === 0) return [v, v, v];
  const i = Math.floor(h * 6.0);
  const f = h * 6.0 - i;
  const p = v * (1.0 - s);
  const q = v * (1.0 - s * f);
  const t = v * (1.0 - s * (1.0 - f));
  switch (((i % 6) + 6) % 6) {
    case 0: return [v, t, p];
    case 1: return [q, v, p];
    case 2: return [p, v, t];
    case 3: return [p, q, v];
    case 4: return [t, p, v];
    default: return [v, p, q];
  }
}

/**
 * Rotate a single hex color's hue by `shift` (0.0-1.0 fraction of the full
 * color wheel), preserving saturation and value -- identical math to
 * `_hue_shift_palette` in effect_placer.py.
 */
export function hueShiftHex(hex: string, shift: number): string {
  if (!shift) return hex;
  const [r, g, b] = hexToRgb(hex);
  const { h, s, v } = rgbToHsv(r, g, b);
  const newH = ((h + shift) % 1.0 + 1.0) % 1.0;
  const [nr, ng, nb] = hsvToRgb(newH, s, v);
  return rgbToHex(nr, ng, nb);
}

/** Rotate every color in a palette by the same shift. */
export function hueShiftPalette(colors: string[], shift: number): string[] {
  if (!shift) return colors;
  return colors.map((c) => hueShiftHex(c, shift));
}
