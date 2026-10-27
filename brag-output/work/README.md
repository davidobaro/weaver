# Render notes

The movie uses copies of Weaver's actual React components and stylesheet. Only the copies in this folder have film adapters. App state and ForYou feed are injected as fictional fixtures; network access is stubbed. The main app is unchanged. Frame state is a pure function of `renderFrame(seconds)`; all transitions are calculated from that time. Fonts are downloaded locally and awaited before capture.

- `film.tsx`: timeline, composition, fictional fixtures
- `film.css`: focus framing and readable enlargement
- `src/`: reused product source with isolated fixture adapters
- `render.mjs`: local Chrome frame rendering, using Playwright
- `audio.py`: original stereo D-major music and matching soft UI cues
- `encode.py`: poster, frame-zero replacement, H.264/AAC encoding, full decode verification
- `brag-plan.md` in the parent folder: creative direction and scene timing

For a future rerender: serve this directory with the project's Vite and this config on port 4317; run render.mjs check, inspect the PNGs, then render.mjs render, audio.py, and encode.py. The final video has 666 frames at 30fps. The poster replaces frame zero without extending the timeline.
