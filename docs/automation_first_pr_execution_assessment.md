# Amber 2.0.lawmight automation first-PR execution assessment

## Revision note: what changed after the full context

This assessment was revised after receiving the full Amber agent context pasted in the task. The local
files referenced by that context were **not available** in this cloud environment:

- `/opt/data/home/amber-agent-context.md`
- `/opt/data/home/amber-research-results/`

The pasted context is therefore treated as the source of truth for this revision, including the summarized
Nia research outputs, prior art, phases, acceptance criteria, and notes for future agents.

If future agents have access to the local Nia report directory, they should read these files before
expanding beyond the first PR:

- `oracle_automation_api_architecture.md`
- `oracle_agentic_video_editor_loop.md`
- `oracle_amber_code_integration_map.md`
- `tracer_existing_video_editor_automation_projects.md`
- `tracer_capcut_jianying_draft_api_mcp_projects.md`
- `tracer_open_source_nle_architectures.md`
- `summary_for_tom.txt`

Material changes from the first assessment:

1. The first PR must satisfy the stated acceptance criterion of **at least four read-only tools and two
   mutation tools**. The safest two mutation tools are `undo` and `redo`.
2. `save_project` should not count as one of the required first two mutation tools unless it is guarded
   against unsaved projects. It is acceptable as an optional third tool or explicit placeholder.
3. The full proposed file layout is worth preserving in the first implementation, including
   `jsonrpc.*`, `mcp_tools.*`, and `src/automation/CMakeLists.txt`, because the context is planning for
   later external Cursor SDK orchestration and future agents need clear ownership boundaries.
4. The first PR should still **not** include `import_media`, `create_sequence`, `add_clip`, `split_clip`,
   `ripple_delete`, or `render_preview_frame`. That recommendation is unchanged, but now framed as the
   minimum way to meet acceptance criteria while avoiding the repo-specific mutation risks found below.
5. The smoke script should call `inspect_project` and `undo` (or `redo`) specifically, because that
   proves one read-only path and one mutation-class tool without requiring media, timelines, or render
   resources.

## Executive recommendation

Make the first PR a narrow automation substrate, not a broad editing-tool PR.

Recommended first-PR scope:

1. Add explicit `--automation-stdio`.
2. Preserve normal GUI launch behavior when the flag is absent.
3. Implement newline-delimited JSON-RPC 2.0 over stdio, shaped as MCP:
   - `initialize`
   - `tools/list`
   - `tools/call`
4. Expose at least four read-only tools:
   - `inspect_project`
   - `list_media`
   - `list_sequences`
   - `inspect_timeline`
5. Expose exactly two safe mutation tools for the first PR:
   - `undo`
   - `redo`
6. Optionally expose `save_project` as a guarded mutation:
   - refuse if `amber::ActiveProjectFilename` is empty;
   - otherwise call the existing save path on the GUI thread.
7. Add short README documentation.
8. Add one smoke script that starts Amber with `--automation-stdio`, calls `inspect_project`, then calls
   `undo` or `redo`.

Do not include media import, clip creation, timeline edits, preview render, export, sidecars, OTIO, or the
external Cursor SDK runner in the first PR. Those belong in later phases after the stdio contract and GUI
thread dispatch are proven.

This PR still advances the strategic architecture from the full context: Amber becomes a deterministic
local tool host, while Cursor SDK remains an external orchestrator.

## Full-plan comparison

### First-PR acceptance criteria

The full context gives these acceptance criteria:

| Criterion | First-PR plan |
| --- | --- |
| Compile on `2.0.lawmight` | Keep code isolated under `src/automation/`, use existing Qt Core JSON, and validate with local CMake build. |
| Normal launch unchanged | Gate all new behavior behind `--automation-stdio`; preserve `showMaximized()` / `showFullScreen()` path when absent. |
| Explicit automation flag | Add only `--automation-stdio`; defer `--automation-headless`. |
| At least four read-only tools | Implement `inspect_project`, `list_media`, `list_sequences`, `inspect_timeline`. |
| At least two mutation tools | Implement `undo` and `redo` only. |
| Undo/redo preserved | Route through `AmberGlobal::undo()` / `redo()` and existing `amber::UndoStack`. |
| No direct `Clip` / `Cacher` / QRhi manipulation | Serialization only reads stable accessors/fields; no render/cacher methods. |
| README | Add a short automation section to `README.md`. |
| Smoke script | Add `scripts/smoke_automation_stdio.py` calling `inspect_project` and `undo`. |

The main change after seeing the full context is that `undo` and `redo` move from optional "safe
mutation-class" tools to required first-PR scope, because they are the lowest-risk way to satisfy the
two-mutation acceptance criterion.

### Strategic architecture

The full plan says:

- do not embed Cursor SDK in Amber first;
- add local automation inside Amber;
- expose tools over stdio JSON-RPC 2.0 framed as MCP;
- keep mutations on the GUI thread;
- route mutations through `ComboAction` and `amber::UndoStack`;
- run Cursor SDK externally.

Repo inspection supports this architecture. Amber already has a Qt GUI-centric ownership model, global
project/timeline state, and worker threads for rendering/loading/caching. Embedding a model or adding an
HTTP server first would increase review surface and runtime risk without proving the core editing seam.

### MVP tool list

The full plan's MVP list is intentionally broad:

- read-only: `inspect_project`, `list_sequences`, `list_media`, `get_active_sequence`,
  `inspect_timeline`, `inspect_clip`, `inspect_effects`;
- mutations: `import_media`, `create_sequence`, `add_clip`, `move_clip`, `split_clip`,
  `ripple_delete`, `add_text`, `add_subtitle`, `apply_effect`, `set_effect_param`,
  `set_keyframe`, `undo`, `redo`, `save_project`;
- render/export: `render_preview_frame`, `export_sequence`, task APIs.

For the first PR, use only the acceptance-minimum subset:

- read-only: `inspect_project`, `list_media`, `list_sequences`, `inspect_timeline`;
- mutation: `undo`, `redo`;
- optional guarded `save_project`.

This is the smallest set that meets the first-PR acceptance criteria while avoiding the timeline, effect,
media analysis, and QRhi risks identified in the actual code.

### Proposed phases

The full plan phases are sound:

1. Phase 1: read-only automation.
2. Phase 2: safe mutations.
3. Phase 3: preview render.
4. Phase 4: external Cursor SDK runner.
5. Phase 5: compound tools, OTIO, sidecars, snapshots.

The only adjustment is tactical: because acceptance criteria require two mutation tools in the first PR,
include `undo` and `redo` with Phase 1. Treat them as "safe Phase 2 slivers" that call existing global
slots and do not introduce new editing behavior.

### Agentic editor loop

The broader plan is an external loop:

1. ingest media;
2. run perception sidecars such as `ffprobe`, Whisper, diarization, scene/shot/silence/beat detection,
   OCR, face/object detection, and CLIP/image embeddings;
3. build timeline state JSON;
4. have an external Cursor SDK agent plan edits;
5. call Amber tools;
6. render previews;
7. critique with vision/perception;
8. iterate with undo/redo/project snapshots;
9. export final media.

The first PR should only establish steps 3-5 for empty or existing projects. It should not add sidecars,
preview critique, snapshots, or export. Those need the stdio contract and task/polling model to be stable
first.

## Repository facts verified

### Build system

- Top-level CMake entry is `src/CMakeLists.txt`.
- Project is C++17 (`src/CMakeLists.txt:9-11`) with Qt automoc/autouic/autorcc enabled
  (`src/CMakeLists.txt:13-16`).
- Qt components already include `Qt6::Core`, `Qt6::Gui`, `Qt6::Widgets`, and others
  (`src/CMakeLists.txt:31-44`). `QJsonDocument`, `QJsonObject`, `QJsonArray`, `QFile`,
  `QSocketNotifier`, and `QMetaObject` are in Qt Core, so no new dependency is needed.
- Core non-UI code is collected in the `amber-engine` object library (`src/CMakeLists.txt:98-163`).
- UI/application sources are listed in `UI_SOURCES`, currently including `main.cpp`
  (`src/CMakeLists.txt:181-268`).
- Executable target is `amber-editor` except on Apple, where it is `Amber`
  (`src/CMakeLists.txt:358-363`).
- Tests are enabled only when not cross-compiling (`src/CMakeLists.txt:386-390`).
- Shader/effect and export-preset post-build copies attach to the app target
  (`src/CMakeLists.txt:404-417`).

### Test setup

- Tests live in `src/tests/` and are registered with CTest in `src/tests/CMakeLists.txt`.
- Test targets link `amber-engine` plus `Qt6::Test`; UI symbols are satisfied by
  `src/tests/test_ui_stubs.cpp` (`src/tests/CMakeLists.txt:3-8`).
- `src/tests/test_projectio.cpp` demonstrates a headless `AppContext` stub pattern
  (`src/tests/test_projectio.cpp:10-37`).
- Automation startup is app-level, so the first smoke test should be a script that runs the built
  executable, not a Qt unit test linked only to `amber-engine`.

### CI and release workflows

- `.github/workflows/build.yml` builds packages on `workflow_dispatch` and release publication.
- `.github/workflows/preview.yml` only triggers package builds on pushes to `2.0.x` with `[preview]`
  in the commit message (`.github/workflows/preview.yml:3-6`, `:16-27`).
- These workflows build AppImage/Windows/macOS packages. They do not appear to run a PR CTest workflow.
  The first automation PR needs local build, CTest, and smoke-script evidence.

### Startup parsing and normal launch

- Startup parsing is custom `argc`/`argv` handling in `src/main.cpp`, not `QCommandLineParser`.
- `handle_flag()` recognizes current options and rejects unknown flags (`src/main.cpp:88-134`).
- `parse_args()` treats the first non-flag argument as the project filename
  (`src/main.cpp:136-148`).
- `main()` currently:
  - creates `amber::Global` (`src/main.cpp:252-253`);
  - parses arguments (`src/main.cpp:259-260`);
  - installs the internal logger unless `--no-debug` is used (`src/main.cpp:265`);
  - forces `QT_AUDIO_BACKEND=pulseaudio` (`src/main.cpp:267-270`);
  - creates `QApplication` (`src/main.cpp:274`);
  - creates `MediaIconService` (`src/main.cpp:286`);
  - creates `MainWindow` (`src/main.cpp:290`);
  - connects `MainWindow::finished_first_paint` to `AmberGlobal::finished_initialize`
    (`src/main.cpp:299-300`);
  - optionally schedules project loading (`src/main.cpp:302`);
  - shows the window maximized/fullscreen (`src/main.cpp:304-308`);
  - enters `a.exec()` (`src/main.cpp:310`).
- `AmberGlobal::finished_initialize()` is where startup project loading and first-launch behavior run
  (`src/global/global.cpp:324-345`).

Automation mode must not break this default launch path. If the automation window is hidden, it must not
depend on `finished_first_paint`, because that signal will not fire without a first paint.

### Project, sequence, and timeline seams

- Project tree is `amber::project_model` (`src/project/projectmodel.h:65-67`), with `childCount()`,
  `child()`, and `getItem()` for traversal (`src/project/projectmodel.h:50-58`).
- `Media` exposes `get_type()`, `get_name()`, `to_footage()`, `to_sequence()`, `childCount()`, and
  `child()` (`src/project/media.h:45-70`).
- `Sequence` exposes serializable fields directly: `name`, `width`, `height`, `frame_rate`,
  `audio_frequency`, `audio_layout`, `playhead`, `workarea_*`, `markers`, `guides`, and `clips`
  (`src/engine/sequence.h:38-70`).
- `Clip` exposes safe read methods for timeline/media state: `media()`, `media_stream_index()`,
  `timeline_in()`, `timeline_out()`, `clip_in()`, `track()`, `enabled()`, `name()`, `speed()`,
  `linked`, and transition pointers (`src/engine/clip.h:81-122`, `:137-141`).
- `Clip` also owns `Cacher` and QRhi resources (`src/engine/clip.h:144-179`, `:196-197`).
  Automation serialization must not call cache/render methods or inspect QRhi fields.

### Undo, redo, save, import, sequence, split, and ripple seams

- Global undo stack is `amber::UndoStack`, a `QUndoStack` (`src/engine/undo/undostack.h:6-10`,
  `src/engine/undo/undostack.cpp:1-3`).
- `ComboAction` is the established grouping mechanism for multi-step mutations and owns appended
  `QUndoCommand`s (`src/engine/undo/comboaction.h:19-83`).
- `AmberGlobal::undo()` and `AmberGlobal::redo()` already route through UI refresh and avoid running
  while timeline import is active (`src/global/global.cpp:414-428`).
- `AmberGlobal::save_project()` saves to the current path or opens a Save As dialog if no filename is
  set (`src/global/global.cpp:290-297`). Automation must guard this.
- Import flow exists through `AppContext::processFileList()` (`src/core/appcontext.h:35`) and
  `AppContextImpl::processFileList()` forwarding to `Project::process_file_list()`
  (`src/ui/appcontextimpl.cpp:96-100`).
- `Project::process_file_list()` creates a `ComboAction("Import Media")`, appends media, pushes the
  action in `finalize_import()`, and starts `PreviewGenerator::AnalyzeMedia()` for imported items
  (`src/panels/project.cpp:827-887`, `:820-824`).
- `Project::process_file_list()` can prompt for `.ove` imports (`src/panels/project.cpp:856-863`).
- Sequence creation entry points exist:
  - `create_sequence_from_media()` (`src/panels/project.cpp:240-300`);
  - `Project::create_sequence_internal()` (`src/panels/project.h:62`);
  - `NewSequenceDialog` pushes `ComboAction("Create Sequence")`
    (`src/dialogs/newsequencedialog.cpp:97-113`).
- Add-clip via timeline ghost import exists:
  - `Timeline::create_ghosts_from_media()` (`src/panels/timeline.h:131`);
  - `Timeline::add_clips_from_ghosts()` (`src/panels/timeline.h:132`,
    implementation `src/panels/timeline.cpp:288-353`).
  This path can depend on `panel_sequence_viewer` for optional seek (`src/panels/timeline.cpp:347-349`).
- Split is implemented through `Timeline::split_clip()`, `Timeline::split_clip_and_relink()`, and
  related helpers (`src/panels/timeline.h:116-121`, `src/panels/timeline_splitting.cpp:74-188`).
- Ripple delete is selection-driven through `Timeline::delete_selection()` and `Timeline::ripple_delete()`
  (`src/panels/timeline.cpp:732-751`, `:1045-1055`).

These seams support later Phase 2 tools, but they are not small enough for the first PR.

### Render preview seam

- `RenderThread::start_render()` accepts a save path and has frame-save failure signaling
  (`src/rendering/renderthread.h:61-76`).
- `RenderThread` is `QThread`-based and owns QRhi/offscreen state (`src/rendering/renderthread.h:35-141`).

This supports Phase 3, but preview rendering needs dedicated timeout/cancel/backend tests and should not
be in the first PR.

## Nia/prior-art implications for Amber

The full context summarized several Nia reports and tracer findings. Applied to this repo:

- `burningion/video-editing-mcp`: reinforces using MCP-shaped tool definitions, resource URIs, lazy
  loading, and polling. For Amber first PR, copy the MCP shape but not OTIO/resource complexity yet.
- `samuelgursky/davinci-resolve-mcp`: validates a granular NLE automation surface plus later compound
  tools. For Amber first PR, start granular and deterministic.
- OpenTimelineIO: provides a future canonical IR vocabulary: overwrite, insert, trim, slice, slip,
  slide, ripple, roll, fill, remove. Do not introduce OTIO in PR 1; keep serializer fields compatible
  with later OTIO mapping.
- OpenShot `UpdateAction`: supports JSON command-bus thinking with old/new values and transactions.
  Amber already has `ComboAction`/`QUndoCommand`; do not duplicate a command bus in PR 1.
- Kdenlive: suggests Python sidecars are a good place for AI/perception integrations. Keep sidecars
  outside Amber until the core tool host exists.
- MLT: shows value in a headless engine contract. Amber is not architected as a headless engine today,
  so stdio automation should still initialize the Qt app and GUI-owned state.
- MoviePy: points toward a future fluent SDK layer outside Amber. Do not shape C++ internals around it now.
- CapCut/Jianying draft APIs: useful for social-video workflow schemas, but fragile; avoid copying their
  unofficial API assumptions into Amber core.

Net effect: the prior art strengthens the external-agent/local-tool split and the phased plan. It does
not justify adding more first-PR features.

## Agentic editor loop fit

The full context describes the target loop:

1. external agent ingests media and sidecar perception results;
2. agent reads Amber timeline/project state as JSON;
3. agent plans edits;
4. agent calls Amber tools;
5. Amber mutates through existing undoable edit paths;
6. Amber renders preview frames/segments;
7. external vision/perception critiques the result;
8. agent iterates with undo/redo/snapshots;
9. final export runs through Amber.

PR 1 only covers steps 2, part of 4, and undo/redo for step 8. That is intentional. It creates the
stable process/protocol/threading seam that every later step depends on, without taking on sidecar,
render, export, or compound editing complexity.

## Exact first-PR file plan

Use the full context's proposed layout, but keep each file small:

- `src/automation/CMakeLists.txt`
- `src/automation/automationserver.h`
- `src/automation/automationserver.cpp`
- `src/automation/jsonrpc.h`
- `src/automation/jsonrpc.cpp`
- `src/automation/commands.h`
- `src/automation/commands.cpp`
- `src/automation/serialize.h`
- `src/automation/serialize.cpp`
- `src/automation/mcp_tools.h`
- `src/automation/mcp_tools.cpp`

Responsibilities:

- `AutomationServer`
  - owns stdio reader/writer lifetime;
  - reads newline-delimited JSON-RPC requests;
  - writes protocol responses to stdout only;
  - dispatches fast command handlers onto the GUI thread.
- `jsonrpc.*`
  - validates JSON-RPC 2.0 envelopes;
  - builds `result` and `error` responses;
  - centralizes error codes (`parse_error`, `invalid_request`, `method_not_found`,
    `invalid_params`, `not_ready`, `tool_error`).
- `mcp_tools.*`
  - implements `initialize`, `tools/list`, and `tools/call` response shapes;
  - owns first-PR tool metadata and schemas.
- `commands.*`
  - maps tool names to handlers;
  - validates arguments;
  - calls only safe read-only serializers and existing global slots for `undo`/`redo`;
  - optionally guards and calls `save_project`.
- `serialize.*`
  - serializes project, media, sequence, timeline, clips, and basic undo state;
  - never opens media, starts caching, touches QRhi, or mutates model state.

### CMake integration

In `src/CMakeLists.txt`:

1. Add `add_subdirectory(automation)` after existing `add_subdirectory(core)` /
   `add_subdirectory(engine)` or near the executable setup.
2. Make `src/automation/CMakeLists.txt` define a small object or static library, for example
   `amber-automation`.
3. Link or include that target into `${AMBER_TARGET}` only, not `amber-engine`, because automation
   depends on app/UI globals and should not contaminate headless engine tests.
4. Keep dependencies to Qt Core/Widgets already present through the app target.

If the CMake target split creates linker friction, fallback is adding automation sources directly to
`UI_SOURCES`. That is less clean but still acceptable for the first PR. Prefer the subdirectory because
the full context explicitly asks for it and future agents will expect it.

### Startup changes in `src/main.cpp`

Conservative edits:

1. Add `bool automation_stdio = false;`.
2. Add `--automation-stdio` to `print_help()`.
3. Extend `handle_flag()` / `parse_args()` to set it.
4. Preserve all existing behavior when absent.
5. After `MainWindow w(nullptr)` and panel/app initialization, create `AutomationServer` only when the
   flag is present.
6. In automation mode:
   - still create `QApplication`, `MediaIconService`, `MainWindow`, panels, and app context;
   - do not show the main window;
   - explicitly queue `amber::Global->finished_initialize()` because `finished_first_paint` will not fire;
   - ensure stdout remains protocol-only.
7. In normal mode:
   - keep `w.showFullScreen()` / `w.showMaximized()` behavior unchanged.

Do not add `--automation-headless` in PR 1. The context calls it optional later.

## First-PR tool behavior

### `inspect_project`

Return:

- `amber::AppName`;
- `amber::ActiveProjectFilename`;
- modified state from `amber::Global->is_modified()` or `amber::project_io->isModified()`;
- active sequence summary if `amber::ActiveSequence` exists;
- counts for media, sequences, clips;
- undo/redo availability from `amber::UndoStack.canUndo()` / `canRedo()`.

### `list_media`

Traverse `amber::project_model` with `childCount()` / `child()` and return:

- stable tree path/index;
- name;
- type: `footage`, `sequence`, or `folder`;
- footage URL/name/ready/error fields only when already safe and exposed;
- sequence summary, not full timeline.

### `list_sequences`

Return all sequence media items from project traversal. Avoid depending on `panel_project` where direct
model traversal is enough.

### `inspect_timeline`

Inputs:

- optional sequence path/id; if omitted, use `amber::ActiveSequence`.

Return:

- sequence properties;
- clips with index, name, media reference, media stream index, track, timeline in/out, clip in, enabled,
  speed, linked indexes, transition presence;
- selection summary if useful.

Do not call `Clip::Open()`, `Clip::Cache()`, `Clip::Retrieve()`, `Clip::Close()`, or inspect QRhi fields.

### `undo` and `redo`

Call `AmberGlobal::undo()` and `AmberGlobal::redo()` on the GUI thread. Return:

- whether the call was attempted;
- `canUndo` / `canRedo` after the call;
- current modified state.

These preserve existing behavior through `update_ui(true)` (`src/global/global.cpp:414-428`) and satisfy
the two-mutation acceptance criterion without new edit semantics.

### Optional `save_project`

If included:

- if `amber::ActiveProjectFilename.isEmpty()`, return a structured error such as
  `project_has_no_filename`;
- otherwise call `amber::Global->save_project()` on the GUI thread.

Do not let automation open a save dialog.

## Threading and stdio guidance

The full context suggests an automation `QThread` with stdio reader/writer and GUI-thread dispatch.
That is compatible with the repo, but the implementation must avoid two traps:

1. Stdin handling must not block the GUI thread.
2. `Qt::BlockingQueuedConnection` must never be used from the GUI thread to itself.

Recommended first implementation:

- A dedicated automation thread (either `QThread` or a small `std::thread`) blocks on stdin.
- It parses newline-delimited JSON or forwards raw lines for parsing.
- It dispatches command execution to the GUI thread.
- It writes responses under a mutex to stdout.
- It joins/stops cleanly when stdin closes.

GUI dispatch helper:

- if current thread is `qApp->thread()`, run directly;
- otherwise use `QMetaObject::invokeMethod(..., Qt::BlockingQueuedConnection)` for fast commands;
- return `task_id` immediately for future long tasks instead of blocking.

All read-only inspection should also run on the GUI thread, because `ProjectModel`, `ActiveSequence`, and
clip vectors are GUI-owned.

## README and smoke script

### README

Add a short section covering:

- `--automation-stdio`;
- JSON-RPC newline framing;
- MCP methods implemented;
- first supported tools;
- normal GUI launch unchanged;
- media/timeline/render mutations intentionally deferred.

### Smoke script

Add:

- `scripts/smoke_automation_stdio.py`

Behavior:

1. Locate executable:
   - default `build/amber-editor` on Linux;
   - override with `AMBER_BIN=/path/to/amber-editor`.
2. Launch:
   - `amber-editor --automation-stdio --no-debug`
   - use `QT_QPA_PLATFORM=offscreen` or document `xvfb-run -a` fallback.
3. Send JSON-RPC:
   - `initialize`;
   - `tools/list`;
   - `tools/call` for `inspect_project`;
   - `tools/call` for `undo`.
4. Assert:
   - each stdout line is valid JSON;
   - responses have JSON-RPC envelopes;
   - `inspect_project` includes expected keys;
   - `undo` returns clean no-op or success with undo state.
5. Close stdin and wait with timeout; terminate by Python process handle only if needed.

No media fixture, GPU rendering, or project file should be required for this first smoke.

## Local validation commands

From repo root:

```bash
cmake -S src -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build -j$(nproc)
ctest --test-dir build --output-on-failure
python3 scripts/smoke_automation_stdio.py
```

If there is no display:

```bash
QT_QPA_PLATFORM=offscreen python3 scripts/smoke_automation_stdio.py
```

If Qt Widgets needs a virtual display:

```bash
xvfb-run -a python3 scripts/smoke_automation_stdio.py
```

The PR should state exactly which smoke path was run.

## CI/build risks and mitigations

### Qt JSON

Risk: low. Qt JSON types are in Qt Core, already linked.

Mitigation: use Qt JSON only; do not add `nlohmann/json` or other dependencies.

### stdout protocol corruption

Risk: high if Qt warnings or Amber logs write to stdout.

Mitigation:

- smoke uses `--no-debug`;
- automation writes protocol only to stdout;
- diagnostics go to stderr or the existing internal debug sink;
- smoke rejects non-JSON stdout lines.

### `QSocketNotifier` on stdin

Risk: platform-specific behavior, especially Windows console handles.

Mitigation: prefer a blocking reader in the automation thread for PR 1. If `QSocketNotifier` is used,
test it on Linux and Windows packaging paths before relying on it.

### `QThread` / `std::thread` lifetime

Risk: blocked stdin thread outlives `QApplication`.

Mitigation:

- server owns an atomic running flag;
- closing stdin exits the read loop;
- destructor joins/waits;
- smoke closes stdin before process teardown.

### `BlockingQueuedConnection`

Risk: self-deadlock if called from GUI thread.

Mitigation: centralize GUI dispatch and detect current thread.

### Hidden-window startup

Risk: `finished_first_paint` never fires, so launch-project initialization never runs.

Mitigation: explicitly queue `AmberGlobal::finished_initialize()` in automation mode after app/panel
construction.

### `save_project`

Risk: modal save dialog hangs automation for unsaved projects.

Mitigation: guard on `amber::ActiveProjectFilename.isEmpty()`.

### Media import

Risk: `.ove` imports prompt; media analysis is asynchronous; imported media readiness is timing-sensitive.

Mitigation: defer to PR 2. Initially reject `.ove` and return imported media identities after undo action
push, not after analysis completes.

### Timeline mutations

Risk: panel globals, viewer seek, selections, timeline ghosts, and UI refresh can be bypassed or left
inconsistent.

Mitigation: defer. When implemented, use existing `Timeline` methods on GUI thread and push `ComboAction`.

### Render preview

Risk: QRhi/offscreen resources, backend selection, failure signals, timeout, and cancellation.

Mitigation: defer to dedicated Phase 3 PR with its own smoke fixture.

## Rollback strategy

The first PR should be easy to revert:

- all runtime behavior gated by `--automation-stdio`;
- normal launch remains default;
- automation code isolated under `src/automation/`;
- README and smoke script additive;
- no project format changes;
- no persisted data migration;
- only mutation tools are existing `undo`/`redo` and optional guarded save.

Rollback options:

1. Revert the automation PR.
2. For a hotfix, remove `--automation-stdio` parsing, remove `add_subdirectory(automation)` or source
   entries from CMake, and leave docs/scripts if desired.
3. No data repair should be needed.

## Later implementation order

1. **PR 1: stdio MCP substrate**
   - `--automation-stdio`
   - JSON-RPC/MCP initialize/tools/list/tools/call
   - four read-only tools
   - `undo` and `redo`
   - optional guarded `save_project`
   - README and smoke script
2. **PR 2: safe project mutations**
   - `import_media` via `AppContext::processFileList()` / `Project::process_file_list()`
   - reject `.ove` initially
   - `create_sequence` through `Project::create_sequence_internal()`
3. **PR 3: timeline mutations**
   - `add_clip` through ghost creation and `Timeline::add_clips_from_ghosts()`
   - `move_clip` through `Clip::move(ComboAction*, ...)`
   - `split_clip` through `Timeline::split_clip_and_relink()`
   - `ripple_delete` through selection construction and `Timeline::delete_selection()`
4. **PR 4: preview render**
   - `render_preview_frame` through `RenderThread::start_render()` save path
   - timeout, failure signal, cancellation
5. **PR 5: external Cursor SDK runner**
   - outside Amber
   - treats Amber as stdio MCP server
6. **PR 6+: compound workflows and sidecars**
   - transcript/scene/silence/beat sidecars
   - preview segment
   - OTIO import/export
   - project snapshots/branching
   - social-video compound tools

## Checklist for future Cursor agents

Before editing:

1. Confirm branch is `2.0.lawmight` or the requested feature branch based on it.
2. Read this assessment, `src/main.cpp`, `src/CMakeLists.txt`, and the full agent context if available.
3. Keep Cursor SDK external; do not embed model orchestration in Amber.

During implementation:

4. Add automation under `src/automation/` using the proposed layout.
5. Keep stdout protocol-only.
6. Run every command handler on the GUI thread.
7. Run read-only inspection on the GUI thread too.
8. Do not mutate `Sequence`, `Clip`, `ProjectModel`, or `UndoStack` from automation thread.
9. Do not touch `Clip::Cacher`, QRhi textures, or render resources.
10. Use `ComboAction` and `amber::UndoStack` for every real edit mutation.
11. For first PR, implement only read-only tools plus `undo`/`redo`.
12. Guard `save_project` if included.
13. Preserve normal launch exactly when `--automation-stdio` is absent.

Before submitting:

14. Build:
    - `cmake -S src -B build -DCMAKE_BUILD_TYPE=Debug`
    - `cmake --build build -j$(nproc)`
15. Run:
    - `ctest --test-dir build --output-on-failure`
    - `python3 scripts/smoke_automation_stdio.py`
16. Confirm smoke covers `inspect_project` and one mutation tool.
17. Confirm no non-JSON stdout in automation mode.
18. Confirm no feature code for later phases slipped into PR 1.
19. Document any environment-specific smoke fallback used (`offscreen` vs `xvfb-run`).
