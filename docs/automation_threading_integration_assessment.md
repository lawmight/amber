# Amber 2.0.lawmight automation threading and integration assessment

## Scope and conclusion

This assessment reviews the feasibility of adding an explicit `amber --automation-stdio`
mode that exposes deterministic editing tools to an external Cursor SDK agent over
stdio JSON-RPC 2.0 / MCP framing. It does not propose embedding an agent inside
Amber and does not implement automation code.

This revision incorporates the full Amber 2.0.lawmight agent context supplied after
the initial assessment. The local `/opt/data/home/amber-agent-context.md` file and
`/opt/data/home/amber-research-results/` directory were not present in this
environment, so the pasted full context is treated as the exact plan input for this
revision.

The plan is feasible, but only if the automation layer is treated as a thin transport
and dispatch boundary. Stdio parsing and response writing can run on a dedicated
automation thread, but every read or write of project/editor state must execute on
the GUI thread. Mutations should use existing undoable operations (`ComboAction`,
`AmberAction` subclasses, and `amber::UndoStack`) or existing UI/application entry
points that already preserve undo and refresh side effects.

The unsafe path is equally clear: direct writes to `Sequence::clips`, `Clip` timeline
fields, `EffectField` data, `Cacher`, or QRhi-owned resources from the automation
thread would bypass undo, race with renderer/cacher threads, or violate Qt widget and
timer affinity rules.

After reviewing the complete context, the core feasibility judgment is unchanged,
but the recommended first implementation should be narrower and more explicitly
phased than the initial report implied:

- Phase 1 should be read-only MCP plumbing plus inspection tools only.
- Phase 2 should add a very small undo-preserving mutation set.
- Preview/export automation should remain a later task-backed phase.
- The first PR should be an automation skeleton with one or two safe tools, not a
  broad editor automation surface.

## What changed after seeing the full plan

### Confirmed by the full context

The full plan strongly confirms these repo-grounded findings:

- **External Cursor SDK process first.** Amber should expose deterministic local
  tools; the agent brain should run outside Amber. This matches the repo reality:
  the safe seams are Qt/C++ command handlers, not embedded scripting or model code.
- **Stdio MCP first.** The no-port/no-auth parent-process trust model is compatible
  with Amber's desktop app shape and avoids adding HTTP server lifecycle/security
  concerns to an already thread-sensitive Qt application.
- **GUI-thread ownership.** The plan's claim that `OliveGlobal`/`AmberGlobal`,
  `ProjectModel`, `UndoStack`, `amber::ActiveSequence`, clip vector mutations, and
  panel state belong to the GUI thread is supported by the inspected code.
- **Undo as mutation contract.** The plan's requirement to route mutations through
  `ComboAction` + `amber::UndoStack` is exactly what timeline, project, effect, and
  media paths already do.
- **No render internals in automation MVP.** The inspected QRhi/render/export code
  makes this more important, not less.

### Added nuance from repo inspection

The full context says short commands can use `QMetaObject::invokeMethod(...,
Qt::BlockingQueuedConnection)` from the automation thread into a GUI-thread command
handler. That can work for fast commands, but the repo inspection adds important
constraints:

- Blocking calls must never be made from the GUI thread itself; guard against same
  thread invocation and use direct execution when already on the GUI thread.
- Blocking calls must not wrap operations that can show modal dialogs, wait on
  rendering/export, or trigger project load UI.
- Blocking calls must not hold worker-thread locks while waiting, or shutdown can
  deadlock.
- Long operations must use queued async task creation and return `task_id`.

The complete context also broadens the product vision with compound editing tools,
perception sidecars, OTIO, social-video workflows, and preview critique loops. Those
are strategically sound, but the code integration assessment still says they should
sit above a narrow, deterministic, undo-safe primitive layer.

### Corrections to the initial tool ordering

The initial report listed some project operations alongside MVP candidates. With
the complete plan, the order should be stricter:

1. `initialize`, `tools/list`, `tools/call`, and read-only inspection tools.
2. Only then `undo`, `redo`, `save_project`, `import_media`, `create_sequence`,
   `add_clip`, `split_clip`, and `ripple_delete`.
3. Preview/export and compound operations later.

This reduces risk because it first proves JSON-RPC framing, GUI-thread dispatch,
stable IDs, and state serialization without exercising undo or render/export
hazards.

## Full plan comparison

### Strategic architecture

The full plan's architecture is well aligned with the codebase:

- Amber remains the deterministic editing environment.
- Cursor SDK remains an external orchestrator.
- The protocol surface is stdio JSON-RPC 2.0 framed as MCP.
- The launch path is explicit: `amber --automation-stdio`.
- Optional `--automation-headless` should remain future work.

The one integration caveat is that normal GUI initialization should still occur for
the first implementation. Current safe operations rely on `MainWindow`, panel
singletons, `AppContextImpl`, `ProjectModel`, `amber::Global`, and `amber::UndoStack`.
A headless mode would require a separate app-context and panel-free command service
design.

### Suggested `src/automation` layout

The proposed layout is reasonable:

- `src/automation/CMakeLists.txt`
- `automationserver.h/.cpp`
- `jsonrpc.h/.cpp`
- `commands.h/.cpp`
- `serialize.h/.cpp`
- `mcp_tools.h/.cpp`

Repo integration note: `src/CMakeLists.txt` currently builds `amber-engine` plus a
large `UI_SOURCES` list for the executable. The lowest-risk first PR is to add
automation sources to `UI_SOURCES` or add a small automation library linked only by
`${AMBER_TARGET}`. Do not put UI-panel-dependent automation code into
`amber-engine` unless tests/stubs are updated, because `amber-engine` is already
shared with headless tests.

### MCP shape and Nia prior art

The Nia prior-art summary changes the report from "generic JSON-RPC feasibility" to
"MCP-compatible editor tool surface with known precedents":

- `burningion/video-editing-mcp`
  - Useful for MCP shape, resource URIs, lazy loading, OTIO-oriented resources, and
    task/resource polling.
  - Amber should borrow the protocol/resource discipline, not its implementation
    details.
- `samuelgursky/davinci-resolve-mcp`
  - Useful as a mature NLE MCP surface with both granular and compound operations.
  - Amber should first expose granular undo-safe commands, then layer compound
    tools externally.
- OpenTimelineIO
  - Useful canonical IR and vocabulary: overwrite, insert, trim, slice, slip,
    slide, ripple, roll, fill, remove.
  - Amber should not make OTIO import/export part of the first PR, but its JSON
    timeline DTOs should avoid names that conflict with OTIO concepts.
- OpenShot `UpdateAction`
  - Useful precedent for command-bus records carrying `type`, `key`, `values`,
    `old_values`, and `transaction`.
  - Amber already has stronger native undo objects; an automation audit log could
    mimic this shape later.
- Kdenlive Python sidecars
  - Supports the plan's "no embedded scripting first" decision. Perception and AI
    helpers can live outside Amber.
- MLT
  - Demonstrates robust headless engine automation, but Amber's current app is not
    factored as a headless engine. Treat headless as later architecture work.
- MoviePy
  - Good inspiration for a future high-level SDK, not a replacement for Amber's
    native undoable editor operations.
- CapCut/Jianying draft APIs
  - Useful for social-video workflow vocabulary, but too fragile for a core local
    automation contract.

### Agentic editor loop

The loop in the full context is feasible above the MCP layer:

1. ingest media,
2. run perception sidecars,
3. build timeline JSON,
4. agent plans edit,
5. agent calls Amber tools,
6. Amber mutates timeline and renders preview frame/segment,
7. vision/perception critiques output,
8. agent iterates through undo/redo or snapshots,
9. final export.

Repo-grounded implication: Amber should provide stable, deterministic primitives and
preview/export task hooks. It should not own Whisper, diarization, CLIP embeddings,
OCR, face/object detection, or caption critique in the first implementation.

### Timeline JSON expectations

The requested timeline JSON shape is reasonable and should include:

- project metadata,
- sequences,
- tracks,
- clips with timeline in/out, source media, source range, track, linked IDs,
- effects and keyframes,
- markers/subtitles,
- media bin,
- render/export settings.

Implementation warning: external IDs must be per-session stable IDs, not raw
pointers and not bare `QVector` indices without validation. Sequence/clip/effect
indices can change after undo, delete, import, split, ripple, or project reload.

## Files and symbols verified

### Startup, lifecycle, project IO

- `src/main.cpp`
  - `parse_args(int, char**, bool&, QString&, bool&)`
  - `handle_flag(int, char**, int&, bool&, bool&)`
  - `main(int, char**)`
  - `QObject::connect(&w, &MainWindow::finished_first_paint, ..., Qt::QueuedConnection)`
- `src/global/global.h` / `src/global/global.cpp`
  - `AmberGlobal::AmberGlobal()`
  - `AmberGlobal::load_project_on_launch(const QString&)`
  - `AmberGlobal::finished_initialize()`
  - `AmberGlobal::OpenProjectWorker(QString, bool)`
  - `AmberGlobal::LoadProject(const QString&, bool)`
  - `AmberGlobal::ImportProject(const QString&)`
  - `AmberGlobal::save_project()`, `save_project_as()`, `save_autorecovery_file()`
  - `AmberGlobal::set_rendering_state(bool)`
  - `AmberGlobal::undo()`, `redo()`, `clear_undo_stack()`
  - `AmberGlobal::set_sequence(SequencePtr, bool)`, `go_back_sequence()`
- `src/global/projectio.h` / `src/global/projectio.cpp`
  - `ProjectIO::setModified(bool)`
  - `ProjectIO::setRenderingState(bool)`
  - `ProjectIO::setSequence(SequencePtr, bool)`
  - `ProjectIO::goBackSequence()`
  - `ProjectIO::initAutorecovery()`, `reconfigureAutorecovery()`
  - `ProjectIO::autorecoverySaveRequested`

### App context and UI boundary

- `src/core/appcontext.h` / `src/core/appcontext.cpp`
  - `AppContext`
  - `amber::app_ctx`
  - `AppContext::listAllSequences()`
  - `AppContext::processFileList(QStringList&, bool, MediaPtr, Media*)`
  - `AppContext::updateUi(bool)`, `refreshViewer()`, `refreshTimeline()`,
    `refreshEffectControls()`
- `src/ui/appcontextimpl.h` / `src/ui/appcontextimpl.cpp`
  - `AppContextImpl::listAllSequences()`
  - `AppContextImpl::processFileList(...)`
  - `AppContextImpl::updateUi(bool)`
  - dialog/widget methods such as `showMessage`, `showQuestion`,
    `showSaveFileDialog`, `getMainWindow`
- `src/ui/mainwindow.cpp`
  - `MainWindow::init_panels_and_menus()`
  - `amber::app_ctx = new AppContextImpl()`
  - `MainWindow::~MainWindow()`
- `src/panels/panels.h` / `src/panels/panels.cpp`
  - global panel pointers (`panel_project`, `panel_timeline`,
    `panel_sequence_viewer`, `panel_effect_controls`, `panel_graph_editor`)
  - `update_ui(bool modified, bool scrubbing = false)`

### Undo infrastructure

- `src/engine/undo/undostack.h` / `src/engine/undo/undostack.cpp`
  - `amber::UndoStack`
- `src/engine/undo/comboaction.h` / `src/engine/undo/comboaction.cpp`
  - `ComboAction::append(QUndoCommand*)`
  - `ComboAction::appendPost(QUndoCommand*)`
  - `ComboAction::redo()`, `undo()`
  - command ownership in `ComboAction::~ComboAction()`
- `src/engine/undo/undoactions.h`
  - `AmberAction`
- `src/engine/undo/undo_generic.cpp`
  - `AmberAction::redo()` records and sets modified state through
    `amber::app_ctx`
  - `AmberAction::undo()` restores modified state
  - generic pointer/value commands (`SetBool`, `SetInt`, `SetLong`,
    `SetDouble`, `SetString`, `SetPointer`, `SetQVariant`)
  - `CloseAllClipsCommand`, `UpdateViewer`
- `src/engine/undo/undo_clip.h` / `src/engine/undo/undo_clip.cpp`
  - `MoveClipAction`
  - `DeleteClipAction`
  - `AddClipCommand`
  - `ReplaceClipMediaCommand`
  - `SetClipProperty`
  - `SetSpeedAction`
  - `RenameClipCommand`
  - `RefreshClips`
  - `LinkCommand`
- `src/engine/undo/undo_timeline.h` / `src/engine/undo/undo_timeline.cpp`
  - `RippleAction`
  - `ChangeSequenceAction`
  - `SetTimelineInOutCommand`
  - `SetSelectionsCommand`
  - `EditSequenceCommand`
  - marker commands
- `src/engine/undo/undo_media.h` / `src/engine/undo/undo_media.cpp`
  - `AddMediaCommand`
  - `DeleteMediaCommand`
  - `ReplaceMediaCommand`
  - `MediaMove`
  - `MediaRename`
- `src/engine/undo/undo_effect.h` / `src/engine/undo/undo_effect.cpp`
  - `SetEffectEnabled`
  - `AddEffectCommand`
  - `EffectDeleteCommand`
  - `MoveEffectCommand`
  - `SetEffectData`
  - `SetIsKeyframing`
  - transition and keyframe commands

### Timeline, clip, effects, rendering

- `src/engine/sequence.h` / `src/engine/sequence.cpp`
  - `amber::ActiveSequence`
  - `Sequence::clips`, `selections`, `playhead`, work area fields
  - `Sequence::copy()`, `RefreshClips(Media*)`, `SelectedClips()`,
    `SelectedClipIndexes()`, `getTrackLimits()`, `getEndFrame()`
- `src/engine/clip.h` / `src/engine/clip.cpp`
  - `Clip::move(ComboAction*, long, long, long, int, bool, bool)`
  - direct setters (`set_timeline_in`, `set_timeline_out`, `set_clip_in`,
    `set_track`, `set_media`, `set_speed`, `set_enabled`)
  - `Clip::Open()`, `Close(bool)`, `Cache(...)`, `Retrieve(...)`
  - `Clip::NeedsCpuRgba()`, `NeedsCacherReconfigure()`
  - QRhi fields (`cached_rhi_tex`, `yuv_tex_*`, `rgba_tex`, `fbo_rhi`)
- `src/panels/timeline.h` / `src/panels/timeline.cpp`
  - free `ripple_clips(ComboAction*, Sequence*, long, long, const QVector<int>&)`
  - `Timeline::add_clips_from_ghosts(ComboAction*, Sequence*)`
  - `Timeline::delete_areas_and_relink(ComboAction*, QVector<Selection>&, bool)`
  - `Timeline::delete_selection(QVector<Selection>&, bool)`
  - `Timeline::delete_in_out_internal(bool)`
  - `Timeline::edit_to_point_internal(bool, bool)`
  - slots `ripple_to_in_point`, `edit_to_in_point`,
    `three_point_insert`, `three_point_overwrite`
- `src/panels/timeline_splitting.cpp`
  - `Timeline::split_clip(...)`
  - `Timeline::split_clip_and_relink(...)`
  - `Timeline::split_clip_at_positions(...)`
  - `Timeline::split_selection(...)`
  - `Timeline::split_all_clips_at_point(...)`
- `src/effects/effect.h` / `src/effects/effect.cpp`
  - `Effect::Create(Clip*, const EffectMeta*)`
  - `Effect::delete_self()`, `move_up()`, `move_down()`
  - `Effect::load_from_file()` / `SetEffectData`
  - `Effect::SetEnabled(bool)`, `Effect::FieldChanged()`
- `src/effects/effectrow.cpp`
  - `EffectRow::SetKeyframingEnabled(bool)`
  - `EffectRow::ToggleKeyframe()`
  - `EffectRow::SetKeyframeOnAllFields(ComboAction*)`
- `src/effects/effectfield.cpp`
  - `EffectField::SetValueAt(...)`
  - `EffectField::PrepareDataForKeyframing(bool, ComboAction*)`
- `src/rendering/renderthread.h` / `src/rendering/renderthread.cpp`
  - `RenderThread::start_render(...)`
  - `RenderThread::paint()`
  - `RenderThread::DeferRhiResourceDeletion(...)`
  - `RenderThread::cancel()`, `wait_until_paused()`
  - deferred QRhi deletion queue
- `src/rendering/exportthread.h` / `src/rendering/exportthread.cpp`
  - `ExportThread`
  - `ExportThread::run()`, `Export()`, `EncodeAllFrames(...)`
  - `ExportThread::Interrupt()`
  - `ExportThread::ProgressChanged`
- `src/dialogs/exportdialog.cpp`
  - `ExportDialog::launch_export_thread(...)`
  - `ExportDialog::export_thread_finished()`
  - `ExportDialog::build_export_params(...)`

### Build and tests

- `src/CMakeLists.txt`
  - `amber-engine` object library
  - `UI_SOURCES`
  - `AMBER_TARGET`
  - `add_executable(${AMBER_TARGET} ...)`
  - test subdirectory wiring
  - shader/resource setup
- `src/tests/CMakeLists.txt`
  - headless Qt Test executables linked to `amber-engine`
  - `test_ui_stubs.cpp` as UI symbol stubs

## Confirmed integration seams

### 1. Command-line parsing can accept `--automation-stdio` without disturbing normal launch

`main.cpp` already has a narrow command-line seam:

- `parse_args(...)` loops over argv.
- `handle_flag(...)` handles known flags and errors on unknown flags.
- normal GUI launch continues after `QApplication`, `MainWindow`, panel allocation,
  and `a.exec()`.

Adding a boolean out-param or runtime-config bit for `--automation-stdio` is low
risk if it is only consumed after `QApplication` and `MainWindow` are created.
The automation server should not bypass normal initialization, because the safe
mutation paths depend on:

- `amber::Global`
- `amber::MainWindow`
- global panel instances
- `amber::app_ctx`
- `amber::project_model`
- `amber::UndoStack`

The launch flag should also be included in `print_help(...)`. It should not make
Amber headless unless a separate, explicitly designed headless mode is added later.
The proposed MCP stdio mode can still run with the GUI event loop active.

### 2. `AppContext` is the existing UI/engine seam, but it is not a thread-safety layer

`AppContext` already decouples several engine operations from concrete panels. The
important confirmed methods are:

- `listAllSequences()`
- `processFileList(QStringList&, bool, MediaPtr, Media*)`
- `refreshViewer()`
- `refreshTimeline()`
- `refreshEffectControls()`
- `updateUi(bool)`
- dialog/messagebox methods

`AppContextImpl` simply forwards these calls to UI panels and dialogs. That means
it is a useful semantic seam, but not safe to call from the automation stdio thread.
Every `amber::app_ctx` call should be made on the GUI thread.

### 3. `ComboAction` + `amber::UndoStack` is the central mutation contract

The undo system is mature enough for an MVP automation layer:

- `amber::UndoStack` is a global `QUndoStack`.
- `ComboAction` groups multiple `QUndoCommand`s and owns appended commands.
- `AmberAction::redo()` and `undo()` coordinate modified-state changes through
  `amber::app_ctx`.
- Timeline operations consistently create `ComboAction`, append commands, push
  to `amber::UndoStack`, and call `update_ui(...)`.

Automation mutations should follow the same structure:

1. create a `ComboAction` on the GUI thread,
2. append existing command objects or call helper methods that append them,
3. push with `amber::UndoStack.push(...)`,
4. call the same UI refresh method the UI path calls.

### 4. `Clip::move(...)` is the safe movement primitive; direct clip setters are not

`Clip::move(ComboAction*, ...)` appends `MoveClipAction` and also accounts for
shared transition relationships. This is the correct primitive for automated trim,
move, slip-like, and ripple helpers where the command knows the final clip points.

The individual setters (`set_timeline_in`, `set_timeline_out`, `set_clip_in`,
`set_track`, etc.) are not safe public automation primitives by themselves. They
are used inside undo command redo/undo implementations and setup code for new
uncommitted clip objects. Calling them directly on an existing project object would
bypass undo, modified state, transition repair, and UI refresh.

### 5. Timeline helpers provide the best MVP editing surface

The following timeline functions already encode complicated edit semantics into
undoable commands:

- `Timeline::split_clip(...)`
- `Timeline::split_clip_and_relink(...)`
- `Timeline::split_clip_at_positions(...)`
- `Timeline::split_all_clips_at_point(...)`
- `Timeline::delete_areas_and_relink(...)`
- `Timeline::delete_selection(...)`
- `Timeline::delete_in_out_internal(...)`
- `Timeline::edit_to_point_internal(...)`
- `Timeline::three_point_edit(...)`
- free `ripple_clips(...)`

Some helpers are currently UI-oriented and depend on selections, playhead, panel
state, or footage viewer state. They are still valuable seams, but automation should
wrap the underlying helper with deterministic explicit inputs where possible, rather
than simulate keyboard focus, cursor state, or hover state.

### 6. Existing import and sequence creation paths are usable but UI-coupled

Confirmed seams:

- `Project::process_file_list(...)`
- `AppContext::processFileList(...)`
- `Project::create_sequence_internal(ComboAction*, SequencePtr, bool, Media*)`
- `AddMediaCommand`
- `ChangeSequenceAction`
- `Project::list_all_project_sequences()`
- `AppContext::listAllSequences()`

Import can be exposed cautiously for local file paths, but the current path may
show modal dialogs for `.ove` imports and depends on `PreviewGenerator::AnalyzeMedia`.
For automation, file import should initially reject `.ove` project files or require
an explicit `merge_project` command, because `Project::process_file_list(...)`
currently asks a GUI question before merging.

### 7. Effects have undoable add/delete/reorder/data/keyframe paths

Confirmed safe command objects:

- `AddEffectCommand`
- `EffectDeleteCommand`
- `MoveEffectCommand`
- `SetEffectData`
- `SetEffectEnabled`
- `SetIsKeyframing`
- `KeyframeAdd`
- `KeyframeDelete`
- `KeyframeDataChange`

The MVP can safely add an effect by resolving `EffectMeta`, constructing an
`EffectPtr` through `Effect::Create(...)` only on the GUI thread, appending
`AddEffectCommand`, and refreshing effect controls/viewer.

Parameter updates are more subtle. Direct `EffectField::SetValueAt(...)` changes
data immediately and only emits `Changed()`. The undoable pattern for drag/gizmo
changes is `KeyframeDataChange` capturing old and new state. For non-keyframed
field changes, existing UI code often uses generic `SetQVariant` or related
commands through field widgets. Automation should add small GUI-thread command
wrappers around field changes rather than writing `persistent_data_` or `keyframes`
directly.

## Red flags and integration hazards

### 1. Qt object affinity is the largest risk

The repo already has comments documenting cross-thread Qt hazards:

- `ExportThread::run()` explicitly avoids `pausePlayback` and `seekPlayhead`
  because calling UI methods from the export thread can repaint widgets on the
  wrong thread.
- `ExportDialog::export_thread_finished()` restores `set_rendering_state(false)`
  on the main thread because starting a `QTimer` from `ExportThread` would fail.
- `LoadThread` uses queued signals for success/error/question handling.

Automation must therefore never call project, panel, widget, `QAbstractItemModel`,
`QUndoStack`, or dialog APIs directly from the stdio thread.

### 2. Global mutable project state has no general lock

Important globals include:

- `amber::ActiveSequence`
- `amber::project_model`
- `amber::UndoStack`
- global panel pointers
- `amber::app_ctx`

These are assumed to be accessed from the GUI thread except specialized render,
load, cache, export, and audio paths. There is no repository-wide project mutex
that would make arbitrary cross-thread automation safe.

### 3. Read-only inspection is not automatically safe

Even inspection commands such as `list_sequences`, `list_clips`, or
`get_effects` must marshal to the GUI thread. Reads traverse `QAbstractItemModel`,
`Sequence::clips`, `Clip::effects`, and active viewer/timeline state. These can
change during user operations, undo/redo, import, playback, export setup, or project
load.

### 4. `Sequence` and `Clip` expose raw mutable fields

`Sequence` exposes `clips`, `selections`, `playhead`, markers, guides, and format
fields publicly. `Clip` exposes effect lists, links, transitions, cache locks, and
QRhi texture pointers. This makes it easy for automation code to compile unsafe
direct edits. The automation implementation should establish a strict internal
policy:

- project state DTO serialization may read these fields only on GUI thread,
- command handlers may mutate only via existing commands/helpers,
- no automation tool may expose raw pointers, vector indices without validation,
  or QRhi/Cacher internals.

### 5. Renderer/export ownership is thread-sensitive

Rendering uses `RenderThread`, `Cacher`, and QRhi resources:

- `RenderThread::paint()` owns QRhi frame rendering and CPU readback.
- `Clip::Retrieve(...)` creates and uses QRhi resources during render.
- `Clip::Close(bool)` queues QRhi deletion via `RenderThread::DeferRhiResourceDeletion(...)`.
- `ExportThread` owns a nested `RenderThread` for export, emits progress, and
  supports interruption.

Automation should not touch `RenderThread`, `Cacher`, or clip QRhi fields. Preview
or export automation should call a higher-level GUI-thread service that starts an
async job and reports status by `task_id`.

### 6. Export currently mutates `seq_->playhead` from the export thread

`ExportThread::EncodeAllFrames(...)` loops while `seq_->playhead <= end_frame` and
increments `seq_->playhead++` inside the export thread. Existing UI setup/teardown
in `ExportDialog` pauses playback, seeks to the export start frame, disables UI,
and restores the playhead on the GUI thread after completion.

For automation, export must preserve that discipline:

- start export from GUI thread,
- mark rendering state on GUI thread,
- prevent concurrent edit commands while exporting,
- report status asynchronously,
- restore playhead/state on GUI thread,
- expose cancellation by task id.

Do not expose a synchronous `export` JSON-RPC method that blocks stdio until
completion.

### 7. Some existing helpers perform immediate side effects before push

Several helpers prepare objects by direct setter calls before appending
`AddClipCommand`, and `AddMediaCommand` calls `doRedo()` in its constructor. This
is acceptable inside current GUI-thread command construction patterns, but it means
automation command handlers must be careful:

- construct and push command graphs entirely on the GUI thread,
- validate inputs before any command object with constructor side effects is
  created,
- delete unused `ComboAction`s if no changes are appended,
- do not build command graphs on the stdio thread and then pass raw object pointers
  across threads.

### 8. Modal dialogs conflict with deterministic automation

Some existing operations can show message boxes or file dialogs:

- `AmberGlobal::OpenProject()`, `save_project_as()`, `can_close_project()`
- `Project::process_file_list(...)` for `.ove` imports
- `EffectRow::SetKeyframingEnabled(false)` confirmation
- effect save/load file dialogs
- export dialog startup path

Automation tools should use explicit non-interactive variants and return structured
errors for cases that require user confirmation. A stdio automation mode should not
hang waiting for modal UI unless the MCP command explicitly requested an interactive
operation.

## Recommended GUI-thread dispatch pattern

### Transport shape

Use a dedicated `QObject`/`QThread` pair for automation stdio:

- The worker thread owns blocking stdin reads and stdout writes.
- It parses framed JSON-RPC/MCP messages into immutable request DTOs.
- It never dereferences Amber project/UI objects.
- It emits a signal to a GUI-thread automation controller for each request.
- Responses are posted back to the worker thread for serialization and writing.

### Dispatch semantics

Recommended split:

- **Inspection commands:** queued to GUI thread, execute quickly, copy results into
  plain JSON DTOs, return asynchronously.
- **Short mutation commands:** queued to GUI thread, validate all IDs/indices,
  create/push undo command(s), refresh UI, return result DTO.
- **Long tasks:** queued to GUI thread only for task creation/start; return
  `{ "task_id": ... }`; progress, completion, cancellation, and logs are available
  through separate JSON-RPC methods or notifications.

For short synchronous request/response behavior, avoid blocking the GUI thread on
the stdio thread and avoid blocking the stdio thread while holding any project
lock. If a request must wait for a GUI-thread result, the wait should be outside
any Qt object access and should include cancellation/shutdown handling.

### Controller shape

A safe design is:

```text
AutomationStdioWorker (automation QThread)
  - read frames from stdin
  - parse JSON
  - emit requestReceived(RequestEnvelope)
  - write ResponseEnvelope objects to stdout

AutomationController (GUI thread QObject)
  - receives RequestEnvelope via queued connection
  - validates method and parameters
  - executes inspection/mutation using existing GUI-thread APIs
  - emits responseReady(ResponseEnvelope)

AutomationTaskRegistry (GUI thread QObject)
  - owns task IDs and task state
  - starts export/render/proxy-like long operations
  - receives progress/finished signals
  - supports cancellation
```

Important implementation constraints:

- `AutomationController` should be constructed after `MainWindow` initializes
  panels and `amber::app_ctx`.
- All methods that inspect or mutate Amber state should assert GUI-thread affinity.
- The worker should never call `QMetaObject::invokeMethod` directly on arbitrary
  panels; only the controller should know application internals.
- Do not expose raw `Clip*`, `Media*`, `Effect*`, or `Sequence*` addresses as
  external IDs. Use stable per-session automation IDs resolved on GUI thread.
- Re-resolve IDs for every command and fail cleanly if the object disappeared.

## Safe MVP tool candidates

These are realistic first tools because they can be implemented as GUI-thread
wrappers around confirmed seams and can return deterministic JSON.

### Project and sequence inspection

- `get_project_state`
  - filename, modified flag, active sequence ID/name, sequence list.
  - Use `amber::Global`, `ProjectIO`, `AppContext::listAllSequences()`.
- `list_sequences`
  - Traverse `Project::list_all_project_sequences()` through `AppContext`.
- `list_clips`
  - For a specified sequence, read `Sequence::clips` and serialize clip ranges,
    tracks, media names, enabled state, speed, links, transitions summary.
- `get_timeline_state`
  - Active sequence playhead, work area, selections, track limits, end frame.
- `list_effects`
  - For a clip, serialize `Clip::effects`, `Effect::meta`, enabled/expanded state,
    rows and fields.

All of these must marshal to the GUI thread.

### Project operations

- `open_project(path)`
  - GUI-thread wrapper around `OpenProjectWorker(path, false)` with automation
    rules for unsaved-current-project handling. MVP should require current project
    to be clean or an explicit `discard_unsaved: true`.
- `save_project`
  - Use `AmberGlobal::save_project()` only if `ActiveProjectFilename` is set.
    MVP should provide `save_project_as(path)` as an explicit non-dialog operation
    that calls `update_project_filename(path)` and `panel_project->save_project(false)`
    on GUI thread.
- `import_media(paths)`
  - Use `AppContext::processFileList(...)` / `Project::process_file_list(...)`
    on GUI thread.
  - MVP should reject directories or `.ove` files unless explicitly supported,
    because recursion and project merge can involve additional behavior.

### Timeline mutations

- `split_clip(sequence_id, clip_id, frame, relink = true)`
  - Use `Timeline::split_clip_and_relink(...)` or `split_clip(...)` inside a
    `ComboAction`, push only if a split occurred.
- `split_all_at_frame(sequence_id, frame)`
  - Use `Timeline::split_all_clips_at_point(...)`.
- `delete_range(sequence_id, track, in, out, ripple = false)`
  - Build `Selection`, call `Timeline::delete_areas_and_relink(...)`, optionally
    `ripple_clips(...)`, push `ComboAction`.
- `set_work_area(sequence_id, enabled, in, out)`
  - Use `SetTimelineInOutCommand`.
- `move_clip(sequence_id, clip_id, timeline_in, timeline_out, clip_in, track)`
  - Use `Clip::move(...)` inside `ComboAction`.
- `toggle_clip_enabled` / `set_clip_enabled`
  - Use `SetClipProperty(kSetClipPropertyEnabled)`.
- `set_clip_speed`
  - Use `SetSpeedAction`.

These are safe only if the handler validates sequence/clip identity and all frame
ranges before creating commands.

### Effect mutations

- `add_effect(clip_id, effect_name_or_id, insert_pos)`
  - Resolve `EffectMeta`, create `EffectPtr` with `Effect::Create(...)`, append
    `AddEffectCommand`.
- `delete_effect(effect_id)`
  - Use `EffectDeleteCommand`.
- `move_effect(effect_id, direction_or_index)`
  - Use `MoveEffectCommand`.
- `set_effect_enabled(effect_id, enabled)`
  - Use `SetEffectEnabled`.
- `set_effect_data(effect_id, serialized_xml)`
  - Use `SetEffectData`, but validate that settings match the effect.

Parameter/keyframe editing should be MVP only if implemented with a dedicated
undoable command pattern equivalent to `KeyframeDataChange` or existing widget
commands.

### Undo/redo

- `undo`
  - Use `AmberGlobal::undo()` on GUI thread.
- `redo`
  - Use `AmberGlobal::redo()` on GUI thread.
- `get_undo_state`
  - Read `amber::UndoStack.canUndo()`, `canRedo()`, `undoText()`, `redoText()`
    on GUI thread.

## Deferred tools

Defer these until an automation service layer exists and has integration tests:

- full export command with arbitrary codec settings,
- preview frame render / thumbnail render,
- proxy generation management,
- project merge/import of `.ove`,
- nested sequence edits,
- operations that depend on current hover/focus/cursor state,
- keyframe graph editing beyond simple explicit field value changes,
- transition editing beyond using existing add/delete/modify commands,
- direct manipulation of guides/gizmos while playback/rendering may be active,
- any operation that requires modal confirmation.

## Long-running tasks and `task_id`

Export/render/proxy operations should be asynchronous:

- `start_export(params) -> { task_id }`
- `get_task(task_id) -> { state, progress, eta, error }`
- `cancel_task(task_id) -> { accepted }`
- optional JSON-RPC notifications for progress/completion.

The export path should mirror `ExportDialog::launch_export_thread(...)`:

1. validate params on GUI thread,
2. pause playback on GUI thread,
3. set rendering state on GUI thread,
4. seek/start state on GUI thread,
5. create `ExportThread`,
6. connect progress/finished/cancel signals,
7. start thread,
8. restore rendering state and playhead in a GUI-thread finished handler.

Do not call `ExportThread` methods that touch state from the stdio worker, except
through queued task-registry methods.

## Implementation phases from the full plan

The full context's phased plan is the right sequencing. Repo inspection adds the
following integration notes and gates for each phase.

### Phase 0: prepare branch and avoid render internals

Confirmed. This work should remain on `2.0.lawmight` / derivative feature branches
and avoid broad render, cache, and QRhi refactors. The branch already contains
threading-sensitive RHI/export fixes, so speculative cleanup in these areas would
raise review risk without helping the automation skeleton.

Phase 0 gate:

- no behavior changes outside explicitly requested automation scaffolding,
- normal launch remains unchanged,
- no direct changes to `RenderThread`, `ExportThread`, `Cacher`, or clip QRhi fields
  unless a later preview/export phase specifically requires a service wrapper.

### Phase 1: read-only automation

This should be the first implementation PR. It should add:

- `--automation-stdio` flag,
- JSON-RPC/MCP initialize path,
- `tools/list`,
- `tools/call`,
- at least four read-only tools from the plan:
  - `inspect_project`,
  - `list_media`,
  - `list_sequences`,
  - `inspect_timeline` or `get_active_sequence`.

Repo-grounded constraints:

- Even read-only tools must execute serialization on the GUI thread.
- Serialization should return value DTOs only; no pointers or mutable references.
- Normal launch without the flag must be byte-for-byte behaviorally equivalent from a
  user perspective.
- Avoid loading/saving project files or touching undo in Phase 1.

### Phase 2: safe mutations

Phase 2 should add only a small mutation set after Phase 1 proves dispatch and IDs:

- `undo`,
- `redo`,
- `save_project` or explicit `save_project_as`,
- `import_media` with guarded local file paths,
- `create_sequence`,
- one or two timeline mutations such as `add_clip`, `split_clip`, or
  `ripple_delete`.

Repo-grounded constraints:

- Every mutation must run on GUI thread.
- Every project mutation must push `ComboAction` / `AmberAction` commands to
  `amber::UndoStack` or call an existing UI/app operation with equivalent undo
  behavior.
- Validate all IDs and frame ranges before constructing commands with side effects.
- Do not hand-write `.ove` XML; use project save/import paths.
- Reject operations that would open modal confirmation dialogs unless the tool has an
  explicit non-interactive policy.

### Phase 3: preview frame rendering

`render_preview_frame` should remain deferred until command dispatch and mutation
undo are proven. It should not expose `RenderThread` internals directly. A safe
preview phase needs a GUI-thread task facade that:

- pauses or snapshots the relevant viewer/render state deliberately,
- starts rendering through existing render surfaces or a narrowly designed preview
  service,
- returns a file path plus frame/timecode metadata,
- cleans up through existing QRhi ownership paths.

Because `Clip::Retrieve(...)` and QRhi resource lifetimes are tightly tied to
`RenderThread::paint()`, preview work should be reviewed as a rendering integration,
not a generic automation command.

### Phase 4: external Cursor SDK runner

This should remain outside Amber. Amber should know about MCP/JSON-RPC tool calls,
not Cursor SDK internals. The external runner can orchestrate:

- perception sidecars,
- planning,
- tool calls,
- preview critique,
- undo/redo iteration,
- final export.

Amber's responsibility is deterministic, local, undo-preserving tool execution.

### Phase 5: compound tools and interchange

Compound tools from the full context should be implemented after primitives are
stable:

- `create_rough_cut_from_transcript`,
- `make_short_variant`,
- `remove_silence`,
- `add_caption_style`,
- `apply_reference_style`,
- `generate_preview_pack`,
- OTIO import/export,
- sidecar Python helpers,
- preview segments,
- branch/snapshot support.

These should mostly live in the external agent or a thin composition layer. Amber
should expose primitives and, selectively, local deterministic compound operations
where undo grouping is clear.

## Acceptance realism

### First Cursor-agent implementation acceptance criteria

The full context's acceptance criteria are realistic if scoped to Phase 1 plus a
small Phase 2 slice. The first implementation should be accepted only if it proves:

- Amber compiles on `2.0.lawmight`.
- Normal launch is unchanged when `--automation-stdio` is absent.
- Automation is behind the explicit `--automation-stdio` flag.
- MCP/JSON-RPC plumbing supports initialize, `tools/list`, and `tools/call`.
- At least four read-only tools work end-to-end.
- At least two mutation tools work end-to-end.
- Every mutation preserves undo/redo through `amber::UndoStack`.
- No mutation directly writes existing `Clip` fields or `Sequence::clips`.
- No automation code touches `Cacher`, `RenderThread` internals, or QRhi texture
  ownership.
- A short README or developer note explains launch, protocol framing, tools, and
  safety rules.
- A smoke test/script calls `inspect_project` and one mutation, then verifies undo.

Repo inspection adds two extra acceptance checks:

- Read-only inspection must also prove GUI-thread dispatch.
- Mutations should fail with structured JSON-RPC errors when project state is
  missing or IDs are stale, rather than crashing or opening modal UI.

### Realistic for MVP

An MVP is realistic if it is scoped to deterministic project inspection first, then
undoable timeline/effect mutations that already have command objects. The highest
confidence read-only tools are:

- inspect project/sequences/clips/effects,
- list media,
- active sequence and timeline state,
- effect/field/keyframe summaries.

The highest confidence mutation tools after read-only plumbing are:

- save/open with explicit non-interactive policy,
- import media with guarded file types,
- create sequence,
- add clip using existing media and undo commands,
- split/move/delete/ripple ranges,
- set work area,
- add/delete/reorder/enable effects,
- undo/redo.

These operations match existing code structure and can preserve user-visible undo
behavior.

### Risky but possible with a service layer

These are possible but need more design:

- export automation,
- preview frame automation,
- keyframe editing,
- transition editing,
- nested sequence workflows,
- three-point edits with explicit source/destination inputs rather than footage
  viewer state.

They are not impossible, but each needs a GUI-thread service wrapper with clear
state ownership and no modal UI dependency.

### Not acceptable for first implementation

The following should be rejected in code review:

- direct mutation from the automation thread,
- direct `Sequence::clips` modifications on existing sequences,
- direct `Clip` setter calls on existing clips outside undo commands,
- direct `EffectField` keyframe/vector edits outside undo commands,
- direct access to `Cacher`, `RenderThread` internals, `QRhiTexture*`, or
  `Clip::fbo_rhi`,
- synchronous JSON-RPC export calls that block until completion,
- automation commands that rely on current mouse hover, focus, or modal dialogs.

## Notes for future agents

The full context's future-agent guidance should be treated as code-review policy:

- Do not solve everything in one PR.
- The first PR should be a narrow automation skeleton with one or two safe tools.
- Avoid speculative refactors.
- Preserve Amber's lightweight, thread-sensitive architecture.
- Prefer small adapters over rewrites.
- Keep the Cursor SDK external.
- Do not require Amber to understand Cursor internals.
- Read the Nia reports before coding if they are available locally:
  - `oracle_automation_api_architecture.md`,
  - `oracle_agentic_video_editor_loop.md`,
  - `oracle_amber_code_integration_map.md`,
  - `tracer_existing_video_editor_automation_projects.md`,
  - `tracer_capcut_jianying_draft_api_mcp_projects.md`,
  - `tracer_open_source_nle_architectures.md`,
  - `summary_for_tom.txt`.

If those files are not available in a future agent environment, use the summarized
prior art in this report and the pasted agent context as the fallback source of
truth.

## Recommended test plan

### Unit and integration tests

Add tests under `src/tests/` once automation code exists:

- parser/framing tests for stdio JSON-RPC messages,
- method validation tests with malformed parameters and unknown IDs,
- GUI-thread dispatch tests using a fake controller target,
- undo preservation tests for each mutation:
  - perform automation command,
  - assert project state changed,
  - call undo,
  - assert original state restored,
  - call redo,
  - assert changed state restored,
- inspection snapshot tests for stable JSON output from a small synthetic project,
- effect command tests for add/delete/enable/reorder,
- task registry tests for progress, completion, cancellation, and stale task IDs.

Current test wiring supports headless Qt Test executables linked against
`amber-engine` with UI stubs. Automation that depends on real panels will need either
an application-level integration test target or a testable controller abstraction
whose command-building logic can run with stubs.

### Runtime/manual verification

For the real app:

1. Launch normal Amber without `--automation-stdio` and verify existing startup,
   autorecovery prompt, window display, and command-line flags are unchanged.
2. Launch with `--automation-stdio` and verify:
   - GUI still initializes,
   - stdio thread starts,
   - invalid JSON returns JSON-RPC errors,
   - normal app close shuts down the automation thread cleanly.
3. Run inspection commands during idle, playback paused, and after project load.
4. Run a mutation command and verify:
   - timeline/effect UI updates,
   - modified state changes,
   - menu/UI undo performs the inverse operation,
   - automation `undo` and `redo` match UI behavior.
5. Attempt concurrent automation commands during export and verify mutation commands
   fail or queue according to the chosen policy.
6. Start an export task and verify:
   - immediate `task_id`,
   - progress updates,
   - cancellation,
   - final state restoration.

### Thread safety checks

Each automation controller method should have a test or debug assertion proving it
runs on the GUI thread. Useful checks:

- compare `QThread::currentThread()` with `QCoreApplication::instance()->thread()`,
- ensure no command handler is invoked directly from the stdio worker,
- run ThreadSanitizer or Qt debug builds where practical,
- include stress tests that issue repeated list/mutate/undo/redo commands while the
  UI event loop is active.

## Final feasibility judgment

The automation plan is compatible with Amber's current architecture if it is
implemented as a GUI-thread command facade over existing undoable operations. The
repo already contains the necessary seams for a useful MVP, especially around
timeline edits, media import, effect add/delete/reorder, and undo/redo.

The main engineering work is not the JSON-RPC framing; it is defining and enforcing
the boundary that the automation thread never owns project state. The acceptance bar
should require proof that every automation mutation:

- executes on the GUI thread,
- uses `ComboAction` / `AmberAction` / `amber::UndoStack` or an existing UI path
  with equivalent undo behavior,
- updates the same UI state as the corresponding user action,
- avoids renderer/cacher/QRhi internals,
- returns deterministic structured errors instead of opening unexpected modal UI,
- exposes long operations through asynchronous task IDs.
