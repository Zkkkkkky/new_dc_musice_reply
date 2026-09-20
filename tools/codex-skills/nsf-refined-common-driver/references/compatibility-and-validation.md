# Compatibility and validation

## Supported inputs

The packaged path is intentionally narrow:

- NSF signature `NESM\x1A` and one song per file.
- Standard NES 2A03 audio with no expansion-audio bits set.
- NTSC or dual-region timing. PAL-only material needs a separate timing design.
- An INIT/PLAY interface that the bundled `py65` emulator and FamiStudio importer can execute.
- A reference NSF whose entry points are `$F000/$F100/$F160`, initial banks are `01 02 03 04 05 06 07 00`, and whose first 4 KiB payload page is the accepted common driver.
- A FamiStudio export that fits one of the supported banked layouts: `$2080`, `$3080`, or `$4080` bytes including the NSF header.

Stop rather than weakening validation for a multi-song NSF, PAL-only source, expansion chip, unsupported mapper-side behavior, self-modifying ROM payload, or a conversion that cannot recover an exact loop/terminal state.

## What the converter proves

The core emulates the source INIT and PLAY routines at one call per NTSC frame. It first searches for a repeated complete mutable state. If engine bookkeeping prevents that, it searches for an exact eventual APU-state period with at least three complete repetitions. A stable muted tail is treated as a one-shot ending.

FamiStudio captures the audible channel state into an editable text project. The converter changes only inaudible leading padding to place the loop start and end on exact pattern boundaries, normalizes imported timing to one unit per NTSC frame, and exports a fresh NSF.

It then replaces the generated first 4 KiB payload page with the exact reference page. Validation has two layers:

1. Generated-driver versus reference-bound output: compare semantic audible targets, including pulse timer-high shadows at `$02A0/$02A1`. This accepts the known difference between sweep-assisted and direct timer-high writes without accepting a pitch, volume, or timing change.
2. Source versus final output: compare channel enable, pulse duty, volume, pitch, triangle, noise, and DPCM trigger/sample semantics frame by frame across the recovered song timeline.

The report must show `apuStateMismatchFrames: 0`. Pulse channels must have zero on/off and duty mismatches, zero mean volume error, and 100% of non-sweep pitch comparisons within 25 cents. Triangle/noise/DPCM mismatch counters must also be zero.

## Hardware sweep

During an enabled hardware sweep, raw `$4002/$4003` or `$4006/$4007` images can remain static while the APU's audible period changes. FamiStudio unfolds the audible sweep. The report therefore counts these as `sourceHardwareSweepFrames` and excludes only those frames from raw-register pitch comparison; all remaining pitch frames must still pass exactly.

## DPCM

FamiStudio 4.5.3 can omit the last byte of a `16n+1` sample on import and later pad it with zero. Do not waive a DPCM-trigger mismatch. Supply the byte-exact sample through a manifest:

```json
{
  "tracks": [
    {
      "file": "track.nsf",
      "title": "Track",
      "dpcmSamples": {
        "Sample 0": { "file": "samples/sample-0.dmc" }
      }
    }
  ]
}
```

Paths inside the manifest are relative to the manifest file. A sample value may instead use `{ "hex": "..." }`.

## Preserved driver offsets

The default is an exact reference-driver page. Preserve bytes from the newly generated driver only when the reference page contains a known song-specific configuration location and the offset has been reviewed. Use `--preserve-driver-offset` globally or `preserveDriverOffsets` per manifest track. Offsets are relative to the 4 KiB driver page, not the NSF file.

Every preserved offset weakens byte identity and must be documented in the report and task evidence.

## Manifest shape

All fields except `tracks[].file` are optional:

```json
{
  "outputPrefix": "Game name",
  "projectName": "Game name - refined common driver",
  "preserveDriverOffsets": ["0x123"],
  "tracks": [
    {
      "file": "01 - Track.nsf",
      "title": "Track",
      "outputPrefix": "Game name",
      "preserveDriverOffsets": ["0x456"],
      "dpcmSamples": {
        "Sample 0": { "hex": "00112233" }
      }
    }
  ]
}
```

Global and per-track preserved offsets are combined. In `mitsume` profile, do not override the file list or selector assumptions.
