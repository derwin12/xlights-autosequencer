# Pro Reference Corpus

Professional xLights sequences used as quality calibration ground truth for the harness in `tests/golden/`.

## Files on disk vs. in the repo

`.xsq`, `.xsqz`, and `.mp3` files live on local disk at `/home/node/xlights/baseline-sequences/` and are **not committed to the repository**. Only `manifest.json`, this README, and the `notes/` stubs are in the repo.

## manifest.json format

```json
{
  "entries": [
    {
      "song_id": "light-of-christmas",     // lowercase hyphen slug for the song
      "pro_id": "xatw",                    // short identifier for the pro or take
      "xsq_path": "/absolute/path.xsq",   // absolute path to the .xsq or .xsqz file
      "mp3_path": "/absolute/path.mp3",   // absolute path to the source MP3
      "audio_hash": "md5:<32hexchars>",   // MD5 of the MP3 (see below)
      "tags": ["christmas", "pop"],       // genre/mood tags
      "notes_ref": "notes/light-of-christmas.md",  // relative path to notes stub
      "master_may_differ": false          // true if the pro may have used a different master
    }
  ]
}
```

Multiple entries may share the same `song_id` (different pro sequences for the same song) and the same `mp3_path` + `audio_hash` (scored independently against the same source audio).

## Computing audio_hash

```bash
md5sum <mp3_path> | awk '{print "md5:" $1}'
```

## Current corpus (9 sequences, 6 songs)

| song_id | pro_id | notes |
|---|---|---|
| baby-shark | default | |
| candy-cane-lane | default | |
| danger-zone | xatw | `master_may_differ: true` |
| danger-zone | xatw-2 | `master_may_differ: true` |
| light-of-christmas | default | |
| light-of-christmas | xatw | |
| light-of-christmas | xatw-alt | |
| kid-on-christmas | xatw | |
| shut-up-and-dance | jeremy-poling | |

## Missing MP3s (3 songs not yet in corpus)

The following `.xsq` files exist on disk but have no matching MP3:

| XSQ filename | Expected MP3 basename convention |
|---|---|
| `The Weeknd AG - Save Your Tears HD.xsq` | `## - Save Your Tears.mp3` |
| `Uptown Funk (Radio Edit) Updated 11.25.xsqz` | `## - Uptown Funk.mp3` |
| `Idina Menzel - Christmas Just Ain't Christmas.xsq` | `## - Christmas Just Ain't Christmas.mp3` |

Acquire the MP3s manually (purchase/rip from a legitimate source), place them in `/home/node/xlights/baseline-sequences/` following the `NN - Title.mp3` naming convention used by the existing files, then add entries to `manifest.json` with the computed `audio_hash`.

## Adding a new corpus entry

1. Place the `.xsq`/`.xsqz` and `.mp3` in `/home/node/xlights/baseline-sequences/`
2. Compute the hash: `md5sum <mp3> | awk '{print "md5:" $1}'`
3. Add an entry to `manifest.json` following the format above
4. Create a `notes/<song-id>.md` stub following the template in the existing notes files
5. Commit only `manifest.json`, the notes stub, and this README — never commit the audio or sequence files
