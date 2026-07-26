import { describe, it, expect } from 'vitest';
import { hueShiftHex, hueShiftPalette } from './hueShift';

// Expected values cross-checked against the real backend
// (src/generator/effect_placer.py::_hue_shift_palette) via:
//   python -c "from src.generator.effect_placer import _hue_shift_palette; \
//     print(_hue_shift_palette(['#FF0000'], 0.5))"
describe('hueShiftHex', () => {
  it('matches the backend for a half-circle shift on red', () => {
    expect(hueShiftHex('#FF0000', 0.5)).toBe('#00FFFF');
  });

  it('matches the backend for a quarter-circle shift on red', () => {
    expect(hueShiftHex('#FF0000', 0.25)).toBe('#80FF00');
  });

  it('matches the backend for a half-circle shift on green', () => {
    expect(hueShiftHex('#00FF00', 0.5)).toBe('#FF00FF');
  });

  it('matches the backend for an arbitrary color and shift', () => {
    expect(hueShiftHex('#336699', 0.33)).toBe('#993368');
  });

  it('leaves white unchanged (no saturation to rotate)', () => {
    expect(hueShiftHex('#FFFFFF', 0.5)).toBe('#FFFFFF');
  });

  it('leaves gray unchanged (no saturation to rotate)', () => {
    expect(hueShiftHex('#808080', 0.5)).toBe('#808080');
  });

  it('is a no-op at shift=0', () => {
    expect(hueShiftHex('#FF0000', 0)).toBe('#FF0000');
  });
});

describe('hueShiftPalette', () => {
  it('rotates every color in the palette by the same shift', () => {
    expect(hueShiftPalette(['#FF0000', '#00FF00'], 0.5)).toEqual(['#00FFFF', '#FF00FF']);
  });

  it('returns the original array reference-equal colors at shift=0', () => {
    const palette = ['#FF0000', '#00FF00'];
    expect(hueShiftPalette(palette, 0)).toBe(palette);
  });
});
