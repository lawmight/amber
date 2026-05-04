# Amber 2.0.lawmight Automation Threading and Integration Safety Assessment

This assessment was prepared for the proposed local automation layer on
`lawmight/amber` branch `2.0.lawmight`. It is intentionally a design and safety
document only; it does not implement automation feature code.

The strategic direction from the handoff is sound for this codebase: keep the
agent process outside Amber, expose deterministic editing tools from Amber over
an explicit local stdio JSON-RPC/MCP mode, and route all project mutations
through the existing GUI-thread undo system. Amber's current architecture has
usable seams for this, but it is thread-sensitive: project state, UI panels,
the active sequence, clips, effects, and undo commands are not safe to mutate
from an automation worker thread.

## Prior art and design context used

The assessment uses the prior-art research references from the handoff as
design context:

- `burningion/video-editing-mcp`: useful MCP shape, resource URIs, lazy loading,
  defensive resource polling, and timeline resource serialization patterns.
- `samuelgursky/davinci-resolve-mcp`: good evidence that a mature NLE automation
  surface should offer both granular tools and later compound tools, organized by
  resource type instead of one monolithic command.
- OpenTimelineIO: useful vocabulary for canonical timeline state and edit verbs
  such as insert, overwrite, trim, slice/split, slip, slide, ripple, roll, fill,
  and remove. Amber does not need OTIO in the first PR, but its terms are a good
  schema target.
- OpenShot `UpdateAction`: validates a transaction-style command bus with
  explicit type, key, values, old values, and transaction boundaries; Amber's
  closest native equivalent is `ComboAction` plus `QUndoCommand` subclasses.
- Kdenlive Qt/C++ sidecars, MLT, MoviePy, and CapCut/Jianying automation
  projects: support the "real editor timeline plus external orchestration"
  approach, with headless/high-level SDK ideas deferred until Amber exposes a
  reliable local tool surface.

The local Nia output files named in the handoff were not present on this
machine, so the concrete conclusions below are based on direct inspection of
this checkout plus the full prior-art summary embedded in the task prompt.

## Verified source map

The following files and symbols were inspected and are the main integration
points:

- App lifecycle and active project:
  - `src/main.cpp`: `main`, `handle_flag`, `parse_args`, startup constructs
    `QApplication` and `MainWindow`.
  - `src/global/global.h/.cpp`: `AmberGlobal`, `amber::Global`,
    `AmberGlobal::save_project`, `OpenProject`, `ImportProject`,
    `set_sequence`, `undo`, `redo`, `set_rendering_state`,
    `save_autorecovery_file`.
  - `src/global/projectio.h/.cpp`: `ProjectIO`, `amber::project_io`,
    `ProjectIO::setSequence`, `setModified`, `setRenderingState`,
    `autorecoverySaveRequested`.
- GUI/project model seams:
  - `src/core/appcontext.h`: `AppContext`, `amber::app_ctx`,
    `listAllSequences`, `processFileList`, `setModified`, `updateUi`.
  - `src/ui/appcontextimpl.h/.cpp`: `AppContextImpl`, forwarding to
    `panel_project`, `panel_timeline`, `panel_sequence_viewer`,
    `panel_effect_controls`, and `amber::Global`.
  - `src/project/projectmodel.h/.cpp`: `ProjectModel`,
    `amber::project_model`, `appendChild`, `removeChild`, `clear`.
  - `src/panels/project.h/.cpp`: `Project::process_file_list`,
    `create_sequence_internal`, `list_all_project_sequences`, `save_project`.
- Timeline and clip state:
  - `src/engine/sequence.h/.cpp`: `Sequence`, `amber::ActiveSequence`,
    public fields `clips`, `selections`, `markers`, `guides`, `playhead`,
    `workarea_*`.
  - `src/engine/clip.h/.cpp`: `Clip`, `Clip::move`, `Open`, `Cache`,
    `Retrieve`, `Close`, `NeedsCpuRgba`, `NeedsCacherReconfigure`,
    `cached_rhi_tex`, YUV/RGBA `QRhiTexture*` fields, private `Cacher`.
  - `src/panels/timeline.h/.cpp`: `Timeline`, `ripple_clips`,
    `delete_selection`, `ripple_delete`, `delete_in_out_internal`,
    `edit_to_point_internal`, `three_point_edit`.
  - `src/panels/timeline_splitting.cpp`: `Timeline::split_clip`,
    `split_clip_and_relink`, `split_all_clips_at_point`, `split_at_playhead`.
  - `src/ui/timelinewidget.cpp`: object creation path for title/solid/tone
    clips and default effect construction.
- Undo and mutation:
  - `src/engine/undo/undostack.h/.cpp`: global `amber::UndoStack`.
  - `src/engine/undo/comboaction.h/.cpp`: `ComboAction`.
  - `src/engine/undo/undo_generic.cpp`: `AmberAction::redo/undo` sets modified
    state through `amber::app_ctx`.
  - `src/engine/undo/undo_clip.h/.cpp`: `MoveClipAction`, `DeleteClipAction`,
    `AddClipCommand`, `ReplaceClipMediaCommand`, `SetClipProperty`.
  - `src/engine/undo/undo_timeline.h/.cpp`: `RippleAction`,
    `ChangeSequenceAction`, `SetTimelineInOutCommand`, `SetSelectionsCommand`,
    `EditSequenceCommand`, marker actions.
  - `src/engine/undo/undo_effect.h/.cpp`: `AddEffectCommand`,
    `EffectDeleteCommand`, `MoveEffectCommand`, `SetEffectData`,
    keyframe commands, transition commands.
- Render/export/worker threads:
  - `src/engine/cacher.h/.cpp`: `Cacher : QThread`, `Open`, `Cache`,
    `Retrieve`, `Close`, internal wait conditions and FFmpeg state.
  - `src/rendering/renderthread.h/.cpp`: `RenderThread : QThread`,
    `start_render`, `paint`, `cancel`, `DeferRhiResourceDeletion`,
    QRhi creation, readback, save-frame and pixel-buffer paths.
  - `src/rendering/exportthread.h/.cpp`: `ExportThread : QThread`,
    internal `RenderThread`, `Interrupt`, `ProgressChanged`, `Export`.
  - `src/dialogs/exportdialog.cpp`: `ExportDialog::launch_export_thread`,
    `build_export_params`, GUI-thread export setup and cleanup.
  - `src/project/loadthread.h/.cpp`: `LoadThread : QThread`, project XML load,
    moves loaded effects/transitions to `QApplication::instance()->thread()`.
  - `src/project/previewgenerator.h/.cpp`: `PreviewGenerator : QThread`,
    `AnalyzeMedia`.
  - `src/project/proxygenerator.h/.cpp`: global `amber::proxy_generator`.
- Effects:
  - `src/effects/effect.h/.cpp`: `Effect::Create`, `GetInternalMeta`,
    `get_meta_from_name`, `save_to_string`, `load_from_string`,
    `Effect::ImageFlag`.
  - `src/effects/internal/frei0reffect.cpp`: Frei0r sets `ImageFlag`.
  - `src/rendering/renderfunctions.cpp`: `compose_sequence` checks
    `Clip::NeedsCacherReconfigure()` and closes/reopens clips around CPU RGBA
    pipeline changes.

## Ownership model and threading conclusions

### GUI-thread-owned state

Automation must treat these as GUI-thread-only:

- `amber::Global` and `AmberGlobal` project lifecycle slots.
- `amber::project_model` and `ProjectModel`, a `QAbstractItemModel`.
- `panel_project`, `panel_timeline`, `panel_sequence_viewer`,
  `panel_effect_controls`, `panel_graph_editor`, and other global panel
  pointers.
- `amber::ActiveSequence` and the active `Sequence` object's public vectors
  (`clips`, `selections`, `markers`, `guides`).
- `Clip` timeline fields, effect lists, transitions, links, and open/closed
  playback state.
- `amber::UndoStack`.

Reason: these objects are used directly by widgets, `QAbstractItemModel`
notifications, and undo commands with no global project-state mutex. For
example, `ProjectModel::appendChild/removeChild` call Qt model begin/end
methods, `Timeline` methods read and mutate `amber::ActiveSequence` directly,
and `AmberAction::redo/undo` updates modified state through `amber::app_ctx`.

### Worker-thread-owned or worker-sensitive state

Automation must not directly touch:

- `Cacher` internals, frame queues, FFmpeg contexts, and retrieve wait
  conditions.
- `Clip` RHI texture/resource fields (`cached_rhi_tex`, `yuv_tex_*`,
  `rgba_tex`, render targets/descriptors, `fbo_rhi`).
- `RenderThread` QRhi resources except through `start_render`, `cancel`, and
  documented readback/save paths.
- `ExportThread` encoding state and its internal `RenderThread`.
- `LoadThread`, `PreviewGenerator`, and `ProxyGenerator` internals.

Reason: these components already have their own threading contracts. `Cacher`
documents that `Retrieve()` may block and should not be called from the GUI
thread. `RenderThread` owns QRhi creation and drains deferred QRhi deletes on
the render thread. `ExportThread::run` explicitly avoids calling UI methods
from the export thread because it can crash widget/render backends.

### Dispatch rule for automation

The safe command path is:

1. Automation stdio thread receives and parses JSON-RPC/MCP requests.
2. It validates parameters without touching project state.
3. It invokes a GUI-thread command handler with `QMetaObject::invokeMethod`.
4. Fast read-only and mutation tools run to completion on the GUI thread.
5. Mutations build existing `QUndoCommand`/`ComboAction` objects and push them
   to `amber::UndoStack`.
6. Long render/export tools create task objects and return `task_id`
   immediately; status is polled or signalled later.

Use `Qt::BlockingQueuedConnection` only for short, bounded GUI-thread work.
Never use it for render/export, media analysis, proxy generation, or commands
that may show modal UI. Read-only snapshot tools should still run on the GUI
thread so the serialized timeline is internally consistent.

## AppContext integration seam

`AppContext` is a good first automation seam because it already abstracts UI
operations and tests can stub it:

- `AppContext::listAllSequences()` maps to `AppContextImpl::listAllSequences()`,
  which calls `panel_project->list_all_project_sequences()`.
- `AppContext::processFileList(...)` maps to
  `panel_project->process_file_list(...)`.
- `AppContext::setModified` and `updateUi` are already the way undo commands
  and engine-adjacent code communicate UI/project changes.

However, `AppContextImpl` is not a thread-safe facade. It directly calls UI
panels and dialogs. Automation may use `amber::app_ctx` only from the GUI-thread
command handler. For headless or stdio mode, prompts such as
`showQuestion/showOpenFileDialog/showSaveFileDialog` need explicit nonmodal
automation alternatives; tools should accept file paths and options instead of
opening dialogs.

## Undo and mutation safety

### Required invariant

Every project mutation exposed to automation must be undoable unless it is
explicitly documented as a project lifecycle operation. The native invariant is
`ComboAction` pushed to `amber::UndoStack`, containing existing command objects.

Verified native mutation paths:

- Clip move: `Clip::move(ComboAction*, ...)` appends `MoveClipAction` and
  transition fixups.
- Add clips: `AddClipCommand`.
- Delete clips: `DeleteClipAction` through timeline selection helpers.
- Ripple: `ripple_clips(...)` appends `RippleAction`.
- Split: `Timeline::split_clip`, `split_clip_and_relink`,
  `split_all_clips_at_point`, and `split_at_playhead`.
- Effects: `AddEffectCommand`, `EffectDeleteCommand`, `MoveEffectCommand`,
  `SetEffectData`, keyframe commands.
- Workarea/selection/sequence metadata: `SetTimelineInOutCommand`,
  `SetSelectionsCommand`, `EditSequenceCommand`.
- Media import: `Project::process_file_list` creates a `ComboAction("Import
  Media")` for top-level imports and pushes it to `amber::UndoStack`.

### Unsafe mutation pattern

Automation must not directly edit:

- `Sequence::clips`, `selections`, `markers`, or `guides`.
- `Clip::set_timeline_in/out`, `set_clip_in`, `set_track`, `effects.append`,
  or transition pointers outside a native undo command.
- `ProjectModel::appendChild/removeChild` outside an existing command path,
  except during project load/import internals that already own their lifecycle.

Direct writes would bypass `AmberAction::redo/undo`, modified-state handling,
selection cleanup, effect panel refresh, clip closing, link maintenance, and
transition fixups.

## Timeline seam assessment

The timeline panel provides useful edit verbs, but many are UI-stateful. For
automation, prefer extracting or wrapping narrow command helpers that accept
explicit sequence/clip/frame/track arguments over driving `Timeline` selection
state.

Safe or nearly safe first wrappers:

- `split_clip`: use `Timeline::split_clip_and_relink` or
  `split_all_clips_at_point` from a GUI-thread handler, with explicit clip id or
  frame. It already appends undo actions and maintains links when used through
  the existing split helpers.
- `ripple_delete`: safe only when driven from explicit selection ranges via
  `Timeline::delete_selection`/`delete_areas_and_relink`, not from hover focus
  state.
- `add_clip`: safe if it builds `MediaImportData`/ghosts or directly constructs
  `ClipPtr` using the same data as `Timeline::add_clips_from_ghosts`, then
  appends `AddClipCommand`. It must not push raw clips into `Sequence::clips`.
- `create_sequence`: safe through `Project::create_sequence_internal` with a
  `ComboAction`, or an equivalent helper that appends `AddMediaCommand` and
  optionally calls `AmberGlobal::set_sequence`.

Defer or keep UI-only initially:

- Pointer/drag tools, slip/slide/roll, transition tool, snapping, and hover
  empty-space ripple. These depend on `Timeline` mouse state, current keyboard
  modifiers, scroll/zoom, cursor frame/track, `ghosts`, and selection state.
- `three_point_insert/overwrite` as an MVP automation primitive. The underlying
  `Timeline::three_point_edit` is useful, but it depends on
  `panel_footage_viewer`, source viewer in/out state, and active sequence state.
  A later automation command should accept explicit source media/ranges and
  destination frame, then reuse the same command objects.

## Render and preview safety

`RenderThread::start_render` is the right preview seam, but only with strict
task ownership:

- It accepts `Sequence*`, playback speed, optional save path, optional pixel
  buffer, divider, and scrubbing flag.
- It owns QRhi creation in `RenderThread::run/try_create_rhi`.
- `paint` calls `compose_sequence`, does QRhi readback into `cpu_frame_`, saves
  a frame if `save_fn` is set, copies pixels if `pixel_buffer` is set, and drains
  deferred QRhi deletes.
- `Clip::~Clip` and clip closing use `RenderThread::DeferRhiResourceDeletion`
  for QRhi resources instead of deleting them directly.

Safe MVP preview shape:

- `render_preview_frame(sequence_id, frame, path, width/divider?) -> {path,
  frame, width, height}`.
- Run setup and sequence/playhead mutation on GUI thread.
- Own a short-lived or pooled `RenderThread` task object outside the automation
  request parser.
- Return a task id or block only with a short timeout; avoid indefinite waits.
- Never return raw `QRhiTexture*` or frame pointers.

Hazards:

- `compose_sequence` reads active sequence/clip/effect state while rendering.
  If automation mutates the same `Sequence` concurrently, the render thread can
  observe torn state. A first implementation should serialize automation
  mutations and preview tasks, or snapshot enough state before rendering.
- `Cacher::Retrieve` may block. Preview commands must not run retrieval on the
  GUI thread.
- Adding/removing `Effect::ImageFlag` effects can trigger
  `Clip::NeedsCacherReconfigure()` in `compose_sequence`; automation should not
  add Frei0r/ImageFlag effects while a preview/export task is active.

## Export safety

`ExportThread` is asynchronous and should remain asynchronous in automation:

- `ExportDialog::launch_export_thread` performs GUI-thread setup: pauses viewer,
  sets `audio_rendering_rate`, calls `AmberGlobal::set_rendering_state(true)`,
  seeks the viewer, clears audio buffer, closes active clips, saves
  autorecovery, prepares UI, then starts `ExportThread`.
- `ExportThread::Export` constructs an internal `RenderThread`, renders frames
  into an FFmpeg frame buffer, encodes audio/video, supports `Interrupt`, and
  emits `ProgressChanged`.
- `ExportThread::run` comments explicitly state that calling UI methods from the
  export thread is unsafe.

Safe MVP export shape:

- Defer `export_sequence` as a blocking tool.
- Provide `start_export_task(params) -> task_id`, `get_task_status(task_id)`,
  and `cancel_task(task_id)` after read-only and basic mutation tools are
  stable.
- Build a non-dialog automation export setup helper on the GUI thread that
  mirrors `ExportDialog::launch_export_thread` without UI widgets.

Hazards:

- Export currently receives a raw `Sequence*`. If automation edits that
  sequence during export, the export thread and internal render thread can race
  timeline mutation. The automation server should reject mutations while export
  tasks are active, or later introduce project snapshots.
- Export setup currently manipulates viewer state and UI progress. Automation
  needs a separate task object that owns progress and cleanup without assuming an
  `ExportDialog`.

## Project load/import/save safety

Use existing project I/O flows; do not hand-write `.ove` XML from automation.

Safe:

- `save_project`: call `AmberGlobal::save_project()` for already-named projects,
  or a new explicit-path save helper that uses `Project::save_project`/project
  filename update without showing a save dialog.
- `import_media`: call `AppContext::processFileList`/`Project::process_file_list`
  on the GUI thread with explicit file paths. Avoid importing `.ove` through the
  MVP tool because current code prompts with `QMessageBox` and merges projects.
- `list_media`, `list_sequences`, and `inspect_project`: serialize
  `amber::project_model` and `AppContext::listAllSequences` on the GUI thread.

Defer:

- `open_project` and `import_project` automation. `LoadThread` mutates project
  structures and calls panel/project functions during load; it also uses queued
  question dialogs. This needs a noninteractive load policy first.

## MVP tool classification

### Safe for phase 1 read-only

These are safe if implemented as GUI-thread snapshots with no direct worker
state access:

- `inspect_project`: project filename, modified flag, active sequence id/name,
  media count, sequence count.
- `list_media`: traverse `amber::project_model` and serialize media bin items.
- `list_sequences`: via `AppContext::listAllSequences` or project model walk.
- `get_active_sequence`: read `amber::ActiveSequence`.
- `inspect_timeline`: serialize tracks, clips, in/out/source ranges, links,
  markers, workarea, playhead.
- `inspect_clip`: serialize one clip by stable id/index within a sequence.
- `inspect_effects`: serialize effect names, enabled flags, rows/fields, and
  keyframes without opening/closing effects.

Read-only tools should return stable identifiers that are explicit about their
lifetime, for example `{sequence_id, clip_index, clip_generation}` or a project
snapshot version. Do not promise pointer stability across undo/redo.

### Safe for phase 2 with existing undo paths

These are good first mutations if every implementation runs on the GUI thread
and pushes native undo commands:

- `undo` / `redo`: call `AmberGlobal::undo` / `redo` or `amber::UndoStack`
  through the GUI thread.
- `save_project`: for existing project filename; explicit path support should
  avoid dialogs.
- `import_media`: explicit paths only, no `.ove` prompt path in MVP.
- `create_sequence`: through `Project::create_sequence_internal` or equivalent
  `AddMediaCommand` flow.
- `add_clip`: explicit media id, sequence id, track, timeline in/out, source in,
  using `AddClipCommand`.
- `move_clip`: use `Clip::move(ComboAction*, ...)`.
- `split_clip`: use existing `Timeline` split helpers.
- `ripple_delete`: explicit frame/track ranges only, not hover/selection state.
- `apply_effect`: use `Effect::Create` and `AddEffectCommand`; initially allow
  only non-`ImageFlag` built-ins unless render/export is idle.
- `set_effect_param`: use `SetEffectData` or field/keyframe undo commands after
  a narrower effect-field API is identified.
- `set_keyframe`: use existing keyframe commands, but only after field identity
  serialization is stable.

### Defer until task manager/render locking exists

- `render_preview_frame`: acceptable in phase 3, but not before an automation
  task manager can own a `RenderThread`, timeouts, file paths, and mutation
  exclusion.
- `export_sequence`: do not expose as a synchronous MVP tool.
- `start_export_task`, `get_task_status`, `cancel_task`: phase 3/4 after a
  non-dialog export task wrapper exists.
- `add_text` / `add_subtitle`: defer as first mutation unless implemented by
  the same command objects as UI object creation/subtitle import. They are safe
  in principle, but touch effect creation, generated media-less clips, and UI
  creation state.
- Compound tools (`create_rough_cut_from_transcript`, `make_short_variant`,
  `remove_silence`, `add_caption_style`, `apply_reference_style`,
  `generate_preview_pack`): defer until granular tools, preview, undo/redo, and
  project snapshot/task-status support are proven.

### Avoid in MVP

- Direct `Clip`/`Cacher` control tools.
- Direct QRhi texture/frame-buffer tools.
- Background project-load/project-merge tools.
- Tools that depend on current mouse hover, keyboard modifiers, scroll/zoom, or
  active dialog state.

## Recommended first implementation boundary

The first code PR should be narrow:

1. Add explicit launch flag `--automation-stdio` in `src/main.cpp`.
2. Add `src/automation/` with a stdio JSON-RPC/MCP skeleton:
   `automationserver`, `jsonrpc`, `commands`, `serialize`, and `mcp_tools`.
3. Start automation only when the flag is present; normal launch remains
   unchanged.
4. Implement `initialize`, `tools/list`, `tools/call`.
5. Implement four read-only tools:
   - `inspect_project`
   - `list_media`
   - `list_sequences`
   - `inspect_timeline`
6. Optionally implement one or two low-risk mutations:
   - `undo`
   - `redo`
   - or `create_sequence` if undo coverage is verified.
7. Add a smoke script that launches Amber with `--automation-stdio` and calls at
   least `inspect_project`.

Do not include render preview, export, effect mutation, sidecar perception, OTIO,
or compound editing tools in the first PR.

## Invariants for future automation code

- The automation parser thread never mutates Amber project or UI state.
- All reads and writes of project state run on the GUI thread.
- All mutations use existing undo commands and `amber::UndoStack`.
- Automation does not show modal UI; tools accept explicit parameters.
- Preview/export tasks exclude concurrent timeline mutations until a snapshot
  model exists.
- Automation never exposes raw pointers, QRhi resources, AVFrame pointers, or
  Cacher queues.
- Tool schemas use deterministic ids and return enough snapshot metadata for an
  external agent to reason about stale state.
- Compound agent behavior remains external to Amber. Amber exposes tools; the
  Cursor SDK agent plans, calls tools, requests previews, critiques, and
  iterates outside the editor process.
