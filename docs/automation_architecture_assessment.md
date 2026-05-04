# Amber local automation architecture assessment

## Executive summary

The complete agent context strengthens the original conclusion: the recommended architecture is feasible, and the right first move is a narrow local automation layer in Amber with the agent brain kept outside the editor. Amber should expose deterministic, undoable editing tools over stdio JSON-RPC/MCP; a separate Cursor SDK process should plan, call tools, request previews, critique outputs, and iterate.

After reviewing the repository and the full context, the most important adjustment is scope discipline. The full plan's acceptance criteria ask the first Cursor-agent implementation to expose at least four read-only tools and two mutation tools, but the safest first repository PR should still prove the control plane with read-only tools plus one or two very small mutations (`undo`, `redo`, and possibly explicit-path `save_project`). `import_media`, `add_clip`, render preview, and export are feasible, but they cross modal-dialog, media-analysis, timeline-panel, QRhi, and worker-thread boundaries that should be handled only after the stdio dispatcher and object identity model are proven.

The Nia prior-art research also changes the recommendation from "make some JSON tools" to "design a stable editor command contract." Amber should borrow timeline vocabulary from OpenTimelineIO, command transaction concepts from OpenShot's JSON `UpdateAction` model, modular MCP surface ideas from DaVinci Resolve MCP/video-editing MCP projects, and sidecar-process boundaries from Kdenlive/MLT rather than inventing ad hoc editing semantics.

## What changed after seeing the complete context

The first assessment already identified the core Amber seams correctly: `AmberGlobal`, `ProjectModel`, `amber::ActiveSequence`, panel globals, `ComboAction`, `amber::UndoStack`, `Timeline`, `Effect`, `RenderThread`, and `ExportThread`. The full context adds these important refinements:

1. **Prior art matters for schema design.** The initial assessment treated tool names as mostly local wrappers. With the Nia outputs, the tool schema should be informed by existing video automation systems:
   - OpenTimelineIO for edit verbs and timeline concepts.
   - OpenShot's transactional JSON action bus for undoable command payload shape.
   - DaVinci Resolve MCP and video-editing MCP projects for MCP resource/tool organization.
   - MLT and Kdenlive for keeping heavy media/perception tasks outside the GUI editor core.
2. **The external agent loop is part of the architecture, not a later detail.** Amber's tool API should return timeline state and preview artifacts in forms useful to an evaluator loop: stable IDs, source ranges, track data, effects/keyframes, preview file paths, and task IDs.
3. **The first implementation target is larger than a pure read-only skeleton, but still should be staged.** The provided acceptance criteria say "at least 4 read-only tools and 2 mutation tools." The narrowest safe interpretation is read-only tools plus `undo`/`redo`; `save_project` can count only if it never opens a dialog and the project path is explicit or already known.
4. **Future-agent handoff should be explicit.** The doc now includes notes for future coding agents, local Nia report paths, and a warning not to collapse all phases into one PR.
5. **Headless mode is clearly later.** The full context mentions optional `--automation-headless`; repo inspection confirms the first phase should still create the normal Qt app because many "model" operations currently touch panels and `AppContext`.

## Full-plan fit assessment

### Strategic architecture decision

The full context recommends:

1. Add a local automation layer inside Amber.
2. Expose editing tools over stdio JSON-RPC 2.0, framed as MCP.
3. Keep all project mutations on the GUI thread.
4. Route mutations through existing `ComboAction` + `amber::UndoStack`.
5. Run Cursor SDK externally as the agent brain.
6. Let the external agent call Amber tools, request preview frames, evaluate results, and iterate.

This architecture fits the codebase. The split is especially important for Amber because it is a lightweight, thread-sensitive Qt/FFmpeg editor. Embedding an LLM directly into Amber would add network/auth/model orchestration concerns to a process that already coordinates UI panels, render threads, cache threads, preview generators, and FFmpeg export. A deterministic local tool server keeps Amber's responsibility narrow.

### Why stdio MCP first fits Amber

The full context's reasons for stdio MCP first are valid in this repo:

- No local port, auth, or DNS-rebinding surface.
- Parent-process trust model fits a Cursor SDK launcher.
- stdout/stdin JSON-RPC is easier to gate behind `--automation-stdio`.
- Qt already provides `QJsonDocument`, `QJsonObject`, `QThread`, and queued method invocation.
- HTTP can be layered later once command semantics and task lifecycles are stable.

Repo caveat: stdout must be reserved for protocol messages in automation mode. `src/main.cpp` installs the internal logger with `qInstallMessageHandler(debug_message_handler)` when `use_internal_logger` is true, but automation mode should still force diagnostics away from stdout.

## Repository-grounded feasibility

### 1. Local automation layer inside Amber

Feasible. The application has centralized state and a single GUI executable:

- Entry point: `src/main.cpp`, `main()`.
- Command-line parsing: `handle_flag()` and `parse_args()` in `src/main.cpp`.
- Global app object: `src/global/global.h/.cpp`, `AmberGlobal`; instance at `amber::Global`.
- Active project filename: `amber::ActiveProjectFilename`.
- Active sequence: `src/engine/sequence.cpp`, `SequencePtr amber::ActiveSequence`.
- Project model: `src/project/projectmodel.h/.cpp`, `ProjectModel amber::project_model`.
- UI panel globals: `src/panels/panels.cpp`, `panel_project`, `panel_timeline`, `panel_sequence_viewer`, `panel_effect_controls`, `panel_graph_editor`.

The suggested source layout is appropriate:

```text
src/automation/
  CMakeLists.txt
  automationserver.h/.cpp
  jsonrpc.h/.cpp
  commands.h/.cpp
  serialize.h/.cpp
  mcp_tools.h/.cpp
```

Recommended ownership:

- `automationserver`: stdio reader/writer, request lifecycle, server shutdown, JSON-RPC framing.
- `jsonrpc`: request/response/error envelopes using `QJsonDocument`.
- `commands`: dispatch table and GUI-thread marshaling.
- `serialize`: project, media, sequence, clip, effect, marker, guide, and task JSON.
- `mcp_tools`: `initialize`, `tools/list`, `tools/call` adapters and schemas.

Build integration should start in the GUI executable, not `amber-engine`. `src/CMakeLists.txt` has an `amber-engine` object library for engine/rendering/project/global config pieces, but `AmberGlobal`, panels, and `main.cpp` are in `UI_SOURCES`. Since useful automation commands currently need panel and global UI seams, the first automation module should be linked into `${AMBER_TARGET}`.

### 2. GUI-thread dispatch

The full context says all mutations must run on the GUI thread. Repo inspection shows read-only snapshots should also run on the GUI thread.

Verified GUI-owned or GUI-adjacent state:

- `AmberGlobal::set_sequence()` in `src/global/global.cpp` calls `ProjectIO::setSequence()`, clears graph/effect panels, updates the sequence viewer, updates preview labels, updates the timeline, and sets focus.
- `ProjectModel::appendChild()`, `moveChild()`, and `removeChild()` in `src/project/projectmodel.cpp` emit Qt model signals.
- `Project::process_file_list()` in `src/panels/project.cpp` mutates media and can launch `PreviewGenerator::AnalyzeMedia()`.
- `Timeline::split_clip*()`, `Timeline::add_clips_from_ghosts()`, and many timeline operations depend on `panel_timeline`, active selections, `panel_sequence_viewer`, and `update_ui()`.
- `update_ui()` in `src/panels/panels.cpp` touches effect controls, timeline, viewer, and graph editor.
- Several undo commands call `amber::app_ctx` methods that map back to UI panels through `AppContextImpl`.

Recommended dispatch pattern:

1. Automation thread reads one JSON-RPC frame from stdin.
2. It parses `QJsonObject params` and validates JSON shape only.
3. It invokes a GUI-thread `AutomationDispatcher` with `QMetaObject::invokeMethod`.
4. Fast commands can use `Qt::BlockingQueuedConnection`; long tasks return `task_id` immediately and report state through polling.
5. The GUI-thread handler reads or mutates Amber state.
6. The automation thread serializes the response to stdout.

The automation thread must never dereference `Media*`, `Sequence*`, `Clip*`, `Effect*`, `Cacher`, or `QRhi` resources.

### 3. Undo/redo and mutations

The undo system is the correct mutation seam:

- Global stack: `src/engine/undo/undostack.h/.cpp`, `QUndoStack amber::UndoStack`.
- Grouped command: `src/engine/undo/comboaction.h/.cpp`, `ComboAction`.
- Base command: `src/engine/undo/undoactions.h`, `AmberAction`.
- Clip commands: `MoveClipAction`, `DeleteClipAction`, `AddClipCommand`, `SetClipProperty`, `SetSpeedAction`, `RenameClipCommand` in `src/engine/undo/undo_clip.h/.cpp`.
- Media commands: `AddMediaCommand`, `DeleteMediaCommand`, `ReplaceMediaCommand`, `MediaMove`, `MediaRename` in `src/engine/undo/undo_media.h/.cpp`.
- Timeline commands: `RippleAction`, `ChangeSequenceAction`, `SetTimelineInOutCommand`, `EditSequenceCommand` in `src/engine/undo/undo_timeline.h/.cpp`.
- Effect commands: `AddEffectCommand`, `SetEffectData`, `KeyframeAdd`, `KeyframeDataChange`, transition commands in `src/engine/undo/undo_effect.h/.cpp`.

Important caveat: command side effects are not uniform. `AddMediaCommand::AddMediaCommand()` calls `doRedo()` immediately, while most commands apply on `QUndoStack::push()`. Automation should introduce a tiny edit helper that knows these differences and ensures each tool pushes exactly one undoable user action and calls `update_ui(true)` at most once.

## Prior-art/Nia research implications

The full context summarizes Nia tracer/oracle outputs. Those findings should shape the command and schema design even before implementation.

### burningion/video-editing-mcp

Relevant pattern: MCP server for video editing, resource URIs, OTIO output, lazy loaders, and defensive resource polling.

Implication for Amber:

- Use MCP resource-like IDs for project/media/sequence/clip/effect/task references rather than exposing raw pointers.
- `tools/list` schemas should be explicit and stable.
- Long-running render/export/media-analysis tools should use polling-friendly task resources.

### samuelgursky/davinci-resolve-mcp

Relevant pattern: mature NLE MCP surface with both granular and compound tools organized per resource.

Implication for Amber:

- Keep granular tools (`add_clip`, `split_clip`, `set_effect_param`) separate from later compound tools (`make_short_variant`, `remove_silence`).
- Do not hide deterministic edit operations behind high-level "agent magic."
- Organize commands around project, media, sequence, timeline, effects, preview, and export modules.

### OpenTimelineIO

Relevant pattern: canonical timeline IR and edit algorithms: overwrite, insert, trim, slice, slip, slide, ripple, roll, fill, remove.

Implication for Amber:

- Tool semantics should use OTIO vocabulary where practical.
- `inspect_timeline` JSON should be close enough to OTIO concepts that a future OTIO export/import layer is straightforward.
- `add_clip` should distinguish overwrite vs insert/ripple behavior, not just "append a clip somewhere."

### OpenShot

Relevant pattern: JSON command bus with `type`, `key`, `values`, `old_values`, and `transaction`.

Implication for Amber:

- Amber's public tool payloads should look transactional even though the implementation uses `ComboAction`.
- A future internal "automation command IR" can map JSON operations to undo commands, making validation, dry-run, and audit logging easier.
- Returning old/new state snippets can help an agent verify edits without re-inspecting the whole timeline.

### Kdenlive

Relevant pattern: Qt/C++ NLE using Python sidecars for OTIO and AI helpers.

Implication for Amber:

- Perception sidecars such as Whisper, scene detection, shot detection, OCR, and embeddings do not need to be embedded in Amber.
- Amber should expose media/timeline hooks and preview outputs; sidecars can run outside and feed results to the external Cursor SDK agent.

### MLT

Relevant pattern: headless engine, `melt` CLI, and bindings across languages.

Implication for Amber:

- Long term, Amber may benefit from a cleaner headless command engine, but the current repo is not there yet.
- `--automation-headless` should wait until commands no longer depend on panel globals for correctness.

### MoviePy

Relevant pattern: fluent Python timeline DSL.

Implication for Amber:

- A future SDK layer can provide ergonomic high-level editing in Python/TypeScript while mapping to granular MCP tools.
- Do not force that DSL into Amber's C++ core.

### CapCut/Jianying draft automation projects

Relevant pattern: manipulating editor draft/timeline files and wrapping them in HTTP/MCP APIs.

Implication for Amber:

- Useful for social-video workflow schemas and caption/style command shapes.
- Less useful as an implementation model because Amber can mutate a real open timeline through undoable commands instead of patching closed-editor draft files.

## MVP tool-by-tool assessment

### Read-only tools

These are low-risk if dispatched on the GUI thread and serialized from validated object references:

- `inspect_project`: use `amber::ActiveProjectFilename`, `AmberGlobal::is_modified()`, `amber::UndoStack.canUndo()/canRedo()`, and root `amber::project_model`.
- `list_sequences`: use `Project::list_all_project_sequences()` or recursively traverse `amber::project_model.childCount()/child()`.
- `list_media`: recurse `ProjectModel`; serialize `Media::get_type()`, `Media::get_name()`, `Footage` metadata (`url`, `ready`, tracks), and sequence metadata.
- `get_active_sequence`: serialize `amber::ActiveSequence`.
- `inspect_timeline`: serialize `Sequence::clips`, `Sequence::markers`, `Sequence::guides`, `Sequence::playhead`, work area, dimensions, frame rate, and track limits.
- `inspect_clip`: serialize `Clip` accessors (`timeline_in/out`, `clip_in`, `track`, `media`, `effects`, `linked`, transitions).
- `inspect_effects`: serialize global `effects` (`EffectMeta`) and clip effect rows/fields.

Stable ID risk: Amber has no durable runtime object IDs. Public IDs should be structural and validated every call, for example:

- `media:/0/3` for project tree paths.
- `sequence:/0/3` for a media item that wraps a sequence.
- `clip:sequence:/0/3:12` for clip index 12 in a sequence.
- `effect:clip:sequence:/0/3:12:2` for effect index 2 on that clip.

This is not as robust as true UUIDs, but it is safer than exposing raw pointer strings. If an undo/delete invalidates the path, return `stale_reference`.

### Mutation tools

Feasible, but should be phased:

- `undo`, `redo`: `AmberGlobal::undo()` / `redo()` already route to `amber::UndoStack` and `update_ui(true)`, guarded by `panel_timeline->importing`.
- `save_project`: `AmberGlobal::save_project()` is safe only when `amber::ActiveProjectFilename` is non-empty. Automation should require an explicit path for "save as" to avoid `QFileDialog`.
- `import_media`: `Project::process_file_list()` is close, and `AppContext::processFileList()` is a useful seam. It currently has interactive `.ove` import and image-sequence prompts, so MVP should reject prompt-requiring cases or require explicit policies.
- `create_sequence`: `Project::create_sequence_internal()` already builds the `Media` wrapper and can append `ChangeSequenceAction`.
- `add_clip`: `Timeline::create_ghosts_from_media()` + `Timeline::add_clips_from_ghosts()` contain existing behavior, but they use timeline panel state (`ghosts`, `video_ghosts`, `audio_ghosts`, seek side effects). Either call them only on the GUI thread with cleanup or extract an automation-safe helper.
- `move_clip`: use `Clip::move()` into a `ComboAction`, then push.
- `split_clip`: `Timeline::split_clip_and_relink()` and `split_all_clips_at_point()` already compose the right commands.
- `ripple_delete`: current behavior is selection-driven in `Timeline`; automation should accept explicit clip IDs or `{track, in, out}` and internally build temporary selections or extract deletion logic.
- `add_text`, `add_subtitle`: internal effects exist (`EFFECT_INTERNAL_TEXT`, `EFFECT_INTERNAL_RICHTEXT`, `EFFECT_INTERNAL_SUBTITLE`), but the clip/object creation path should be extracted before exposing this as stable API.
- `apply_effect`: use `Effect::GetInternalMeta()` / `get_meta_from_name()` and `AddEffectCommand`.
- `set_effect_param`: `SetEffectData` can replace serialized effect state, but field-level typed mutation is the better long-term contract.
- `set_keyframe`: `KeyframeAdd` / `KeyframeDataChange` exist; deterministic field identity and typed value schemas need follow-up design.

### Preview/export tools

Technically possible but should follow safe mutations:

- `render_preview_frame`: `RenderThread::start_render()` accepts a save path and a caller-supplied pixel buffer. `ViewerWidget::save_frame()` demonstrates save-to-file use. Automation should run this as a task and return a PNG/JPG path plus frame/timecode metadata.
- `export_sequence`: `ExportThread` has `ExportParams`, `VideoCodecParams`, `ProgressChanged`, and `Interrupt()`. Automation should wrap `ExportThread` directly, not instantiate `ExportDialog`.
- `start_export_task`, `get_task_status`, `cancel_task`: need a task registry, progress snapshots, cancellation, and per-sequence busy state.

Rendering/export risk: `ExportThread::EncodeAllFrames()` currently increments `seq_->playhead` from the export thread. That exists today, but automation must prevent timeline mutations while export reads/mutates sequence state, or later render from immutable snapshots.

## Agentic editor loop fit

The full context's agent loop is compatible with Amber if the API returns state useful for planning and critique:

1. Ingest media through `import_media`.
2. Run perception sidecars outside Amber: ffprobe, Whisper, diarization, scene/shot detection, silence/beat detection, OCR, image embeddings, face/object detection.
3. Build timeline state JSON via read-only tools.
4. External Cursor SDK agent plans an edit.
5. Agent calls deterministic Amber mutation tools.
6. Amber mutates the real timeline through undo commands.
7. Agent requests preview frames or preview segments.
8. Vision/perception layer critiques pacing, captions, framing, continuity, audio sync, and style.
9. Agent iterates using undo/redo or future snapshots.
10. Amber exports through an async task.

API design implications:

- Timeline JSON should include project metadata, sequences, tracks, clips, source paths/ranges, linked IDs, effects, params, keyframes, markers, subtitles, media bin, and export settings.
- Preview endpoints should return file paths, frame/timecode metadata, and task IDs.
- Compound tools should be later layers built on granular tools, not replacements for them.

## Source seams verified

### Startup and command-line

- `src/main.cpp`
  - `handle_flag()` and `parse_args()` are the right place to add `--automation-stdio`.
  - `main()` creates `AmberGlobal`, `QApplication`, `MainWindow`, connects first-paint initialization, and starts the event loop.
  - Automation mode should still create `QApplication` and `MainWindow` for MVP because many model operations touch panels.
  - Automation mode should suppress release-only `DemoNotice` in `AmberGlobal::finished_initialize()`.

### Global project/session

- `src/global/global.h/.cpp`
  - `AmberGlobal::save_project()`, `save_project_as()`, `update_project_filename()`.
  - `AmberGlobal::set_sequence()`, `go_back_sequence()`.
  - `AmberGlobal::undo()`, `redo()`.
  - `AmberGlobal::OpenProjectWorker()` clears project, updates filename, starts load, clears undo.
- `src/global/projectio.h/.cpp`
  - `ProjectIO::setSequence()` owns `amber::ActiveSequence` assignment.
  - `ProjectIO::setModified()` tracks modified state and emits signals.
  - This is a useful future seam for reducing direct UI dependency, but it is not sufficient alone today.

### AppContext

- `src/core/appcontext.h`
  - Existing UI-decoupling interface.
  - Useful methods include `listAllSequences()`, `processFileList()`, `setModified()`, `updateUi()`, and `clearViewerMedia()`.
- `src/ui/appcontextimpl.h/.cpp`
  - Bridges `AppContext` calls back to panels and `AmberGlobal`.
- `src/tests/test_ui_stubs.cpp`
  - Shows existing tests already stub UI layer symbols, which can help future automation serialization tests.

### Project/media

- `src/project/projectmodel.h/.cpp`
  - `ProjectModel::appendChild()`, `moveChild()`, `removeChild()`.
  - `ProjectModel::child()` / `childCount()` for tree traversal.
- `src/project/media.h/.cpp`
  - `Media::set_footage()`, `set_sequence()`, `set_folder()`, `get_type()`, `get_name()`, `to_footage()`, `to_sequence()`.
- `src/project/footage.h`
  - `Footage` and `FootageStream` expose metadata needed for `list_media`.
- `src/project/previewgenerator.h`
  - `PreviewGenerator::AnalyzeMedia(Media*)` is the async media analysis seam.
- `src/panels/project.h/.cpp`
  - `Project::create_sequence_internal()`.
  - `Project::process_file_list()`.
  - `Project::save_project()`.
  - `Project::list_all_project_sequences()`.

### Timeline and clips

- `src/engine/sequence.h/.cpp`
  - `Sequence::clips`, `markers`, `guides`, `selections`, `playhead`, work area, width/height/frame rate/audio settings.
  - `Sequence::getEndFrame()`, `getTrackLimits()`.
- `src/engine/clip.h/.cpp`
  - `Clip::move()`, `copy()`, `refresh()`.
  - Accessors for media, timing, track, speed, enabled state, transitions, effects.
  - `Clip::Open()`, `Cache()`, `Retrieve()`, `Close()` are rendering/cacher territory and should not be touched by automation mutation code.
- `src/panels/timeline.h/.cpp`
  - `Timeline::create_ghosts_from_media()`, `add_clips_from_ghosts()`.
  - `ripple_clips()`.
  - Other useful operations listed in the full context: `delete_areas_and_relink`, `three_point_insert`, `three_point_overwrite`, `edit_to_in_point`, `ripple_to_in_point`.
- `src/panels/timeline_splitting.cpp`
  - `Timeline::split_clip()`, `split_clip_and_relink()`, `split_all_clips_at_point()`, `split_at_playhead()`.

### Effects

- `src/effects/effect.h/.cpp`
  - `EffectMeta`, global `effects`, `Effect::Create()`, `Effect::GetInternalMeta()`, `get_meta_from_name()`.
  - `Effect::save_to_string()` / `load_from_string()` can support presets or coarse mutation, but not an ideal typed public contract.
- `src/effects/effectfield.h`, `effectrow.h`, `fields/*`
  - Need follow-up inspection before designing typed parameter schemas.
- `src/effects/internal/texteffect.*`, `richtexteffect.*`, `subtitleeffect.*`
  - Existing building blocks for text/subtitle tools.
- Frei0r/ImageFlag note from the full context:
  - Adding/removing ImageFlag effects can require Cacher reconfigure. Automation effect mutations must close/reopen or route through existing refresh/reconfigure behavior rather than touching `Cacher`.

### Rendering/export

- `src/rendering/renderthread.h/.cpp`
  - `RenderThread::start_render()`, `ready`, `frame_save_failed`.
  - CPU readback through `get_frame_data()`, `get_frame_width()`, `get_frame_height()`.
- `src/ui/viewerwidget.h/.cpp`
  - `ViewerWidget::save_frame()` demonstrates save-frame use of `RenderThread`.
  - Viewer owns a long-lived `RenderThread`.
- `src/rendering/exportthread.h/.cpp`
  - `ExportParams`, `VideoCodecParams`, `ExportThread::Interrupt()`, `ProgressChanged`.
  - `ExportThread::EncodeAllFrames()` currently mutates `seq_->playhead` from the export thread.
- `src/dialogs/exportdialog.cpp`
  - Owns current export UI coordination, progress, cancellation, rendering-state restoration, and playhead restoration.

### Build/tests

- `src/CMakeLists.txt`
  - Main executable target is `${AMBER_TARGET}`.
  - `amber-engine` object library contains engine/rendering/project/global config/projectio pieces.
  - GUI sources are collected in `UI_SOURCES`; automation GUI integration can start here.
- `src/tests/CMakeLists.txt`
  - Tests link `amber-engine` with `test_ui_stubs.cpp`.
  - A future automation command/serialization layer can be tested if kept independent of panels or given stubs.

## Recommended implementation phases

These phases incorporate the full context and repo-grounded constraints.

### Phase 0: prepare branch

- Work on `2.0.lawmight` or a feature branch based on it.
- Keep this separate from upstream `2.0.x`.
- Avoid render internals unless necessary.
- Do not hand-write `.ove` XML in automation.

### Phase 1: read-only automation

Implement:

- `--automation-stdio` flag.
- JSON-RPC/MCP `initialize`, `tools/list`, `tools/call`.
- GUI-thread dispatcher.
- `inspect_project`.
- `list_media`.
- `list_sequences`.
- `get_active_sequence`.
- `inspect_timeline`.
- README snippet or `docs/` note for running automation mode.

Verify:

- Amber launches normally without the flag.
- Automation mode speaks valid JSON-RPC over stdio.
- Read-only commands run on GUI thread and do not open dialogs.

### Phase 2: safe mutations

Implement:

- `undo`.
- `redo`.
- `save_project` / `save_project_as` with explicit noninteractive path rules.
- `create_sequence`.
- `import_media` with prompt-free policies.
- `add_clip` through existing ghost/media import behavior or extracted helper.
- `split_clip`.
- `ripple_delete`.

Rules:

- Every mutation runs on GUI thread.
- Every project mutation uses `ComboAction` + `amber::UndoStack` unless it is an existing global slot that already does.
- No direct `Clip` field writes from automation command handlers except inside existing undo command construction paths.

### Phase 3: preview

Implement:

- `render_preview_frame`.
- Return PNG/JPG file path, frame/timecode metadata, and task ID if async.
- Timeout handling.
- Per-sequence busy state or mutation rejection while render is active.

Avoid:

- Direct QRhi resource ownership in automation.
- Touching `Cacher` internals.

### Phase 4: external agent harness

Implement outside Amber:

- Cursor SDK runner that launches/connects to Amber MCP stdio.
- Media understanding sidecars.
- Simple edit workflows first: silence removal, captions, short variants.

Amber should not know Cursor SDK internals.

### Phase 5: richer workflows

Add later:

- Agent-facing compound tools.
- OTIO import/export.
- Sidecar Python tools for Whisper and scene detection.
- Preview segment rendering.
- Branch/snapshot support.
- Render queue / batch export integration if roadmap work lands.

## Narrowest first PR shape

The full context says the first Cursor-agent implementation should expose at least four read-only tools and two mutation tools. To satisfy that without overreaching, the narrow first PR should include:

### Files

- `src/automation/CMakeLists.txt`
- `src/automation/automationserver.h/.cpp`
- `src/automation/jsonrpc.h/.cpp`
- `src/automation/commands.h/.cpp`
- `src/automation/serialize.h/.cpp`
- `src/automation/mcp_tools.h/.cpp`
- `src/main.cpp` for `--automation-stdio`
- `src/CMakeLists.txt` wiring
- A short automation README or docs page
- A smoke script or Qt test where practical

### Tools

Read-only:

- `inspect_project`
- `list_media`
- `list_sequences`
- `inspect_timeline`
- `get_active_sequence` if time permits

Mutations:

- `undo`
- `redo`

Optional third mutation:

- `save_project_as` with explicit path, or `save_project` only when `amber::ActiveProjectFilename` is non-empty.

### Why not `import_media` in the first PR?

`import_media` is important for a useful agent, but the current seam `Project::process_file_list()` can prompt for `.ove` project imports and image sequence decisions, mutates project media, and launches preview analysis. It is feasible in Phase 2 after noninteractive policies and structured errors are in place.

### Why not `render_preview_frame` in the first PR?

`RenderThread` can already save/read frames, but preview tasks introduce QRhi backend concerns, task lifetime, timeouts, and render-vs-mutation races. It should follow the dispatcher and busy-state work.

## Acceptance criteria

### First automation PR acceptance criteria

Adjusted from the full context and repo inspection:

- Compiles on `2.0.lawmight`.
- Does not change normal Amber launch behavior.
- Adds automation mode behind explicit `--automation-stdio`.
- Speaks valid JSON-RPC/MCP `initialize`, `tools/list`, `tools/call`.
- Exposes at least four read-only tools.
- Exposes two safe mutation tools (`undo` and `redo`) through GUI-thread dispatch.
- Preserves undo/redo for all mutations.
- Avoids direct `Clip`, `Cacher`, and `QRhi` manipulation.
- Avoids modal dialogs in automation paths.
- Includes a short README/docs note for running automation mode.
- Includes one smoke test or script that calls `inspect_project` and one mutation command.

### Later first Cursor-agent implementation acceptance criteria

Once Phase 2/3 exist, a successful external-agent demo should:

- Launch Amber in automation mode.
- Import media with explicit noninteractive params.
- Create a sequence.
- Add clips.
- Perform at least one edit mutation with undo/redo preserved.
- Render a preview frame.
- Feed preview/timeline state back to the external Cursor SDK loop.
- Export or save the project without blocking on UI dialogs.

## Key risks and mitigations

### Risk: accidental cross-thread project access

Impact: crashes, stale pointers, corrupted timeline state, or intermittent render/export failures.

Mitigation: all command handlers, including read-only serialization, execute on a GUI-thread dispatcher. The stdio thread must never dereference editor objects.

### Risk: modal dialogs in automation paths

Impact: the external agent hangs waiting for a dialog nobody can answer.

Mitigation: add noninteractive automation wrappers. Reject commands that would prompt. Require explicit policies for image sequences and project imports. Require explicit save paths where needed. Suppress launch notices in automation mode.

### Risk: undo command side effects are inconsistent

Impact: double-applying commands or failing to mark UI/project modified.

Mitigation: create a small automation edit helper that owns a `ComboAction`, has explicit append helpers for known commands, pushes once, and calls `update_ui(true)` once.

### Risk: pointer-based IDs become invalid after undo/redo/delete

Impact: tools act on the wrong object or crash.

Mitigation: use structural public IDs, validate on every call, and return `not_found` or `stale_reference` errors.

### Risk: render/export races with mutation

Impact: preview frame does not match requested timeline, export advances the user's playhead, or a mutation runs while a render thread reads a clip.

Mitigation: add automation task registry and per-sequence busy state before preview/export. Reject mutations while automation render/export is active. Longer term, render immutable sequence snapshots.

### Risk: headless mode is much larger than stdio mode

Impact: implementing `--automation-headless` first forces replacement/stubbing of panels, QRhi surfaces, dialogs, and app context.

Mitigation: first implement `--automation-stdio` inside the normal GUI process. Revisit headless after commands no longer depend on panel globals.

### Risk: tool semantics drift from video-editing norms

Impact: external agents produce brittle plans because Amber tools use idiosyncratic terms.

Mitigation: borrow OTIO terminology for timeline operations and keep future command IR close to transactional editor models seen in OpenShot and other NLE automation systems.

## Notes for future agents

- Do not try to solve everything in one PR.
- Keep the first PR to automation skeleton, read-only tools, and one or two safe mutations.
- Avoid speculative refactors.
- Amber is lightweight and thread-sensitive; prefer small adapters over rewrites.
- Treat Cursor SDK as the external orchestration layer. Amber exposes tools; it should not know about Cursor internals.
- Use existing undo commands whenever possible.
- Do not mutate `Sequence::clips`, `Clip` fields, `Cacher`, or QRhi resources from the automation thread.
- Do not hand-write `.ove` XML in the automation MVP; use existing project save/load flows.
- Before coding deeper phases, inspect the local Nia research outputs if available:
  - `/opt/data/home/amber-research-results/oracle_automation_api_architecture.md`
  - `/opt/data/home/amber-research-results/oracle_agentic_video_editor_loop.md`
  - `/opt/data/home/amber-research-results/oracle_amber_code_integration_map.md`
  - `/opt/data/home/amber-research-results/tracer_existing_video_editor_automation_projects.md`
  - `/opt/data/home/amber-research-results/tracer_capcut_jianying_draft_api_mcp_projects.md`
  - `/opt/data/home/amber-research-results/tracer_open_source_nle_architectures.md`
  - `/opt/data/home/amber-research-results/summary_for_tom.txt`

