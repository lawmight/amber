# Amber automation architecture assessment

## Scope and conclusion

This assessment covers the feasibility of adding a local automation API to Amber on branch `2.0.lawmight`.
It does not implement feature code. The recommended architecture is feasible, but the first implementation
should be deliberately narrow: add an explicit automation launch mode, a small stdio JSON-RPC/MCP skeleton,
and a few read-only tools before any timeline mutation is exposed.

The strongest design is the one described in the handoff: keep the Cursor SDK or other agent runtime outside
Amber, and make Amber a deterministic local editor tool host. Amber should expose project and timeline tools
over stdio-framed JSON-RPC 2.0/MCP. All project reads and writes should be marshalled back onto the GUI thread.
All mutations should use the existing undo system, preferably by building `ComboAction` instances and pushing
them to `amber::UndoStack`.

## Context used

The local Nia report directory referenced in the handoff, `/opt/data/home/amber-research-results`, was not
available in this checkout. I used the report names, retrieval IDs, and summarized findings from the supplied
handoff as design context:

- `oracle_automation_api_architecture.md`, retrieve ID
  `nia oracle stream fa89cc7c-5151-4d1d-aa28-3bffea803423`
- `oracle_agentic_video_editor_loop.md`, retrieve ID
  `nia oracle stream 5c94128d-094c-4646-994f-50b32206099b`
- `oracle_amber_code_integration_map.md`, retrieve ID
  `nia oracle stream ba0e136c-09c0-438d-aa7d-c30de4a52e4f`
- `tracer_existing_video_editor_automation_projects.md`, retrieve ID
  `nia tracer stream 93b14f1d-6003-4336-ac58-9dc1eea7c6c3`
- `tracer_capcut_jianying_draft_api_mcp_projects.md`, retrieve ID
  `nia tracer stream 11bbd6af-4236-413c-bdb2-3bdc8883ae5f`
- `tracer_open_source_nle_architectures.md`, retrieve ID
  `nia tracer stream 3526f3c3-df48-4af4-9899-f320c06a7ea3`
- `summary_for_tom.txt`

Prior-art references from that context materially shape the recommendation:

- `burningion/video-editing-mcp`: useful MCP shape for video editing tools, resource-style addressing,
  lazy loading, and defensive polling.
- `samuelgursky/davinci-resolve-mcp`: evidence that agents need both granular NLE operations and later
  compound tools, organized by editor resource.
- OpenTimelineIO: useful vocabulary for timeline semantics: insert, overwrite, trim, slice, ripple, roll,
  slip, slide, remove, and fill.
- OpenShot `UpdateAction`: useful command IR precedent with `type`, `key`, `values`, `old_values`, and
  transaction boundaries.
- Kdenlive: precedent for Qt/C++ NLEs using sidecars for OTIO and AI/perception work instead of embedding
  every scripting/runtime concern in the editor.
- MLT: reference point for a mature headless/media-engine automation contract.
- MoviePy: inspiration for a future high-level SDK or DSL layered above low-level deterministic tools.
- CapCut/Jianying draft automation projects: useful for social-video workflow schemas, but less desirable
  as the primary model because draft-file mutation around closed editors is fragile.

## Verified Amber source seams

The following paths and symbols were inspected in this checkout.

| Area | Verified path and symbol | Relevance to automation |
| --- | --- | --- |
| Application entry and CLI | `src/main.cpp`: `print_help`, `handle_flag`, `parse_args`, `main` | Natural seam for adding `--automation-stdio`. Current parsing rejects unknown flags, so automation mode needs explicit parsing and help text. Normal launch behavior should remain unchanged. |
| App lifecycle | `src/global/global.h`: `AmberGlobal`, `amber::Global`, `AmberGlobal::OpenProject`, `AmberGlobal::ImportProject`, `AmberGlobal::save_project`, `AmberGlobal::undo`, `AmberGlobal::redo`, `AmberGlobal::set_sequence` | Good high-level entry point for project lifecycle, undo/redo, save, and active sequence changes. Many slots are UI-oriented, so automation should avoid dialog-only paths for noninteractive tools. |
| UI abstraction | `src/core/appcontext.h`: `AppContext`, `amber::app_ctx`, `processFileList`, `listAllSequences`, `refreshTimeline`, `refreshViewer`, `setModified` | Existing decoupling seam that tests can stub. `processFileList(QStringList&, bool, MediaPtr, Media*)` is a useful import seam if exposed through a noninteractive adapter. |
| Active sequence | `src/engine/sequence_fwd.h`: `amber::ActiveSequence` | Global active timeline pointer used throughout UI and engine code. Automation read snapshots should not assume it is always non-null. |
| Timeline model | `src/engine/sequence.h`: `Sequence`, `Sequence::clips`, `Sequence::markers`, `Sequence::guides`, `Sequence::playhead`, `Sequence::getEndFrame`, `Sequence::getTrackLimits`, `Sequence::RefreshClips` | Main serialization target for `inspect_timeline` and related read-only tools. `Sequence` is not a `QObject`, so thread affinity is implicit through owning UI usage. |
| Clip model | `src/engine/clip.h`: `Clip`, `Clip::move`, `Clip::media`, `Clip::effects`, `Clip::linked`, `Clip::NeedsCpuRgba`, `Clip::NeedsCacherReconfigure`, `Clip::Retrieve`, QRhi texture fields | Serialization target and mutation target. Automation must not mutate fields directly from a worker thread and must not manage cacher/QRhi resources directly. `Clip::move(ComboAction*, ...)` is the safer movement seam. |
| Timeline verbs | `src/panels/timeline.h`: `Timeline::split_clip`, `Timeline::split_all_clips_at_point`, `Timeline::delete_areas_and_relink`, `Timeline::create_ghosts_from_media`, `Timeline::add_clips_from_ghosts`, `Timeline::three_point_insert`, `Timeline::three_point_overwrite`, `Timeline::ripple_delete`, free `ripple_clips` | Useful existing editor operations. Some are panel/UI methods and likely assume `panel_timeline`, selections, active sequence, and repaint paths. They should be wrapped carefully rather than called blindly from automation. |
| Global panels | `src/panels/panels.h`: `panel_project`, `panel_timeline`, `update_ui` | Practical bridge to existing UI behavior, but also a risk because panel globals couple automation to GUI state. Prefer narrow adapters that can later move into engine-level helpers. |
| Project model | `src/project/projectmodel.h`: `ProjectModel`, `amber::project_model`, `appendChild`, `child`, `childCount`, `get_root` | Main media-bin serialization source. Tree traversal is straightforward for read-only `list_media` and `inspect_project`. |
| Media objects | `src/project/media.h`: `Media`, `MediaType`, `to_footage`, `to_sequence`, `get_type`, `get_name`, `childCount`, `child` | Read-only media and sequence inspection should serialize through this tree rather than inventing a separate project registry. |
| Project panel import/sequence creation | `src/panels/project.cpp`: `Project::create_sequence_internal`, `Project::process_file_list` | `create_sequence_internal(ComboAction*, SequencePtr, bool, Media*)` already supports undo-backed sequence creation when passed a `ComboAction`. `process_file_list` builds footage items and finalizes import through undo for normal media files. It still contains UI prompts for `.ove` project imports. |
| Undo stack | `src/engine/undo/undostack.h`, `.cpp`: `amber::UndoStack` | All mutations should flow through this global `QUndoStack`. Automation commands should create undoable actions, not directly edit project state. |
| Undo grouping | `src/engine/undo/comboaction.h`: `ComboAction::append`, `appendPost`, `hasActions`, `redo`, `undo` | Correct transaction unit for one automation tool call. A tool call should map to one user-visible undo step when it mutates state. |
| Clip undo commands | `src/engine/undo/undo_clip.h`: `MoveClipAction`, `DeleteClipAction`, `AddClipCommand`, `SetClipProperty`, `SetSpeedAction`, `RenameClipCommand`, `RefreshClips` | Existing primitive actions for clip-level automation tools. |
| Timeline undo commands | `src/engine/undo/undo_timeline.h`: `RippleAction`, `ChangeSequenceAction`, `SetTimelineInOutCommand`, `SetSelectionsCommand`, `EditSequenceCommand`, marker commands | Existing primitive actions for sequence activation, timeline in/out, selections, sequence settings, markers, and ripple operations. |
| Media undo commands | `src/engine/undo/undo_media.h`: `AddMediaCommand`, `DeleteMediaCommand`, `ReplaceMediaCommand`, `MediaMove`, `MediaRename`, `UpdateFootageTooltip` | Existing primitive actions for media-bin tools. |
| Effects metadata and construction | `src/effects/effect.h`: `EffectMeta`, global `effects`, `get_meta_from_name`, `Effect::Create`, `Effect::save_to_string`, `Effect::load_from_string`, `Effect::VideoEffectFlags` | Good seam for `inspect_effects`, `apply_effect`, and preset-like parameter serialization. Image effects are a risk because they may trigger CPU RGBA/cacher reconfiguration. |
| Effect undo | `src/engine/undo/undo_effect.cpp`: `AddEffectCommand`, `EffectDeleteCommand`, `SetEffectData`, `ReloadEffectsCommand` | `SetEffectData` can support parameter/preset updates by serializing effect state, but command schemas must validate fields and surface errors instead of accepting arbitrary XML blindly. |
| Preview rendering | `src/rendering/renderthread.h`: `RenderThread::start_render`, `get_frame_data`, `get_frame_width`, `get_frame_height`, `frame_save_failed`, `cancel`, `wait_until_paused`, `setGlFallbackSurface` | Plausible backing for `render_preview_frame`. RHI ownership and fallback surfaces make this a later phase, not first PR work. |
| Export | `src/rendering/exportthread.h`: `ExportThread`, `ExportParams`, `VideoCodecParams`, `ProgressChanged`, `Interrupt`, `GetError`, `WasInterrupted` | Plausible async export backing. Should be exposed only after task tracking and cancellation semantics exist. |
| Build integration | `src/CMakeLists.txt`: `amber-engine` object library, `UI_SOURCES`, `add_executable(${AMBER_TARGET} ...)`, tests via `add_subdirectory(tests)` | An automation module can either be added to `UI_SOURCES` initially or split as a small library. Tests already exist under `src/tests/`. |

## Feasibility assessment

Adding a local automation API is technically feasible because Amber already has:

1. A central Qt application entry point where automation mode can be gated behind a flag.
2. A global application/lifecycle object for project operations.
3. A project tree and active sequence pointer that can be serialized without changing the file format.
4. A mature undo command model with `ComboAction` and many existing primitive actions.
5. Existing timeline panel verbs for common NLE operations.
6. Existing render/export worker objects that can eventually support preview and export tools.

The main feasibility constraint is not data access; it is thread safety and UI coupling. `Sequence` and `Clip`
are plain C++ objects with extensive use from UI code, global panels, render threads, cacher threads, and the
undo stack. A stdio server thread must not directly read or mutate those objects while the GUI and render
threads are active. Even read-only inspection should run on the GUI thread and return an immutable JSON
snapshot to the automation thread.

The second constraint is noninteractive behavior. Some useful methods are dialog-backed or panel-backed.
For example, `AmberGlobal::OpenProject()` and `Project::process_file_list()` contain user-facing behavior.
The automation layer should expose noninteractive variants or thin adapters where necessary instead of
driving dialogs.

## Recommended architecture

### Process boundary

Do not embed the Cursor SDK or an LLM runtime in Amber initially. The editor should be a local deterministic
tool host; the agent should be a separate process.

Recommended runtime shape:

```text
Cursor SDK agent process
  -> launches Amber with --automation-stdio
  -> speaks stdio JSON-RPC 2.0 / MCP
Amber GUI process
  -> automation I/O thread parses requests
  -> GUI-thread command handler snapshots or mutates project state
  -> RenderThread/ExportThread remain specialized workers for preview/export
```

Stdio is the right first transport because it avoids local HTTP authentication, local-port discovery, DNS
rebinding, and remote-control exposure. HTTP JSON-RPC can be added later behind explicit opt-in if remote
control is required.

### Proposed source layout

Add a new module:

```text
src/automation/
  CMakeLists.txt
  automationserver.h/.cpp
  jsonrpc.h/.cpp
  commands.h/.cpp
  serialize.h/.cpp
  mcp_tools.h/.cpp
```

Responsibilities:

- `automationserver`: owns the stdio reader/writer and worker thread lifecycle.
- `jsonrpc`: parses and formats JSON-RPC 2.0 request/response/error objects using `QJsonDocument`.
- `mcp_tools`: implements MCP `initialize`, `tools/list`, and `tools/call`.
- `commands`: dispatches tool calls and marshals execution to the GUI thread.
- `serialize`: converts `ProjectModel`, `Media`, `Sequence`, `Clip`, `Effect`, markers, guides, and selections
  into stable JSON.

For the first PR, this can be even smaller:

```text
src/automation/
  automationserver.h/.cpp
  jsonrpc.h/.cpp
  serialize.h/.cpp
```

The first PR does not need to support all planned files if it keeps the code simple and reviewable.

### Threading contract

Every command should follow this pattern:

1. Automation I/O thread reads one request from stdin.
2. It validates JSON-RPC shape and tool parameters.
3. It invokes a GUI-thread handler using `QMetaObject::invokeMethod`.
4. Fast commands use `Qt::BlockingQueuedConnection` and return a complete JSON response.
5. Long commands create a task record and return `task_id`; progress is polled or emitted later.
6. GUI-thread mutation commands create a `ComboAction` and push it to `amber::UndoStack`.
7. The automation thread writes exactly one response for normal JSON-RPC requests.

This implies two hard rules:

- No automation thread direct writes to `Sequence::clips`, `Clip` fields, `amber::project_model`, or panel
  globals.
- No automation thread direct ownership or deletion of `Cacher`, `QRhi`, `QRhiTexture`, `QRhiResource`, or
  render/export internals.

## Tool surface recommendation

### First read-only tools

Start with a read-only set:

- `inspect_project`
  - Returns project filename, modified state, active sequence summary, media-bin tree counts, and available
    sequences.
  - Sources: `amber::ActiveProjectFilename`, `amber::Global->is_modified()`, `amber::project_model`,
    `amber::ActiveSequence`.
- `list_media`
  - Traverses `amber::project_model` using `ProjectModel::childCount`, `child`, and `Media::get_type`.
- `list_sequences`
  - Traverses the media tree and returns `Media` entries where `get_type() == MEDIA_TYPE_SEQUENCE`.
  - `AppContext::listAllSequences()` is also a useful abstraction if the UI implementation is suitable.
- `inspect_timeline`
  - Serializes `amber::ActiveSequence` or a requested sequence ID: dimensions, frame rate, audio settings,
    playhead, work area, markers, guides, and clips.

These tools are useful enough for an external agent to understand an open project without exposing risky
mutation paths.

### First mutation tools

After read-only inspection is proven, add only two or three safe mutation tools:

- `undo`
  - Calls `AmberGlobal::undo()` or `amber::UndoStack.undo()` on the GUI thread.
- `redo`
  - Calls `AmberGlobal::redo()` or `amber::UndoStack.redo()` on the GUI thread.
- `save_project`
  - Calls `AmberGlobal::save_project()` only if project filename is already set; avoid `save_project_as()`
    dialog behavior in automation. A later `save_project_as(path)` tool can set a path explicitly.

If a content mutation is required in the first feature PR, choose `create_sequence` over clip editing. It can
use `Project::create_sequence_internal(ComboAction*, SequencePtr, bool, Media*)` through a GUI-thread adapter
and produce a single undoable action via `AddMediaCommand` and optionally `ChangeSequenceAction`.

### Later mutation tools

Phase in timeline tools only after read-only snapshots and undo/redo work:

- `import_media`: use `AppContext::processFileList` or a noninteractive wrapper around
  `Project::process_file_list`; reject `.ove` imports initially to avoid UI confirmation.
- `add_clip`: use `Timeline::create_ghosts_from_media` + `Timeline::add_clips_from_ghosts`, or build
  `Clip` objects and use `AddClipCommand` after matching existing add-clip behavior.
- `move_clip`: prefer `Clip::move(ComboAction*, ...)` to direct timeline field writes.
- `split_clip`: use `Timeline::split_clip`, `split_clip_and_relink`, or `split_all_clips_at_point`.
- `ripple_delete`: use existing selection/delete flows only after a command schema can describe selections
  deterministically.
- `apply_effect`: resolve `EffectMeta` with `get_meta_from_name`, construct with `Effect::Create`, and wrap
  with `AddEffectCommand`.
- `set_effect_param` / `set_keyframe`: prefer `SetEffectData` around `Effect::save_to_string()` /
  `load_from_string()` until a safer typed field-level command exists.

### Preview and export tools

Preview/export should not be in the first PR. They require more testing across RHI backends and thread
lifetime boundaries.

Later tools:

- `render_preview_frame`
  - Backed by `RenderThread::start_render(Sequence*, ..., const QString& save, void* pixels, ...)`.
  - Return a PNG/JPEG path plus frame/timecode metadata.
  - Handle `frame_save_failed`, `did_texture_fail`, cancellation, and timeout.
- `export_sequence`
  - Backed by `ExportThread` with `ExportParams` and `VideoCodecParams`.
  - Should be async and task-based from the start.
- `start_export_task`, `get_task_status`, `cancel_task`
  - Required before long export work is exposed to agents.

## Data model and IDs

The automation API needs stable IDs that are not raw pointers:

- Project media IDs can initially be path-like tree positions such as `media:/0/3/1`.
- Active sequence can be addressed as `sequence:active`.
- Sequence media entries can have IDs derived from the media tree path plus `Media::to_sequence()`.
- Clip IDs can initially be sequence-local indexes plus a generation/snapshot token, e.g.
  `sequence:active/clip:12`.

Index-based IDs are acceptable for read-only phase and early mutation if every mutation command validates that
the referenced clip still matches expected `timeline_in`, `timeline_out`, `track`, and media identity. Later,
Amber may need durable internal IDs for clips/effects if agent sessions become long-lived.

## Risks and mitigations

### High risk: cross-thread timeline mutation

`Sequence` and `Clip` are plain objects, while UI, render, export, and cacher code all interact with them.
Direct automation-thread mutation can corrupt state or race rendering.

Mitigation: execute all reads and mutations on the GUI thread. Return JSON snapshots, not live pointers.
Mutations must be undo commands pushed to `amber::UndoStack`.

### High risk: QRhi and cacher ownership

`Clip` owns cacher state and QRhi texture fields, while `RenderThread` owns RHI resources and has deferred
resource deletion helpers. Automation must not create, reuse, or delete those resources.

Mitigation: preview tools should call existing render APIs only. Keep preview out of the first PR.

### High risk: dialog-backed functions in automation mode

Some convenient methods open dialogs or message boxes. Examples include `AmberGlobal::OpenProject()` and
`.ove` handling inside `Project::process_file_list`.

Mitigation: command handlers must be noninteractive. Add explicit path-based or adapter methods where needed.
Reject operations that would require user confirmation until a noninteractive policy exists.

### Medium risk: panel-global coupling

Useful operations live on `panel_project` and `panel_timeline`. Calling them can be pragmatic, but it couples
automation to UI selection, active tools, repaint assumptions, and widget lifetime.

Mitigation: read-only phase should mostly avoid panel globals. Mutation phase can use small GUI-thread adapters
around panel methods, with an explicit roadmap to move reusable edit logic into engine-level helpers.

### Medium risk: weak command schemas

If tool schemas are too permissive, agents will produce ambiguous edits that are hard to undo or audit.

Mitigation: use explicit, typed JSON schemas. Reject unknown fields. Require frame units and sequence IDs.
Return structured errors with valid ranges and current state hints.

### Medium risk: effect parameter serialization

`Effect::load_from_string()` and `SetEffectData` are powerful but broad. Accepting arbitrary serialized effect
XML from an agent would be fragile.

Mitigation: start with `inspect_effects` and `apply_effect` only. Add typed parameter setting later by mapping
`EffectRow` and `EffectField` metadata to JSON.

### Medium risk: unstable clip IDs

Clip index references shift after split, ripple delete, and add operations.

Mitigation: include optimistic concurrency fields in mutation params. Return updated timeline snapshots after
mutations. Add durable IDs only when required by multi-step workflows.

### Low-to-medium risk: normal launch regression

Adding automation mode to `main.cpp` can accidentally alter normal GUI startup.

Mitigation: keep automation behind `--automation-stdio`, add help text, and verify launch path remains unchanged
when the flag is absent.

## Narrow first PR shape

The first PR should be an automation skeleton, not an agentic editor.

Recommended contents:

1. Add `--automation-stdio` parsing in `src/main.cpp`.
   - Normal startup without the flag must behave exactly as it does now.
   - Help text should mention the flag.
2. Add a minimal `src/automation/` module.
   - JSON-RPC 2.0 parsing/formatting.
   - MCP `initialize`, `tools/list`, and `tools/call`.
   - A command dispatcher that marshals tool calls to the GUI thread.
3. Add read-only serializers.
   - `inspect_project`
   - `list_media`
   - `list_sequences`
   - `inspect_timeline`
4. Add at most two safe mutation tools.
   - `undo`
   - `redo`
   - Optionally `save_project` only when no dialog is required.
5. Add a short developer README.
   - How to launch: `amber-editor --automation-stdio`
   - Example JSON-RPC requests.
6. Add a smoke test or script.
   - Launches automation mode.
   - Calls `initialize`, `tools/list`, and `inspect_project`.
   - If mutation is included, tests `undo`/`redo` or a very safe project-level mutation.

Avoid in the first PR:

- Render preview.
- Export.
- Clip move/split/ripple.
- Effect mutation.
- Headless mode.
- HTTP server.
- Cursor SDK embedding.
- OTIO import/export.

## Full phased plan

### Phase 0: branch and guardrails

- Work only on `2.0.lawmight` or a feature branch from it.
- Keep automation behind explicit flags.
- Do not touch render internals unless a preview/export phase requires it.
- Add documentation that normal Amber launch is unaffected.

### Phase 1: read-only automation

- Add stdio JSON-RPC/MCP skeleton.
- Implement `initialize`, `tools/list`, `tools/call`.
- Implement `inspect_project`, `list_media`, `list_sequences`, `inspect_timeline`.
- Marshal every tool call to the GUI thread and return snapshots.
- Add smoke coverage for opening automation mode and reading an empty/new project.

### Phase 2: safe project mutations

- Add `undo`, `redo`, `save_project`.
- Add `create_sequence` through `ComboAction`, `AddMediaCommand`, and optionally `ChangeSequenceAction`.
- Add `import_media` for normal media files; reject `.ove` initially to avoid confirmation dialogs.
- Confirm every mutation creates exactly one undo step.

### Phase 3: timeline mutations

- Add `add_clip`, `move_clip`, `split_clip`, `ripple_delete`.
- Prefer existing `Timeline` and undo helpers at first.
- Stabilize command schemas around OTIO-style terminology.
- Return updated timeline snapshots after mutation commands.

### Phase 4: preview and export

- Add `render_preview_frame` using `RenderThread`.
- Add async task tracking and cancellation.
- Add `export_sequence` through `ExportThread`.
- Validate with real media across at least one GPU/RHI backend and a safe fallback path.

### Phase 5: external agent harness

- Build a Cursor SDK runner outside Amber.
- Launch/connect to Amber MCP stdio.
- Feed perception sidecar outputs to the agent.
- Start with simple deterministic workflows: import media, make a rough cut, add captions, render preview frame,
  critique, undo/adjust, and export.

### Phase 6: richer workflows and interchange

- Add compound tools such as `create_rough_cut_from_transcript`, `remove_silence`, `make_short_variant`,
  `add_caption_style`, and `generate_preview_pack`.
- Add OTIO import/export as a bridge format.
- Add sidecar integrations for Whisper, scene detection, beat detection, OCR, embeddings, and face/object
  detection.
- Add snapshot/branch semantics for agent experimentation.

## Acceptance criteria for the first implementation

A first implementation should be considered successful only if:

- Amber compiles on `2.0.lawmight`.
- Normal Amber launch behavior is unchanged when `--automation-stdio` is absent.
- Automation mode is opt-in and documented.
- At least four read-only tools return structured JSON snapshots.
- Any included mutation tools are undoable and execute on the GUI thread.
- No automation code directly mutates `Clip`/`Sequence` from a worker thread.
- No automation code directly touches `Cacher`, `QRhi`, or `QRhiTexture` ownership.
- A smoke test or script exercises `initialize`, `tools/list`, and at least one tool call.

## Final recommendation

Proceed with a narrow automation skeleton first. Amber has enough existing seams to support agent control, but
the first PR should prove transport, command dispatch, GUI-thread marshalling, serialization, and normal-launch
isolation before attempting timeline edits or preview rendering. The external agent/editor loop should be built
after Amber exposes deterministic tools; Amber should not embed Cursor SDK logic as the first step.
