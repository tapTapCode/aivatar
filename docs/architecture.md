# Architecture

`Aivatar Desktop -> localhost Pipeline API -> SQLite/Queue -> provider jobs -> scene intermediates -> FFmpeg final -> QC`

The authoritative clock is `master_voice.wav`. Presenter-returned audio is not authoritative during final assembly. Presenter, image and video providers return assets that are conformed to the master scene boundaries.

## Cost strategy

Use the cheapest acceptable visual path in this order: approved cached asset, FLUX still, FLUX still + FFmpeg motion, LTX motion when genuine motion materially improves the scene.

## External provider boundary

Presenter and voice systems are adapters. HeyGen is the current primary presenter requirement, but the pipeline cannot require HeyGen in order to plan, generate mock assets, render, resume or validate a project.

## Phase 3 presenter boundary

Presenter clips are generated from exact slices of the authoritative master narration. `PRESENTER`, `SPLIT`, and `PIP` scenes all consume the same `PresenterProvider` interface. HeyGen-specific API versioning remains inside the adapter; local FFmpeg composition never depends on which presenter provider produced the clip.

For final assembly, presenter clip audio is discarded. The project-level master narration is always the final speech track.
