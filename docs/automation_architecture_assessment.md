# Amber local automation architecture assessment

## Executive summary

The proposed architecture is feasible in this codebase if Amber stays the deterministic editing engine and the agent brain remains an external process. The repo already has the right core ingredients: a global project/session object (`AmberGlobal`), a project model (`amber::project_model`), an active sequence pointer (`amber::ActiveSequence`), a Qt undo stack (`amber::UndoStack`), command objects for most editing mutations, and a renderer/export path that can produce CPU-readable frames.

The important constraint is stronger than "mutations on the GUI thread": almost all automation inspection should also run on the GUI thread. The project model, active sequence, timeline selections, effect objects, and many undo commands call UI-facing `AppContext` or panel globals as part of normal operation. A stdio automation thread must therefore only parse/framing JSON and dispatch work to a GUI-thread automation dispatcher.

The narrow first PR should not try to implement the full MCP editing surface. It should add the build/module skeleton, a `--automation-stdio` launch flag, JSON-RPC framing, GUI-thread command dispatch, `initialize` / `tools/list` / `tools/call`, and a small read-only tool set (`inspect_project`, `list_sequences`, `get_active_sequence`, `inspect_timeline`) plus `undo`, `redo`, and `save_project` only if they can be routed through existing slots safely. That first PR proves the control-plane, object identity scheme, GUI-thread marshaling, and deterministic JSON serialization before touching complicated timeline edits or render/export tasks.

## Feasibility of the recommended architecture

### 1. Local automation layer inside Amber

Feasible. The application is a Qt GUI process with centralized globals and panels:

- Entry point: `src/main.cpp`, `main()`.
- Global app object: `src/global/global.h`, `AmberGlobal`; instance at `amber::Global`.
- Active project filename: `amber::ActiveProjectFilename`.
- Active sequence: `src/engine/sequence.cpp`, `SequencePtr amber::ActiveSequence`.
- Project model: `src/project/projectmodel.h/.cpp`, `ProjectModel amber::project_model`.
- UI panel singletons: `src/panels/panels.cpp`, `panel_project`, `panel_timeline`, `panel_sequence_viewer`, `panel_effect_controls`, `panel_graph_editor`.

Adding `src/automation/` is consistent with the current layout. `src/CMakeLists.txt` already separates a reusable `amber-engine` object library from GUI sources, but `AmberGlobal`, panels, and `main.cpp` are in the GUI target. The first automation module should therefore link into the GUI executable, not into `amber-engine`, because the first useful seams are GUI-owned.

### 2. stdio JSON-RPC 2.0 framed as MCP

Feasible with care. `main.cpp` already has a command-line parser (`handle_flag()`, `parse_args()`) for flags such as `--rhi-backend`, `--disable-shaders`, and `--no-debug`, so `--automation-stdio` has a clear insertion point.

Risks:

- MCP over stdio requires stdout to contain only protocol frames. Amber's default internal logger is installed by `qInstallMessageHandler(debug_message_handler)` in `main.cpp`; this helps, but the automation flag should explicitly keep JSON-RPC on stdout and send diagnostics to stderr or the internal debug log.
- The app currently shows release-only launch UI in `AmberGlobal::finished_initialize()` (`DemoNotice` when no project was launched). Automation mode should suppress that prompt.
- Existing UI actions may open modal dialogs (`QFileDialog`, `QMessageBox`). Automation commands must avoid dialog-backed code paths or add noninteractive variants.

### 3. GUI-thread ownership of project state

Required. Verified GUI-owned or GUI-adjacent state includes:

- `AmberGlobal::set_sequence()` in `src/global/global.cpp` updates `ProjectIO`, clears graph/effect panels, updates the sequence viewer, updates the timeline, and sets focus.
- `ProjectModel::appendChild()`, `moveChild()`, and `removeChild()` in `src/project/projectmodel.cpp` emit Qt model insert/move/remove signals.
- `Project::process_file_list()` in `src/panels/project.cpp` mutates project media and can launch `PreviewGenerator::AnalyzeMedia()`.
- `Timeline::split_clip*()`, `Timeline::add_clips_from_ghosts()`, and many timeline operations depend on `panel_timeline`, `panel_sequence_viewer`, active selections, and `update_ui()`.
- `update_ui()` in `src/panels/panels.cpp` touches effect controls, timeline, viewer, and graph editor.

Recommended mechanism:

- Run the stdio JSON-RPC reader/writer in its own `QThread` or a small non-Qt worker.
- Create an `AutomationDispatcher : public QObject` on the GUI thread.
- For every tool call, use `QMetaObject::invokeMethod(dispatcher, ..., Qt::QueuedConnection)` for async calls or `Qt::BlockingQueuedConnection` only for short read-only calls.
- Return structured errors for invalid IDs, no active sequence, media not ready, bad frame ranges, and unsupported effects instead of opening dialogs.

### 4. Route mutations through `ComboAction` + `amber::UndoStack`

Feasible and strongly recommended. The undo system is the best existing mutation seam:

- Global stack: `src/engine/undo/undostack.h/.cpp`, `QUndoStack amber::UndoStack`.
- Grouped command: `src/engine/undo/comboaction.h/.cpp`, `ComboAction`.
- Base command: `src/engine/undo/undoactions.h`, `AmberAction`.
- Clip commands: `MoveClipAction`, `DeleteClipAction`, `AddClipCommand`, `SetClipProperty`, `SetSpeedAction`, `RenameClipCommand` in `src/engine/undo/undo_clip.h/.cpp`.
- Media commands: `AddMediaCommand`, `DeleteMediaCommand`, `ReplaceMediaCommand`, `MediaMove`, `MediaRename` in `src/engine/undo/undo_media.h/.cpp`.
- Timeline commands: `RippleAction`, `ChangeSequenceAction`, `SetTimelineInOutCommand`, `EditSequenceCommand` in `src/engine/undo/undo_timeline.h/.cpp`.
- Effect commands: `AddEffectCommand`, `SetEffectData`, `KeyframeAdd`, `KeyframeDataChange`, transition commands in `src/engine/undo/undo_effect.h/.cpp`.

Important detail: some constructors already perform changes. `AddMediaCommand::AddMediaCommand()` calls `doRedo()` immediately, while most other commands apply on `QUndoStack::push()`. Automation code needs command-specific knowledge or a helper layer that normalizes "build command, push once, update UI once".

### 5. External Cursor SDK agent as the brain

This is the right split. Embedding an LLM in Amber would add auth, model lifecycle, prompt/tool orchestration, and network failure modes to a latency-sensitive Qt/FFmpeg application. A local deterministic tool server lets Cursor SDK plan externally while Amber remains an editor process with stable commands and observable state.

### 6. Preview frames and iterative critique

Feasible after the control-plane and read-only/mutation surfaces are proven. The render path already has CPU readback:

- `RenderThread::start_render()` in `src/rendering/renderthread.cpp` accepts an optional save path and optional pixel buffer.
- `RenderThread::paint()` reads back `front_tex_` into `cpu_frame_`.
- `ViewerWidget::save_frame()` in `src/ui/viewerwidget.cpp` calls `renderer->start_render(viewer->seq.get(), 1, fn)`.
- `ExportThread::EncodeVideoFrame()` in `src/rendering/exportthread.cpp` calls `RenderThread::start_render()` with `video_frame->data[0]`.

However, preview/export should not be in the first PR. Rendering reads `Sequence` and `Clip` state while worker threads are active, and export currently increments `seq_->playhead` from `ExportThread::EncodeAllFrames()`. That behavior exists today, but it is a risk for automation because tool calls can arrive while a render/export task is reading or changing sequence state. Automation preview/export needs a task manager with a per-sequence busy state, cancellation, progress, and clear "no mutation while task is running" rules or a future immutable render snapshot.

## MVP tool-by-tool assessment

### Read-only tools

These are low-risk if dispatched on the GUI thread and serialized without dereferencing stale pointers:

- `inspect_project`: use `amber::ActiveProjectFilename`, `AmberGlobal::is_modified()`, `amber::UndoStack.canUndo()/canRedo()`, root `amber::project_model`.
- `list_sequences`: use `Project::list_all_project_sequences()` or recurse `amber::project_model.childCount()/child()`.
- `list_media`: recurse `ProjectModel`; serialize `Media::get_type()`, `Media::get_name()`, `Footage` metadata (`url`, `ready`, tracks), and sequence metadata.
- `get_active_sequence`: serialize `amber::ActiveSequence`.
- `inspect_timeline`: serialize `Sequence::clips`, `Sequence::markers`, `Sequence::guides`, `Sequence::playhead`, `workarea`.
- `inspect_clip`: serialize `Clip` fields through accessors (`timeline_in/out`, `clip_in`, `track`, `media`, `effects`, transitions).
- `inspect_effects`: serialize global `effects` (`EffectMeta`) and clip effect rows/fields.

Risk: stable IDs do not exist. Use generated automation IDs rather than raw pointer strings in public responses. Internally keep weak-ish mappings that are rebuilt/validated on every request. A practical first scheme is `media:<project-path-index>`, `sequence:<project-path-index>`, `clip:<sequence-id>:<clip-index>`, `effect:<clip-id>:<effect-index>`, with validation that the referenced object still exists.

### Mutations

Feasible, but not all should be first:

- `import_media`: `Project::process_file_list()` is close, but it has interactive prompts for `.ove` project files and image sequence handling. Add a noninteractive wrapper with explicit options (`recursive`, `image_sequence_policy`, reject `.ove` for MVP).
- `create_sequence`: `Project::create_sequence_internal()` already builds `Media` wrappers and can append `ChangeSequenceAction`.
- `add_clip`: `Timeline::create_ghosts_from_media()` + `Timeline::add_clips_from_ghosts()` contain the existing behavior, but they use timeline panel state (`ghosts`, `video_ghosts`, `audio_ghosts`, seek side effects). For automation, extract a service-level "build clips from media import data" helper or call these only on the GUI thread with state cleanup.
- `move_clip`: use `Clip::move()` into a `ComboAction`, then push.
- `split_clip`: `Timeline::split_clip_and_relink()` and `split_all_clips_at_point()` already compose the right commands.
- `ripple_delete`: current implementation is selection-driven in `Timeline`; automation should expose explicit range/track or clip IDs, then create selections internally for the operation or extract the deletion logic.
- `add_text` / `add_subtitle`: internal effect types exist (`EFFECT_INTERNAL_TEXT`, `EFFECT_INTERNAL_RICHTEXT`, `EFFECT_INTERNAL_SUBTITLE`), but the creation UI path should be inspected/extracted before exposing this as a stable tool.
- `apply_effect`: use `Effect::GetInternalMeta()` / `get_meta_from_name()` and `AddEffectCommand`.
- `set_effect_param`: `SetEffectData` can replace serialized effect state. A better tool contract is field-level param mutation that reuses `EffectField` APIs and wraps with undo; this needs more focused design.
- `set_keyframe`: `KeyframeAdd` / `KeyframeDataChange` exist, but field identity and time/value typing need a deterministic schema.
- `undo` / `redo`: `AmberGlobal::undo()` and `redo()` already route to `amber::UndoStack` and call `update_ui(true)`, but they guard on `panel_timeline->importing`.
- `save_project`: `AmberGlobal::save_project()` is safe only when `amber::ActiveProjectFilename` is set. In automation, add `save_project_as(path)` or require an already-open project path; avoid file dialogs.

### Preview/export tools

Technically possible, but should be second or third phase:

- `render_preview_frame`: can use a dedicated `RenderThread` or the existing viewer renderer. It needs a noninteractive API that seeks/sets a target frame on GUI thread, waits for render completion, and writes a file or returns bytes/path. It also needs busy-state protection against concurrent mutation.
- `export_sequence`: can wrap `ExportThread`, `ExportParams`, and `VideoCodecParams`.
- `start_export_task`, `get_task_status`, `cancel_task`: should be backed by an automation task registry. `ExportDialog` currently owns UI progress, cancellation, GL fallback surface lifetime, rendering state, and playhead restoration, so automation should not instantiate the dialog; it should extract a small export coordinator.

## Source seams verified

### Startup and command-line

- `src/main.cpp`
  - `handle_flag()` and `parse_args()` are the right place to add `--automation-stdio`.
  - `main()` creates `AmberGlobal`, `QApplication`, `MainWindow`, connects first-paint initialization, and starts the event loop.
  - Automation mode should still create `QApplication` and `MainWindow` for MVP because many model operations touch panels.

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
  - `Sequence::clips`, `markers`, `guides`, `playhead`, `workarea`.
  - `Sequence::getEndFrame()`, `getTrackLimits()`.
- `src/engine/clip.h/.cpp`
  - `Clip::move()`, `copy()`, `refresh()`.
  - Accessors for media, timing, track, speed, enabled state, transitions, effects.
  - `Clip::Open()`, `Cache()`, `Retrieve()`, `Close()` are rendering/cacher territory and should not be touched by automation mutation code.
- `src/panels/timeline.h/.cpp`
  - `Timeline::create_ghosts_from_media()`, `add_clips_from_ghosts()`.
  - `ripple_clips()`.
- `src/panels/timeline_splitting.cpp`
  - `Timeline::split_clip()`, `split_clip_and_relink()`, `split_all_clips_at_point()`, `split_at_playhead()`.

### Effects

- `src/effects/effect.h/.cpp`
  - `EffectMeta`, global `effects`, `Effect::Create()`, `Effect::GetInternalMeta()`, `get_meta_from_name()`.
  - `Effect::save_to_string()` / `load_from_string()` can support a coarse `set_effect_param` MVP but are not a good long-term typed contract.
- `src/effects/effectfield.h`, `effectrow.h`, `fields/*`
  - Need follow-up inspection before designing typed parameter schemas.
- `src/effects/internal/texteffect.*`, `richtexteffect.*`, `subtitleeffect.*`
  - Existing building blocks for text/subtitle tools.

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

## Key risks and mitigations

### Risk: accidental cross-thread project access

Impact: crashes, stale pointers, corrupted timeline state, or intermittent render/export failures.

Mitigation: all command handlers, including read-only serialization, execute on a GUI-thread dispatcher. The stdio thread must never dereference `Media*`, `Sequence*`, `Clip*`, `Effect*`, or panel globals.

### Risk: modal dialogs in automation paths

Impact: the external agent hangs waiting for a dialog nobody can answer.

Mitigation: add noninteractive automation-specific wrappers. Reject commands that would prompt. Examples: reject `.ove` in `import_media` for MVP; require `save_project.path` when the project has no filename; suppress `DemoNotice` in automation mode.

### Risk: undo command side effects are inconsistent

Impact: double-applying commands or failing to mark UI/project modified.

Mitigation: create a small `AutomationEditBuilder` helper that owns a `ComboAction`, has explicit append helpers for known commands, pushes once, and calls `update_ui(true)` once. Document commands like `AddMediaCommand` whose constructors already call `doRedo()`.

### Risk: pointer-based IDs become invalid after undo/redo/delete

Impact: tools act on the wrong object or crash.

Mitigation: public IDs should be structural and validated on every call. Return a clear `not_found` or `stale_reference` error when a media/clip/effect no longer resolves.

### Risk: render/export races with mutation

Impact: preview frame does not match the requested timeline, export advances the user's playhead, or a mutation runs while a render thread reads a clip.

Mitigation: defer preview/export tools until a task registry and busy-state rules exist. For MVP, read-only and small mutations should reject while an automation render/export task is active. Longer term, render from immutable sequence snapshots or enforce a per-sequence read/write lock with GUI-thread mutations only.

### Risk: headless mode is much larger than stdio mode

Impact: trying to implement `--automation-headless` first will force replacement/stubbing of panels, QRhi surfaces, dialogs, and app context.

Mitigation: first PR should be `--automation-stdio` inside the normal GUI process. Headless should be a later architecture pass after command logic is separated from panels.

## Recommended narrow first PR

### Scope

Add only the automation control-plane and read-only proof tools:

- `src/automation/CMakeLists.txt`
- `src/automation/automationserver.h/.cpp`
- `src/automation/jsonrpc.h/.cpp`
- `src/automation/commands.h/.cpp`
- `src/automation/serialize.h/.cpp`
- `src/automation/mcp_tools.h/.cpp`
- `--automation-stdio` flag in `src/main.cpp`
- CMake wiring in `src/CMakeLists.txt`

### First tools

Implement:

- `inspect_project`
- `list_sequences`
- `get_active_sequence`
- `inspect_timeline`
- `undo`
- `redo`
- `save_project` only when `amber::ActiveProjectFilename` is non-empty, or expose `save_project_as` with an explicit path.

Defer:

- `import_media`
- all clip/effect/keyframe mutations
- preview/export tasks
- headless mode

### Acceptance criteria

- `amber --automation-stdio` starts the normal Qt app and speaks valid JSON-RPC/MCP over stdin/stdout.
- `tools/list` returns stable tool schemas.
- Read-only tool calls are executed on the GUI thread and return deterministic JSON.
- Invalid references and missing active sequence return structured JSON-RPC errors, not dialogs.
- `undo`/`redo` go through `AmberGlobal::undo()` / `redo()` or `amber::UndoStack` on the GUI thread and update UI once.
- `save_project` never opens a dialog in automation mode.
- Unit tests cover JSON-RPC framing and serialization on simple constructed project/sequence data where possible; manual smoke test covers launching `--automation-stdio` and calling `tools/list`.

## Suggested later phases

1. Extract automation-safe edit helpers for create/import/add/move/split/ripple.
2. Add stable typed effect/field serialization and field-level mutation.
3. Add preview frame tasks with per-sequence busy state and deterministic output files.
4. Add export task registry wrapping `ExportThread` without `ExportDialog`.
5. Revisit `--automation-headless` only after project/model/edit commands no longer depend on panel globals for correctness.

