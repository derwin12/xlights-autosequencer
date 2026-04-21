# Danger Zone

**Artist**: Kenny Loggins
**Genre**: Classic rock / 80s film soundtrack
**Selected because**: Iconic driving rock track with a strong, consistent tempo and highly recognisable sectional structure (intro synth build, verses, choruses, instrumental break, outro). Two independent pro sequences for the same song allow direct comparison of different sequencing approaches to identical source material.

## What the pro did well

- Synth arpeggio intro is treated as a distinct build section with progressive effect ramp-up
- Chorus energy peaks ("highway to the danger zone") get maximum tier activation reliably in both sequences
- The two sequences (XATW and XATW-2) demonstrate different valid approaches: one favours palette changes across sections, the other favours effect-type changes
- Beat-lock to the driving drum pattern is strong throughout both sequences

## Caveats

- `master_may_differ: true` — multiple masters of this track exist (original 1986 album, Top Gun soundtrack, Top Gun: Maverick remaster, streaming normalised versions). The MD5 hash on disk is for the specific file found in the corpus; the pro sequencers may have worked with a different master, meaning timing offsets could exist at the millisecond level
- Any harness metric that uses absolute beat timestamps should account for this potential offset when scoring against these entries
- The two pro_ids ("xatw" and "xatw-2") share the same mp3_path and audio_hash — they are scored independently but against the same source audio
