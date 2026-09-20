---
name: nsf-refined-common-driver
description: Convert compatible single-song NES 2A03 NSF files into editable FamiStudio projects and NSF deliverables using a user-supplied ROM-approved F000/F100/F160 refined common driver, with loop recovery and frame-level audible-state verification. Use for rewriting legacy NSF music before DC-family ROM integration; do not use for expansion-audio, PAL-only, or direct ROM-binding tasks.
---

# NSF Refined Common Driver

Rewrite music data through FamiStudio, then bind the exact approved 4 KiB common-driver page. Do not call a file converted merely because its NSF header or entry addresses were changed.

## Required inputs

- Source NSF files. Treat them as read-only.
- A known-good reference NSF already using the ROM's accepted `$F000/$F100/$F160` driver.
- FamiStudio with command-line NSF import/export support.
- Python with `py65` available, or a `--pydeps` directory containing it.

Before converting, read [references/compatibility-and-validation.md](references/compatibility-and-validation.md). It defines the supported input boundary, validation gates, and the cases that require stopping for investigation.

## Workflow

1. Read the active repository's `AGENTS.md` and honor its input, build, asset, evidence, and delivery conventions.
2. Identify the reference NSF from the actual target ROM project. Never substitute a driver based only on matching entry addresses.
3. Check compatibility. Use the `mitsume` profile only for the exact five-file 三目童子 source set; use `generic` for other compatible one-song NSF files.
4. Run `scripts/convert_nsf_set.py` with explicit source, reference, FamiStudio, build, asset, and delivery paths. Use a manifest when titles, per-track preserved driver bytes, or DPCM byte overrides are needed.
5. Inspect the JSON report. A successful process exit is necessary but not sufficient: confirm the common-driver hash, zero raw-to-bound semantic mismatches, and every source-fidelity gate.
6. Render a short audible preview of each result when FamiStudio is available. Confirm that it is non-silent and not truncated.
7. Record hashes, sizes, loop decisions, exceptional sweep/DPCM handling, and any validation not run. Do not bind the converted NSF into a ROM unless the user separately requests ROM integration.

Run the packaged converter from the skill directory:

```powershell
python scripts/convert_nsf_set.py `
  --profile generic `
  --input-dir <source-directory> `
  --reference-nsf <approved-refined-nsf> `
  --famistudio <FamiStudio.exe> `
  --pydeps <directory-containing-py65> `
  --build-dir <build-directory> `
  --assets-dir <versioned-music-directory> `
  --dist-dir <delivery-directory> `
  --output-prefix <game-or-set-name>
```

For the known five 三目童子 rips, replace `generic` with `mitsume`. The profile verifies that all five files share the expected engine image and differ only at selector `$B7B1`.

## Non-negotiable gates

- Preserve source loop length; adjust only inaudible leading frames when pattern alignment requires it.
- The final driver slice must be byte-identical to the selected reference except for explicitly reviewed preserved offsets.
- Reject channel on/off, pulse duty, volume, triangle/noise, DPCM-trigger, or non-sweep pitch mismatches.
- Treat hardware-sweep frames as a documented special case; never misrepresent static timer-register images as audible pitch.
- Keep original NSF/ROM files unchanged and keep intermediate imports/exports out of delivery directories.
