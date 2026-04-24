# Feature demo video

`amber_features_demo.mp4` is a ~82-second 1920x1080 / 30 fps feature tour
showing what Amber adds on top of Olive 0.1 and previewing the upcoming
2.0.x features. It is generated fully from repo assets — no GUI capture.

Structure:

1. **Intro** — title card and "picks up where Olive 0.1 stopped" card.
2. **New foundation** (amber) — Qt RHI / hardware decode / FFmpeg 3.4–8 /
   footprint stats (~3 MB binary, ~70 MB idle RAM, OpenGL 3.2+).
3. **UI tour** — continuous Ken-Burns pan over `.github/amber.jpg`
   highlighting the Viewer, Effect Controls, Timeline, Tools, Project panel.
4. **Quality of life** (amber) — Track Select tool, Shift+Arrow, bold
   timecodes, auto-cut silence.
5. **Coming in 2.0.x** (blue accent) — ShaderToy import, GPU-native effects,
   lift/gamma/gain + scopes, new built-in effects, editing upgrades,
   rendering pipeline, `.ove → .amb`.
6. **Outro** — GPLv3 / 1.x supported / 2.0 in active development.

## Regenerate

```bash
python3 .github/demo/build_demo.py
```

Output lands at `.github/demo/amber_features_demo.mp4`. Intermediate clips and
cards go to `/tmp/demo/`. Requires `ffmpeg`, `ffprobe`, Python 3 with
Pillow (`pip install --break-system-packages Pillow`), and DejaVu fonts.

Editing scenes: each scene is defined in `build_scene_clips()` in
`build_demo.py`. Add an `add(...)` call for a card or `add_shot(...)` for
a screenshot crop; each one takes an explicit `trans=` (`fade`, `fadeblack`,
`slideleft`). Card bullets live in the `make_feature_card(...)` calls in
`generate_cards()`.
