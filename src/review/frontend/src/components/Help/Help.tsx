import React from "react";
import styles from "./Help.module.css";
import { openExternal, FACEBOOK_GROUP_URL } from "../About/About";

const ISSUES_URL = "https://github.com/derwin12/xlights-autosequencer/issues";

interface FaqEntry {
  q: string;
  a: React.ReactNode;
}

const FAQ: FaqEntry[] = [
  {
    q: "What's the overall workflow?",
    a: (
      <>
        <p>
          The seven tabs across the top are a linear pipeline, in order:
        </p>
        <ul>
          <li><strong>Library</strong> — browse and organize every song you've imported, sorted into folders.</li>
          <li><strong>Import</strong> — drop in an MP3/WAV to add it to the library.</li>
          <li><strong>Analyze</strong> — confirm the song's title/artist, then run the audio analysis pipeline (beats, stems, structure, lyrics).</li>
          <li><strong>Timeline</strong> — review the detected sections, beats, and timing tracks.</li>
          <li><strong>Theme</strong> — assign a color/effect theme to each section (or let auto-selection do it), and fine-tune per-section sliders.</li>
          <li><strong>Extras</strong> — optionally upload images matched to lyric words (Pictures effects), and set up custom lyric words that trigger a Moving Head accent.</li>
          <li><strong>Export</strong> — generate the final <code>.xsq</code> sequence file and download it.</li>
        </ul>
        <p>
          A song's status chip in the Library rail (gray/green/blue) shows how far along it is: draft, analyzed, or themed.
        </p>
      </>
    ),
  },
  {
    q: "Nothing happens when I click Generate/Export — why?",
    a: (
      <p>
        Sequence generation needs an xLights layout file (<code>xlights_rgbeffects.xml</code>) configured first —
        without it there's nothing to map effects onto. Set the layout path in Settings, then Export
        should unlock. Every section also needs a confirmed theme before exporting (use "Accept All" on
        the Theme screen if you're happy with the auto-selected themes).
      </p>
    ),
  },
  {
    q: "Why does the first analysis take so long?",
    a: (
      <>
        <p>
          The first analysis of a song runs the full pipeline: beat/onset detection, stem separation
          (splitting the mix into drums/bass/vocals/other), song structure detection, and a lyrics
          lookup. Stem separation in particular downloads a model the first time it's ever used and can
          take a couple of minutes on CPU.
        </p>
        <p>
          Everything is cached by the audio file's content hash, so re-analyzing the same file (or just
          reopening it later) is instant — nothing is recomputed unless the audio itself changes.
        </p>
      </>
    ),
  },
  {
    q: "What do the Theme screen's sliders (Brightness / Hit Strength / Dwell Time / Color Shift) do?",
    a: (
      <>
        <p>These are per-section overrides layered on top of whatever theme is assigned to that section:</p>
        <ul>
          <li><strong>Brightness</strong> — how intense the background/wash colors are for this section.</li>
          <li><strong>Hit Strength</strong> — how punchy accent effects (drum hits, prop/hero highlights) are, independent of the background brightness.</li>
          <li><strong>Dwell Time</strong> — stretches or shrinks how long each effect segment holds before cutting to the next one.</li>
          <li><strong>Color Shift</strong> — rotates the section's color hue away from the theme's authored colors, for a quick variation without picking a whole new theme.</li>
        </ul>
        <p>Each slider defaults to a no-op value, so an untouched section renders exactly as its theme intends.</p>
      </>
    ),
  },
  {
    q: "What's the difference between a Theme and a Variant?",
    a: (
      <p>
        A <strong>Theme</strong> is the overall creative package for a section — mood, color palette,
        and which effects layer on which prop tiers. A <strong>Variant</strong> is one specific
        pre-tuned configuration of a single xLights effect (e.g. "Fire Tall" vs "Fire Ember" are both
        variants of the Fire effect). Themes are built out of variants.
      </p>
    ),
  },
  {
    q: "How do the Pictures uploads work?",
    a: (
      <p>
        The Extras screen shows lyric words that don't yet have a matching image in your library.
        Upload an image and tag it with a word/topic; the generator then places that image as a
        Pictures effect on matrix/mega-tree props whenever that word is sung. This is entirely manual —
        the app never scrapes images from the web on your behalf.
      </p>
    ),
  },
  {
    q: "How do Moving Head Triggers work?",
    a: (
      <p>
        The Extras screen also lists <strong>shake</strong>, <strong>bounce</strong>, and <strong>spin</strong> —
        three built-in lyric words that trigger a Moving Head accent when sung. Uncheck any of them to
        disable it for this song, or add your own custom word from the song's lyrics and assign it one
        of the three existing motions. Motions are fixed (there's no way to invent a new physical
        movement) — a custom word just maps onto one of shake/bounce/spin's behavior.
      </p>
    ),
  },
  {
    q: "Where are my files stored?",
    a: (
      <>
        <p>
          Your song library, themes, and settings live under <code>~/.xlight/</code> (on Windows,
          under your user's <code>AppData\Local\xLightsAI</code>). Audio-specific caches (stems, analysis
          results) are stored alongside the source audio file itself, in a <code>.stems/</code> folder,
          keyed by the file's content hash.
        </p>
      </>
    ),
  },
  {
    q: "Something looks wrong in the generated sequence — where do I check logs?",
    a: (
      <p>
        Open the About dialog (the build-stamp button in the top-right corner) — it has an
        "Open logs folder" button in the packaged app that reveals the backend's log file.
      </p>
    ),
  },
  {
    q: "Where can I get more help or share what I've made?",
    a: (
      <p>
        Join the community Facebook group below to ask questions, share sequences, and see what
        others are building. For a bug report or feature request, open an issue on the project's
        GitHub page instead.
      </p>
    ),
  },
];

export function Help({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null;

  return (
    <div className={styles.backdrop} role="dialog" aria-modal="true" onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={styles.title}>Help &amp; FAQ</h2>
        <div className={styles.subtitle}>Common questions about using xLightsAI</div>

        <div className={styles.links}>
          <button className={styles.linkBtn} onClick={() => void openExternal(FACEBOOK_GROUP_URL)}>
            Join the Facebook group
          </button>
          <button className={styles.linkBtn} onClick={() => void openExternal(ISSUES_URL)}>
            Report an issue
          </button>
        </div>

        {FAQ.map((entry, i) => (
          <details key={i} className={styles.section} open={i === 0}>
            <summary>{entry.q}</summary>
            <div className={styles.sectionBody}>{entry.a}</div>
          </details>
        ))}

        <div className={styles.actions}>
          <button className={styles.btnPrimary} onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
