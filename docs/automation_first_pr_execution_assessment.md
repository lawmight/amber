# Amber 2.0.lawmight automation first-PR execution assessment

## Executive recommendation

Make the first PR a small, reviewable automation transport and read-only command slice:

1. Add an explicit `--automation-stdio` launch flag.
2. Start Amber exactly as the normal GUI does, but hide the main window in automation mode.
3. Implement minimal JSON-RPC/MCP methods: `initialize`, `tools/list`, and `tools/call`.
4. Expose four read-only tools:
   - `inspect_project`
   - `list_media`
   - `list_sequences`
   - `inspect_timeline`
5. Include two mutation-class tools only if they are thin wrappers around existing global actions:
   - `undo`
   - `redo`
6. Include `save_project` as either:
   - a guarded mutation that refuses unsaved projects with a structured error, because
     `AmberGlobal::save_project()` opens a save dialog when `amber::ActiveProjectFilename` is empty; or
   - a listed-but-unimplemented placeholder returning `not_implemented`.

Do **not** include `import_media`, `create_sequence`, `add_clip`, `split_clip`, `ripple_delete`, or
`render_preview_frame` in the first PR. Those commands are valuable, but they cross UI-panel state,
undo grouping, media analysis, timeline ghosts, and render-thread behavior. Including them in the
first PR materially raises compile and review risk.

The first PR should prove the seam: normal launch remains unchanged, `--automation-stdio` is explicit,
JSON-RPC can drive Amber after startup, read-only state serialization works, and simple existing
undo/redo/save entry points can be invoked on the GUI thread.

## Repository facts verified

### Build system

- Top-level CMake entry is `src/CMakeLists.txt`.
- Project is C++17 (`src/CMakeLists.txt:9-11`) with Qt automoc/autouic/autorcc enabled
  (`src/CMakeLists.txt:13-16`).
- Qt components already include `Qt6::Core`, `Qt6::Gui`, `Qt6::Widgets`, and others
  (`src/CMakeLists.txt:31-44`). `QJsonDocument`, `QJsonObject`, `QJsonArray`, `QFile`,
  `QSocketNotifier`, and `QMetaObject` are all in Qt Core, so no new third-party dependency is needed.
- Core non-UI code is collected in the `amber-engine` object library (`src/CMakeLists.txt:98-163`).
- UI/application sources are listed in `UI_SOURCES`, currently including `main.cpp`
  (`src/CMakeLists.txt:181-268`).
- Executable target is `amber-editor` except on Apple, where it is `Amber`
  (`src/CMakeLists.txt:358-363`).
- Tests are enabled only when not cross-compiling (`src/CMakeLists.txt:386-390`).
- Existing shader and export-preset post-build copy steps are attached to the app target
  (`src/CMakeLists.txt:404-417`).

### Test setup

- Tests live in `src/tests/` and are registered with CTest in `src/tests/CMakeLists.txt`.
- Existing test targets link `amber-engine` plus `Qt6::Test`; UI symbols are satisfied by
  `src/tests/test_ui_stubs.cpp` (`src/tests/CMakeLists.txt:3-8`).
- `src/tests/test_projectio.cpp` provides a useful pattern for headless tests with a stub
  `AppContext` (`src/tests/test_projectio.cpp:10-37`).
- Because the automation server will need UI types and startup behavior, the most useful first
  smoke test should be a script that runs the built app, not a Qt unit test linked only to
  `amber-engine`.

### CI/release workflows

- `.github/workflows/build.yml` builds packages on `workflow_dispatch` and release publication.
- `.github/workflows/preview.yml` only triggers package builds on pushes to `2.0.x` with `[preview]`
  in the commit message (`.github/workflows/preview.yml:3-6`, `:16-27`).
- The workflows build Docker AppImage/Windows packages and macOS packages. They do not currently
  run a PR CTest workflow. The first automation PR should therefore be locally validated with the
  commands in this document and not rely on CI to catch regressions.

### Startup parsing and normal launch

- Startup parsing is custom `argc`/`argv` handling in `src/main.cpp`, not `QCommandLineParser`.
- `handle_flag()` recognizes current options and rejects unknown flags
  (`src/main.cpp:88-134`).
- `parse_args()` treats the first non-flag argument as the project filename
  (`src/main.cpp:136-148`).
- `main()` always:
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
- `AmberGlobal::finished_initialize()` is the point where startup project loading actually runs
  (`src/global/global.cpp:324-345`).

### Project, sequence, and timeline seams

- Current project tree is `amber::project_model` (`src/project/projectmodel.h:65-67`), with
  `childCount()`, `child()`, and `getItem()` available for traversal
  (`src/project/projectmodel.h:50-58`).
- `Media` exposes `get_type()`, `get_name()`, `to_footage()`, `to_sequence()`, `childCount()`,
  and `child()` (`src/project/media.h:45-70`).
- `Sequence` exposes serializable fields directly: `name`, `width`, `height`, `frame_rate`,
  `audio_frequency`, `audio_layout`, `playhead`, `workarea_*`, `markers`, `guides`, and `clips`
  (`src/engine/sequence.h:38-70`).
- `Clip` exposes safe read methods for timeline/media state: `media()`, `media_stream_index()`,
  `timeline_in()`, `timeline_out()`, `clip_in()`, `track()`, `enabled()`, `name()`, `speed()`,
  `linked`, and transition pointers (`src/engine/clip.h:81-122`, `:137-141`).
- `Clip` also owns `Cacher` and QRhi resources (`src/engine/clip.h:144-179`, `:196-197`).
  First-PR serialization must not touch `Open()`, `Cache()`, `Retrieve()`, `Close()`, `Cacher`,
  or QRhi fields.

### Undo, redo, save, import, sequence, split, and ripple seams

- Global undo stack is `amber::UndoStack`, a `QUndoStack` (`src/engine/undo/undostack.h:6-10`,
  `src/engine/undo/undostack.cpp:1-3`).
- `ComboAction` is the established grouping mechanism for multi-step mutations and owns appended
  `QUndoCommand`s (`src/engine/undo/comboaction.h:19-83`).
- Global undo/redo slots already route through UI refresh and avoid running while timeline import is
  active (`src/global/global.cpp:414-428`).
- `AmberGlobal::save_project()` saves to the current project path or opens the Save As dialog if
  there is no project filename (`src/global/global.cpp:290-297`). Automation must not call it blindly
  on an unsaved project.
- Import flow exists at `AppContext::processFileList()` (`src/core/appcontext.h:35`) and concrete
  `AppContextImpl::processFileList()` forwards to `Project::process_file_list()`
  (`src/ui/appcontextimpl.cpp:96-100`).
- `Project::process_file_list()` creates a `ComboAction("Import Media")`, appends media to the project,
  pushes the action in `finalize_import()`, and starts `PreviewGenerator::AnalyzeMedia()` for imported
  items (`src/panels/project.cpp:827-887`, `:820-824`).
- `Project::process_file_list()` can prompt when importing `.ove` files (`src/panels/project.cpp:856-863`),
  so an automation import command must initially reject `.ove` inputs or add a non-interactive policy.
- Sequence creation entry points exist:
  - `create_sequence_from_media()` (`src/panels/project.cpp:240-300`);
  - `Project::create_sequence_internal()` (`src/panels/project.h:62`);
  - `NewSequenceDialog` currently pushes a `ComboAction("Create Sequence")`
    (`src/dialogs/newsequencedialog.cpp:97-113`).
- Add-clip via timeline ghost import exists:
  - `Timeline::create_ghosts_from_media()` (`src/panels/timeline.h:131`);
  - `Timeline::add_clips_from_ghosts()` (`src/panels/timeline.h:132`,
    implementation `src/panels/timeline.cpp:288-353`).
  This path depends on `panel_sequence_viewer` for optional seek (`src/panels/timeline.cpp:347-349`).
- Split is implemented through `Timeline::split_clip()`, `Timeline::split_clip_and_relink()`, and
  related helpers (`src/panels/timeline.h:116-121`, `src/panels/timeline_splitting.cpp:74-188`).
- Ripple delete is selection-driven through `Timeline::delete_selection()` and `Timeline::ripple_delete()`
  (`src/panels/timeline.cpp:732-751`, `:1045-1055`).

### Render preview seam

- `RenderThread::start_render()` already accepts a save path and supports frame save failure signaling
  (`src/rendering/renderthread.h:61-76`).
- `RenderThread` is `QThread`-based and owns QRhi/offscreen state (`src/rendering/renderthread.h:35-141`).
  A first PR should not introduce a preview-frame tool because reliable timeout, cancellation, backend,
  and headless behavior need dedicated testing.

## Smallest high-confidence first PR

### Scope

Implement:

- `--automation-stdio`
- JSON-RPC framing over newline-delimited JSON on stdin/stdout
- MCP-compatible:
  - `initialize`
  - `tools/list`
  - `tools/call`
- Read-only tools:
  - `inspect_project`
  - `list_media`
  - `list_sequences`
  - `inspect_timeline`
- Mutation-class tools:
  - `undo`
  - `redo`
- Optional guarded `save_project`:
  - returns an error if `amber::ActiveProjectFilename` is empty;
  - otherwise invokes `amber::Global->save_project()` on the GUI thread.
- README documentation for automation mode.
- A smoke script that starts the app in `--automation-stdio` mode, calls `initialize`,
  `tools/call inspect_project`, and one mutation-class tool (`undo` is safest on a clean project).

### Defer

Defer these to follow-up PRs:

- `import_media`
- `create_sequence`
- `add_clip`
- `split_clip`
- `ripple_delete`
- `render_preview_frame`
- external Cursor SDK runner

Rationale: the first PR should validate process lifetime, startup readiness, JSON protocol, thread
handoff, and serialization. Timeline/media mutations should land once the automation harness is
trusted and a regression script can prove undo/redo around real project state.

## Exact file changes for the first PR

### Add automation source files

Use a small set of files rather than the full proposed layout:

- `src/automation/automationserver.h`
- `src/automation/automationserver.cpp`
- `src/automation/commands.h`
- `src/automation/commands.cpp`
- `src/automation/serialize.h`
- `src/automation/serialize.cpp`

Do not add a separate `jsonrpc.*` or `mcp_tools.*` in the first PR unless the implementation becomes
hard to read. A single server class plus command/serialization helpers is easier to review.

Suggested responsibilities:

- `AutomationServer`
  - Owns stdin notifier or reader thread.
  - Writes JSON responses to stdout.
  - Implements JSON-RPC dispatch and method validation.
  - Emits a signal or uses `QMetaObject::invokeMethod()` to execute tool calls on the GUI thread.
- `commands.*`
  - Maps tool names to handlers.
  - Performs input validation and returns `QJsonObject` results/errors.
  - Calls only stable public seams: `amber::Global->undo()`, `amber::Global->redo()`,
    guarded `amber::Global->save_project()`, and read-only traversal.
- `serialize.*`
  - Converts `ProjectModel`, `Media`, `Sequence`, and `Clip` state to `QJsonObject`/`QJsonArray`.
  - Never opens media, caches, renderers, or QRhi resources.

### Integrate with CMake

Minimal change in `src/CMakeLists.txt`:

1. Add the automation sources to `UI_SOURCES` near `main.cpp` because they depend on UI globals and
   `AmberGlobal`:

   ```cmake
   automation/automationserver.cpp automation/automationserver.h
   automation/commands.cpp automation/commands.h
   automation/serialize.cpp automation/serialize.h
   ```

2. Do not add a new library target in the first PR. Adding a new CMake subdirectory is fine later,
   but the initial path with the fewest linker surprises is compiling into the existing app target.

No new `find_package()` entry is needed for JSON; Qt Core is already linked.

### Modify startup

Change `src/main.cpp` conservatively:

1. Add `bool automation_stdio = false;`.
2. Add `--automation-stdio` to `print_help()`.
3. Extend `handle_flag()` and `parse_args()` to set `automation_stdio`.
4. Preserve every existing default path when the flag is absent.
5. After `MainWindow w(nullptr)` and existing initialization wiring, construct and start
   `AutomationServer` only if `automation_stdio` is true.
6. In automation mode:
   - do not call `w.showMaximized()` or `w.showFullScreen()`;
   - still create the `MainWindow`, panels, `AppContextImpl`, `MediaIconService`, etc.;
   - explicitly schedule `amber::Global->finished_initialize()` with `QTimer::singleShot(0, ...)`
     or rely on a direct initialization path, because `finished_first_paint` will not fire if the
     window is never shown.

The key review invariant is: without `--automation-stdio`, lines equivalent to current
`w.showFullScreen()` / `w.showMaximized()` behavior still run unchanged.

### Startup readiness

The server should not answer project-inspection calls until initialization has completed:

- Track readiness after `AmberGlobal::finished_initialize()` has run.
- For the first PR, if a request arrives before readiness, either:
  - queue it until ready; or
  - return a structured `not_ready` error.

Prefer queueing only for `initialize`; tool calls can return `not_ready` until ready. This avoids
hidden hangs in smoke tests.

### JSON-RPC/MCP shape

Use JSON-RPC 2.0 response envelopes:

```json
{"jsonrpc":"2.0","id":1,"result":{...}}
{"jsonrpc":"2.0","id":2,"error":{"code":-32601,"message":"Method not found"}}
```

Supported methods:

- `initialize`
  - returns protocol/server info and capabilities.
- `tools/list`
  - returns tool definitions with JSON-schema-like `inputSchema`.
- `tools/call`
  - accepts `{ "name": "...", "arguments": { ... } }`.

For MCP compatibility, `tools/call` can return:

```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"project\":{...}}"
    }
  ]
}
```

This is not the prettiest interface, but it is compatible and minimizes custom client assumptions.

### Tool behavior

#### `inspect_project` (read-only)

Return:

- app name/version string from `amber::AppName`
- project filename from `amber::ActiveProjectFilename`
- modified state from `amber::Global->is_modified()` or `amber::project_io->isModified()`
- active sequence summary, if any
- counts for root media items, sequences, and clips
- undo/redo availability from `amber::UndoStack.canUndo()` / `canRedo()`

#### `list_media` (read-only)

Traverse `amber::project_model` using `childCount()` / `child()` and serialize:

- stable path/index within project tree
- name
- type: `footage`, `sequence`, or `folder`
- for footage: URL/name and ready/error fields only if already exposed safely by `Footage`
- for sequence: sequence summary only, not full timeline

#### `list_sequences` (read-only)

Return all sequence media items from project traversal. Avoid depending on `panel_project` if possible,
even though `Project::list_all_project_sequences()` exists (`src/panels/project.h:80`), because direct
model traversal is simpler to test and has fewer UI-panel assumptions.

#### `inspect_timeline` (read-only)

Inputs:

- optional sequence identifier/path; if omitted, inspect `amber::ActiveSequence`.

Return:

- sequence properties (`name`, dimensions, frame rate, audio settings, playhead, work area)
- clips with index, name, media reference, stream index, track, timeline in/out, clip in, enabled,
  speed value, linked indexes, and transition presence
- selections only if useful

Do not call `Clip::Open()`, `Clip::Cache()`, `Clip::Retrieve()`, `Clip::Close()`,
`Clip::media_width()`, or `Clip::media_height()` unless already known safe for unloaded media.

#### `undo` / `redo` (mutation-class, existing global behavior)

Call `AmberGlobal::undo()` and `AmberGlobal::redo()` on the GUI thread. Return:

- whether the action was attempted
- `canUndo` / `canRedo` after the call
- current modified state

These preserve existing behavior and UI refresh through `update_ui(true)`
(`src/global/global.cpp:414-428`).

#### `save_project` (optional guarded mutation)

If included, enforce:

- if `amber::ActiveProjectFilename.isEmpty()`, return an error like
  `{"code":"project_has_no_filename","message":"save_project requires an existing project path"}`.
- otherwise call `amber::Global->save_project()` on the GUI thread.

Do not show a file dialog from automation.

## Threading and stdio implementation guidance

### Recommended first implementation

Use a small background `std::thread` to read newline-delimited JSON from `std::cin`, then hand requests
to the Qt event loop with `QMetaObject::invokeMethod()`.

Why this is lower risk than `QSocketNotifier`:

- `QSocketNotifier` on stdin can differ across platforms and is awkward on Windows console handles.
- A blocking reader thread keeps stdin handling independent from the GUI event loop.
- Qt JSON parsing remains in-process with no dependency.

Rules:

- Never mutate Amber state directly from the reader thread.
- Parse the JSON line in the reader thread or GUI thread, but execute all command handlers on the GUI
  thread.
- Serialize writes to stdout with a mutex.
- Use newline-delimited JSON for request/response framing.
- Do not log debug output to stdout in automation mode. stdout must be protocol-only.

### `invokeMethod` and blocking risk

Avoid `Qt::BlockingQueuedConnection` from the GUI thread to itself; it deadlocks. A safe helper should:

- if already on `qApp->thread()`, run the handler directly;
- otherwise use `QMetaObject::invokeMethod(qApp, lambda, Qt::BlockingQueuedConnection)` only from the
  reader thread.

Alternatively use queued invocation and a promise/future. That avoids accidental self-deadlocks but
requires more code.

### Logger/stdout risk

`main.cpp` installs `debug_message_handler` unless `--no-debug` is passed (`src/main.cpp:265`).
The first PR must verify where that handler writes. In automation mode, force diagnostic output to
stderr or the existing internal debug sink, never stdout. Protocol stdout corruption is a hard failure.

## README and smoke script

### README changes

Add a concise section to `README.md`:

- `--automation-stdio` description
- newline-delimited JSON-RPC example
- warning that normal GUI launch is unchanged
- list of first supported tools
- note that media/timeline mutation and preview render tools are intentionally deferred

Keep this short; detailed protocol docs can follow once the API stabilizes.

### Smoke script path

Add:

- `scripts/smoke_automation_stdio.py`

The repository currently has no tracked `scripts/` directory. Creating one for this single smoke
script is reasonable.

### Smoke script behavior

The script should:

1. Locate the built executable:
   - default `build/amber-editor` on Linux;
   - allow override via `AMBER_BIN=/path/to/amber-editor`.
2. Start with:
   - `QT_QPA_PLATFORM=offscreen` where available, or document `xvfb-run` fallback;
   - `AMBER_RHI_BACKEND=opengl` if needed for a deterministic local smoke.
3. Launch:
   - `amber-editor --automation-stdio --no-debug`
4. Send:
   - `initialize`
   - `tools/call` for `inspect_project`
   - `tools/call` for `undo`
5. Assert:
   - valid JSON-RPC response envelopes;
   - `inspect_project` contains expected keys;
   - `undo` returns success or a clean no-op with `canUndo=false`.
6. Terminate the process gracefully:
   - prefer an automation `shutdown` method if implemented;
   - otherwise close stdin and wait with a timeout, then terminate by process handle from Python.

Do not make the script require media files or GPU rendering.

## Local validation commands

From repository root:

```bash
cmake -S src -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build -j$(nproc)
ctest --test-dir build --output-on-failure
python3 scripts/smoke_automation_stdio.py
```

If the local machine lacks a display:

```bash
QT_QPA_PLATFORM=offscreen python3 scripts/smoke_automation_stdio.py
```

If offscreen is insufficient for Qt Widgets on a given runner:

```bash
xvfb-run -a python3 scripts/smoke_automation_stdio.py
```

The implementation PR should document which of those smoke paths was actually run.

## CI/build risks and mitigations

### Qt JSON

Risk: none expected. `QJsonDocument`, `QJsonObject`, and `QJsonArray` are in Qt Core, already linked.

Mitigation: keep all JSON code Qt-native; do not add `nlohmann/json` or any package dependency.

### Stdio transport

Risk: stdout protocol corruption from existing logging or Qt warnings.

Mitigation:

- Require `--automation-stdio --no-debug` in smoke docs.
- In automation mode, route protocol only to stdout and diagnostics to stderr/internal log.
- Add test assertions that every stdout line is valid JSON.

### `QSocketNotifier` on stdin

Risk: platform-specific behavior, especially Windows console handles.

Mitigation: use a `std::thread` reader for the first PR. If `QSocketNotifier` is used later, keep it
behind platform-specific tests.

### `std::thread`

Risk: shutdown/lifetime bugs if the reader thread blocks after `QApplication` exits.

Mitigation:

- The server owns an atomic `running` flag.
- Closing stdin should exit the read loop.
- Destructor joins if joinable.
- Smoke script closes stdin and waits for process exit.

### `QMetaObject::invokeMethod` / blocking calls

Risk: deadlock if `BlockingQueuedConnection` is used from GUI thread.

Mitigation: centralize GUI-thread dispatch in one helper that detects current thread before blocking.

### Hidden window automation mode

Risk: `finished_first_paint` will not fire if no window is shown, so project-on-launch initialization
may never happen.

Mitigation: in automation mode, explicitly call or queue `AmberGlobal::finished_initialize()` after
panel construction. Smoke test should cover `inspect_project` after startup.

### Save command

Risk: unsaved project opens a modal save dialog and hangs automation.

Mitigation: guard on `amber::ActiveProjectFilename.isEmpty()` before calling `save_project()`.

### Import/media mutations

Risk: `Project::process_file_list()` can prompt for `.ove` imports and triggers asynchronous media
analysis (`PreviewGenerator::AnalyzeMedia()`), making smoke behavior timing-sensitive.

Mitigation: defer import to PR 2. When implemented, reject `.ove` first and return imported media IDs
after the undo action is pushed.

### Add-clip/split/ripple mutations

Risk: existing paths assume panel globals, viewer state, selections, and timeline ghosts. Direct use can
silently bypass undo/redo or leave UI state inconsistent.

Mitigation: defer until the automation harness exists. Implement only through existing `Timeline` and
`Project` methods, with every mutation on the GUI thread and grouped in `ComboAction`.

### Render preview

Risk: render thread uses QRhi/offscreen resources and save-path behavior; timeout/cancel handling is
not trivial.

Mitigation: defer to a dedicated PR with one focused smoke script and a known tiny project/media fixture
or generated sequence.

## Rollback strategy

The first PR should be easy to revert:

- All new behavior is gated by `--automation-stdio`.
- Normal launch code path remains the default.
- New files live under `src/automation/`.
- README and smoke script are additive.
- CMake integration is a small `UI_SOURCES` addition.

If problems appear after merge:

1. Revert the single automation PR.
2. If a narrow hotfix is preferred, remove the `--automation-stdio` flag handling and automation source
   entries from `src/CMakeLists.txt`; no project file format or runtime data migration is involved.
3. Because first-PR mutations are limited to existing `undo`/`redo` and guarded `save_project`, no data
   repair should be needed.

## Later implementation checklist for Cursor agents

Use this checklist when implementing the first PR:

1. Confirm current branch is based on `2.0.lawmight`.
2. Read `src/main.cpp`, `src/CMakeLists.txt`, and this assessment before editing.
3. Add automation sources under `src/automation/`; do not touch `Clip::Cacher` or QRhi paths.
4. Add `--automation-stdio` parsing without changing behavior for existing flags.
5. Hide the window only in automation mode; preserve `showMaximized()` / `showFullScreen()` otherwise.
6. Ensure automation startup reaches the same initialized state as normal launch.
7. Keep stdout protocol-only.
8. Run all command handlers on the GUI thread.
9. Implement only read-only serialization plus `undo`/`redo` and optional guarded `save_project`.
10. Validate command inputs and return structured JSON-RPC errors.
11. Add README documentation and `scripts/smoke_automation_stdio.py`.
12. Build locally:
    - `cmake -S src -B build -DCMAKE_BUILD_TYPE=Debug`
    - `cmake --build build -j$(nproc)`
13. Run:
    - `ctest --test-dir build --output-on-failure`
    - `python3 scripts/smoke_automation_stdio.py`
14. Verify manual normal launch or at least a no-automation startup smoke remains unchanged.
15. Do not add timeline/media mutation tools until the first PR has landed and the stdio harness is
    trusted.

## Recommended follow-up PR order

1. **PR 1: stdio automation + read-only tools + undo/redo/guarded save.**
2. **PR 2: safe project mutations.**
   - `import_media`, rejecting `.ove` initially.
   - `create_sequence` through `Project::create_sequence_internal()` and `ComboAction`.
3. **PR 3: timeline mutations.**
   - `add_clip` through ghost creation + `Timeline::add_clips_from_ghosts()`.
   - `split_clip` through `Timeline::split_clip_and_relink()`.
   - `ripple_delete` through selection construction + `Timeline::delete_selection()`.
4. **PR 4: render preview frame.**
   - `RenderThread::start_render()` with save path, timeout, failure signal, and cancellation.
5. **PR 5: external Cursor SDK runner.**
   - Keep outside Amber; treat Amber as a stdio MCP server.
