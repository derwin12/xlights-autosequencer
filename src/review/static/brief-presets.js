'use strict';

// brief-presets.js — Preset → raw config mapping for the Creative Brief.
// Authoritative source: specs/047-creative-brief/research.md §1.
//
// Attaches BRIEF_PRESETS and resolveBriefToPost(brief) to window.
// Phase 4 (spec 048 follow-up) will consume this map server-side, at which
// point the client-side smart-default ruleset in brief-tab.js can be deleted.

(function () {
  // Axis ordering matches the UI column order in brief-tab.html.
  // Each axis: { label, hint, presets: [{ id, label, hint?, raw: {...} }] }.
  // `raw` is the sparse GenerationConfig override applied by the preset.
  // An empty `raw: {}` means "Auto" — the POST body omits every field.
  const BRIEF_PRESETS = {
    genre: {
      label: 'Genre',
      hint: 'Shapes which palettes and effect families get selected.',
      presets: [
        { id: 'auto', label: 'Auto', raw: {} },
        { id: 'pop', label: 'Pop', raw: { genre: 'pop' } },
        { id: 'rock', label: 'Rock', raw: { genre: 'rock' } },
        { id: 'classical', label: 'Classical', raw: { genre: 'classical' } },
        { id: 'any', label: 'Any', raw: { genre: 'any' } },
      ],
    },
    occasion: {
      label: 'Occasion',
      hint: 'Seasonal palette bias (Christmas reds/greens, Halloween oranges, etc.).',
      presets: [
        { id: 'auto', label: 'Auto', raw: {} },
        { id: 'general', label: 'General', raw: { occasion: 'general' } },
        { id: 'christmas', label: 'Christmas', raw: { occasion: 'christmas' } },
        { id: 'halloween', label: 'Halloween', raw: { occasion: 'halloween' } },
      ],
    },
    mood_intent: {
      label: 'Mood intent',
      hint: 'The overall feeling you want — recommends defaults for other controls.',
      presets: [
        { id: 'auto', label: 'Auto', raw: { mood_intent: 'auto' } },
        { id: 'party', label: 'Party', raw: { mood_intent: 'party' } },
        { id: 'emotional', label: 'Emotional', raw: { mood_intent: 'emotional' } },
        { id: 'dramatic', label: 'Dramatic', raw: { mood_intent: 'dramatic' } },
        { id: 'playful', label: 'Playful', raw: { mood_intent: 'playful' } },
      ],
    },
    variation: {
      label: 'Variation style',
      hint: 'Whether every section cycles through similar effects (Focused) or new ones (Varied).',
      presets: [
        { id: 'auto', label: 'Auto', raw: {} },
        {
          id: 'focused',
          label: 'Focused',
          raw: { focused_vocabulary: true, embrace_repetition: true, tier_selection: true },
        },
        {
          id: 'balanced',
          label: 'Balanced',
          raw: { focused_vocabulary: true, embrace_repetition: false, tier_selection: true },
        },
        {
          id: 'varied',
          label: 'Varied',
          raw: { focused_vocabulary: false, embrace_repetition: false, tier_selection: true },
        },
      ],
    },
    palette: {
      label: 'Color palette',
      hint: 'How many colors are on-screen at once. Restrained reads as cleaner; Full reads as busier.',
      presets: [
        { id: 'auto', label: 'Auto', raw: {} },
        { id: 'restrained', label: 'Restrained', raw: { palette_restraint: true } },
        { id: 'balanced', label: 'Balanced', raw: {} },
        { id: 'full', label: 'Full', raw: { palette_restraint: false } },
      ],
    },
    duration: {
      label: 'Effect duration',
      hint: 'How long each effect lingers — Snappy cuts on beats, Flowing crossfades over bars.',
      presets: [
        { id: 'auto', label: 'Auto', raw: {} },
        { id: 'snappy', label: 'Snappy', raw: { duration_scaling: true, duration_feel: 'snappy' } },
        { id: 'balanced', label: 'Balanced', raw: { duration_scaling: true, duration_feel: 'balanced' } },
        { id: 'flowing', label: 'Flowing', raw: { duration_scaling: true, duration_feel: 'flowing' } },
      ],
    },
    accents: {
      label: 'Accent intensity',
      hint: 'Beat-synchronized bursts on drum hits. None disables them; Strong turns them up.',
      presets: [
        { id: 'auto', label: 'Auto', raw: {} },
        { id: 'none', label: 'None', raw: { beat_accent_effects: false, accent_strength: 'auto' } },
        { id: 'subtle', label: 'Subtle', raw: { beat_accent_effects: true, accent_strength: 'subtle' } },
        { id: 'strong', label: 'Strong', raw: { beat_accent_effects: true, accent_strength: 'strong' } },
      ],
    },
    transitions: {
      label: 'Transitions',
      hint: 'How sections blend at boundaries. None is abrupt; Dramatic uses strobes and flashes.',
      presets: [
        { id: 'auto', label: 'Auto', raw: {} },
        { id: 'none', label: 'None', raw: { transition_mode: 'none' } },
        { id: 'subtle', label: 'Subtle', raw: { transition_mode: 'subtle' } },
        { id: 'dramatic', label: 'Dramatic', raw: { transition_mode: 'dramatic' } },
      ],
    },
    curves: {
      label: 'Value curves',
      hint: 'Let effect parameters (brightness, speed) animate over time instead of staying constant.',
      presets: [
        { id: 'auto', label: 'Auto', raw: {} },
        { id: 'on', label: 'On', raw: { curves_mode: 'all' } },
        { id: 'off', label: 'Off', raw: { curves_mode: 'none' } },
      ],
    },
  };

  // Raw field hints — shown under each Advanced-disclosure control.
  // Technical terminology is allowed here (US6 AC-4).
  const ADVANCED_HINTS = {
    genre: 'Explicit genre override — falls back to ID3 tag if Auto.',
    occasion: 'Explicit occasion override — affects seasonal palettes.',
    focused_vocabulary: 'Derive a weighted working set per theme so effects repeat on-brand.',
    embrace_repetition: 'Relax intra-section dedup so one motif can hit repeatedly.',
    tier_selection: 'Let the tier-selector pick a single partition tier per section.',
    palette_restraint: 'Trim active palette to 2-4 colors per section based on energy.',
    duration_scaling: 'Scale each effect length by BPM and section energy.',
    duration_feel: 'snappy = beat-aligned cuts; flowing = bar-length crossfades.',
    beat_accent_effects: 'Drum-hit Shockwave on small radial props + whole-house impact accents.',
    accent_strength: 'subtle = small/infrequent; strong = large/dense.',
    transition_mode: 'none / subtle / dramatic — controls cross-section blends.',
    curves_mode: 'all / brightness / speed / color / none — which effect parameters get curved.',
    mood_intent: 'Stored nominally in Phase 3 — wired into generation in Phase 4.',
  };

  // Compute the sparse POST body from a Brief JSON.
  // Auto axes contribute nothing; non-Auto axes contribute their preset's raw map.
  // brief.advanced (if present) is spread last so it wins over preset-derived values.
  function resolveBriefToPost(brief) {
    const body = {};
    if (!brief || typeof brief !== 'object') return body;

    Object.keys(BRIEF_PRESETS).forEach(axis => {
      const selected = brief[axis] || 'auto';
      const axisDef = BRIEF_PRESETS[axis];
      const preset = axisDef.presets.find(p => p.id === selected);
      if (!preset) return;
      Object.keys(preset.raw).forEach(k => {
        body[k] = preset.raw[k];
      });
    });

    const advanced = brief.advanced || {};
    Object.keys(advanced).forEach(k => {
      body[k] = advanced[k];
    });

    const overrides = brief.per_section_overrides || [];
    if (overrides.length > 0) {
      const map = {};
      overrides.forEach(row => {
        if (row && typeof row.section_index === 'number' && row.theme_slug && row.theme_slug !== 'auto') {
          map[row.section_index] = row.theme_slug;
        }
      });
      if (Object.keys(map).length > 0) {
        body.theme_overrides = map;
      }
    }

    return body;
  }

  // Derive the "current" preset id for an axis given brief state + advanced overrides.
  // If any advanced key diverges from the preset's raw map, return 'custom'.
  function detectActivePreset(axis, brief) {
    const axisDef = BRIEF_PRESETS[axis];
    if (!axisDef) return 'auto';
    const selected = brief[axis] || 'auto';
    const preset = axisDef.presets.find(p => p.id === selected);
    if (!preset) return 'auto';

    const advanced = brief.advanced || {};
    // For each raw field the preset touches, check advanced doesn't diverge.
    for (const k of Object.keys(preset.raw)) {
      if (Object.prototype.hasOwnProperty.call(advanced, k) && advanced[k] !== preset.raw[k]) {
        return 'custom';
      }
    }
    // Also: if advanced contains a key relevant to this axis that the preset
    // does NOT carry (e.g. user turned palette_restraint on while palette=auto),
    // the preset becomes "custom" too.
    const axisFields = collectAxisFields(axis);
    for (const k of axisFields) {
      if (
        Object.prototype.hasOwnProperty.call(advanced, k) &&
        !Object.prototype.hasOwnProperty.call(preset.raw, k)
      ) {
        return 'custom';
      }
    }
    return selected;
  }

  // Union of raw field names any preset for this axis touches.
  function collectAxisFields(axis) {
    const axisDef = BRIEF_PRESETS[axis];
    if (!axisDef) return [];
    const fields = new Set();
    axisDef.presets.forEach(p => {
      Object.keys(p.raw).forEach(k => fields.add(k));
    });
    return Array.from(fields);
  }

  window.BRIEF_PRESETS = BRIEF_PRESETS;
  window.BRIEF_ADVANCED_HINTS = ADVANCED_HINTS;
  window.resolveBriefToPost = resolveBriefToPost;
  window.detectActivePreset = detectActivePreset;
  window.collectAxisFields = collectAxisFields;
})();
