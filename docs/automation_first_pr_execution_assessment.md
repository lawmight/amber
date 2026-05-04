# Automation-first PR execution assessment

Target branch assessed: `2.0.lawmight` at `77342dbb` (`origin/2.0.lawmight` when inspected from
`cursor/amber-automation-pr-assessment-1c9e`).

This assessment is for the first reviewable PR toward making Amber controllable by an external Cursor SDK agent. It is
intentionally not a feature implementation plan for embedding an LLM in Amber. Amber should expose deterministic local
editing tools; a separate agent process should plan, call tools, request previews, critique results, and iterate.

## Executive recommendation

The smallest reviewable first PR should be a read-only automation skeleton behind an explicit startup flag:

1. Add `amber --automation-stdio`.
2. Add a minimal stdio JSON-RPC/MCP-compatible server that supports:
   - `initialize`
   - `tools/list`
   - `tools/call`
   - `inspect_project`
   - `list_sequences`
   - `get_active_sequence`
   - `inspect_timeline`
3. Keep every project read on the GUI thread.
4. Include a smoke script that launches Amber in automation mode, sends `initialize`, calls `tools/list`, then calls
   `inspect_project`.
5. Do not include mutation tools, render preview, Cursor SDK code, HTTP, or headless mode in this first PR.

Reasoning: the hard first risk is not editing operations; it is proving Amber can launch normally and also launch as a
controllable process without destabilizing Qt startup, RHI setup, project loading, CMake, or tests. Mutations should be
the second PR, once the thread-hop and protocol boundary have review coverage.

If the broader acceptance target still requires "at least 4 read-only tools and 2 mutation tools" in a single Cursor
agent implementation, split that into two review layers:

- PR 1: automation transport + four read-only tools.
- PR 2: `undo`, `redo`, and one safe timeline mutation routed through `ComboAction` + `amber::UndoStack`.

## Prior art and Nia research context used

The local `/opt/data/home/amber-research-results/` directory was not present in this checkout, so I could not read the
saved oracle/tracer files directly. I used the full handoff content as design context, including these referenced Nia
outputs:

- `oracle_automation_api_architecture.md`
- `oracle_agentic_video_editor_loop.md`
- `oracle_amber_code_integration_map.md`
- `tracer_existing_video_editor_automation_projects.md`
- `tracer_capcut_jianying_draft_api_mcp_projects.md`
- `tracer_open_source_nle_architectures.md`
- `summary_for_tom.txt`

Design constraints carried forward from that research:

- Prefer stdio MCP/JSON-RPC first over HTTP: no local port, smaller attack surface, no browser-origin concerns, and a
  natural parent-process trust model.
- Use the editor as a deterministic tool host, not as the agent brain.
- Follow the shape of `burningion/video-editing-mcp` and `samuelgursky/davinci-resolve-mcp`: granular inspect/call
  tools first, compound tools later.
- Keep OpenTimelineIO edit vocabulary in mind for later mutation semantics (`insert`, `overwrite`, `trim`, `slice`,
  `slip`, `slide`, `ripple`, `roll`), but do not add OTIO import/export in PR 1.
- Treat OpenShot's JSON command bus and Kdenlive's sidecar pattern as evidence that Amber can stay a normal Qt editor
  while external tools drive it.
- Avoid closed-app automation assumptions from CapCut/Jianying projects; they are useful only for future social-video
  schemas, not for Amber's first local control surface.

## Verified current code seams

### Startup and command-line parsing

Verified files/symbols:

- `src/main.cpp`
  - `static RhiBackend parseRhiBackend(const char* name)`
  - `static void print_help(const char* prog)`
  - `static bool handle_flag(int argc, char* argv[], int& i, bool& launch_fullscreen, bool& use_internal_logger)`
  - `static bool parse_args(int argc, char* argv[], bool& launch_fullscreen, QString& load_proj, bool& use_internal_logger)`
  - `int main(int argc, char* argv[])`

Current behavior:

- `main()` constructs `amber::Global` before parsing args.
- `parse_args()` treats the first non-flag token as `load_proj`.
- `handle_flag()` knows `--version`, `--help`, `--fullscreen`, `--rhi-backend`, `--disable-shaders`, `--no-debug`,
  `--disable-blend-modes`, and `--translation`.
- Unknown flags are fatal for startup (`handle_flag()` prints an error and returns `false`).
- Qt app construction, RHI backend resolution, `MainWindow` construction, `finished_first_paint`, project-on-launch,
  and window show happen after parsing.

First PR implication:

- Add `--automation-stdio` in `handle_flag()` and `print_help()`.
- Store it in a local `bool automation_stdio = false` or a tiny options struct passed out of `parse_args()`.
- Do not change existing filename parsing.
- Normal launch must remain bit-for-bit behaviorally equivalent when the flag is absent.
- Automation mode should still construct `QApplication` and `MainWindow` initially. Avoid `--automation-headless` in
  PR 1 because RHI, panels, globals, and app context currently assume a UI-backed app.

### Project and global app state

Verified files/symbols:

- `src/global/global.h`
  - `class AmberGlobal`
  - `AmberGlobal::load_project_on_launch(const QString& s)`
  - `AmberGlobal::save_project()`
  - `AmberGlobal::undo()`
  - `AmberGlobal::redo()`
  - `AmberGlobal::finished_initialize()`
  - `AmberGlobal::set_sequence(SequencePtr s, bool record_history = false)`
  - `namespace amber { extern std::unique_ptr<AmberGlobal> Global; }`
- `src/global/projectio.h`
  - `class ProjectIO`
  - `ProjectIO::setSequence(SequencePtr s, bool record_history = false)`
  - `namespace amber { extern ProjectIO* project_io; }`
- `src/engine/sequence_fwd.h`
  - `namespace amber { extern SequencePtr ActiveSequence; }`
- `src/project/projectmodel.h`
  - `class ProjectModel`
  - `namespace amber { extern ProjectModel project_model; }`

First PR implication:

- Read-only commands should snapshot:
  - `amber::ActiveProjectFilename`
  - `amber::Global->projectIO()->projectFilename()` if `amber::Global` is ready
  - `amber::ActiveSequence`
  - `amber::project_model.get_root()`
- Serialize safely and shallowly. Do not walk UI widgets from the automation thread.

### App-context seam

Verified files/symbols:

- `src/core/appcontext.h`
  - `class AppContext`
  - `AppContext::listAllSequences()`
  - `AppContext::processFileList(QStringList& files, bool recursive, MediaPtr replace, Media* parent)`
  - `namespace amber { extern AppContext* app_ctx; }`
- `src/ui/appcontextimpl.h`
  - `class AppContextImpl : public AppContext`

First PR implication:

- `list_sequences` can use `amber::app_ctx->listAllSequences()` if `app_ctx` is initialized; otherwise return an empty
  sequence list plus a readiness field.
- Do not call `processFileList()` in PR 1. It is a future mutation/import seam.

### Timeline and edit operations

Verified files/symbols:

- `src/engine/sequence.h`
  - `class Sequence`
  - fields: `name`, `width`, `height`, `frame_rate`, `audio_frequency`, `audio_layout`, `playhead`, `clips`,
    `markers`, `guides`, `selections`
  - methods: `getTrackLimits(int* video_tracks, int* audio_tracks)`, `getEndFrame()`
- `src/engine/clip.h`
  - `class Clip`
  - `Clip::move(ComboAction* ca, long iin, long iout, long iclip_in, int itrack, bool verify_transitions = true,
    bool relative = false)`
  - getters: `media()`, `media_stream()`, `media_width()`, `media_height()`, `media_frame_rate()`, `media_length()`,
    `clip_in()`, `timeline_in()`, `timeline_out()`, `track()`, `name()`, `speed()`
  - render/cacher state that automation must not touch directly: `Cacher cacher`, `QRhiTexture* cached_rhi_tex`,
    YUV/RGBA texture fields, `NeedsCpuRgba()`, `NeedsCacherReconfigure()`
- `src/panels/timeline.h`
  - `class Timeline`
  - `Timeline::split_clip(...)`
  - `Timeline::split_all_clips_at_point(ComboAction* ca, long point)`
  - `Timeline::delete_areas_and_relink(ComboAction* ca, QVector<Selection>& areas, bool deselect_areas)`
  - `Timeline::create_ghosts_from_media(...)`
  - `Timeline::add_clips_from_ghosts(ComboAction* ca, Sequence* s)`
  - slots such as `ripple_delete()`, `edit_to_in_point()`, `ripple_to_in_point()`
  - free function `ripple_clips(ComboAction* ca, Sequence* s, long point, long length, const QVector<int>& ignore = QVector<int>())`

First PR implication:

- `inspect_timeline` should serialize `Sequence` and `Clip` state only through getters and public collections.
- Do not mutate `Sequence::clips`, `Clip` private fields, `Cacher`, or QRhi resources directly.
- Future mutation PRs should reuse `Timeline` methods or undo command classes rather than constructing ad hoc edits.

### Undo system

Verified files/symbols:

- `src/engine/undo/undostack.h`
  - `namespace amber { extern QUndoStack UndoStack; }`
- `src/engine/undo/comboaction.h`
  - `class ComboAction : public QUndoCommand`
  - `ComboAction::append(QUndoCommand* u)`
  - `ComboAction::appendPost(QUndoCommand* u)`
  - `ComboAction::hasActions()`
- `src/engine/undo/undo.h`
  - includes `undoactions.h`, `undo_clip.h`, `undo_timeline.h`, `undo_effect.h`, `undo_media.h`, `undo_generic.h`

Current usage examples found by search:

- `src/dialogs/newsequencedialog.cpp` creates `ComboAction(tr("Create Sequence"))` and pushes via
  `amber::UndoStack.push(ca)`.
- `src/ui/timelinewidget.cpp` builds `ComboAction(tr("Add Clip(s)"))`, calls timeline/clip helpers, then pushes to
  `amber::UndoStack`.
- `src/dialogs/autocutsilencedialog.cpp` builds grouped timeline edits and pushes a single undoable action.

First PR implication:

- PR 1 should not add mutation commands.
- PR 2 mutation rule: if a command changes project/timeline state, it must build a `ComboAction` or existing
  `QUndoCommand`, then push to `amber::UndoStack` on the GUI thread.

### Rendering and export seams

Verified files/symbols:

- `src/rendering/renderthread.h`
  - `class RenderThread : public QThread`
  - `RenderThread::start_render(Sequence* s, int playback_speed, const QString& save = nullptr, void* pixels = nullptr,
    int pixel_linesize = 0, int idivider = 0, bool scrubbing = false)`
  - `RenderThread::get_frame_data(int buffer_index) const`
  - `RenderThread::get_frame_width() const`
  - `RenderThread::get_frame_height() const`
  - `RenderThread::DeferRhiResourceDeletion(...)`
- `src/rendering/exportthread.h`
  - `struct ExportParams`
  - `struct VideoCodecParams`
  - `class ExportThread : public QThread`
  - `ExportThread::Interrupt()`

First PR implication:

- Do not add `render_preview_frame` in PR 1. It crosses into QRhi/offscreen threading and needs its own test surface.
- For later preview PRs, prefer returning a generated image path and metadata over raw pixels in JSON.

### Effects

Verified files/symbols:

- `src/effects/effect.h`
  - `struct EffectMeta`
  - global `QVector<EffectMeta> effects`
  - `get_meta_from_name(const QString& input)`
  - `class Effect`
  - `Effect::save_to_string()`
  - `Effect::load_from_string(const QByteArray& s)`
  - `Effect::Create(Clip* c, const EffectMeta* em)`
  - `Effect::GetInternalMeta(int internal_id, int type)`
  - `Effect::VideoEffectFlags`, including `ImageFlag`

First PR implication:

- Read-only `inspect_timeline` can include effect names/metadata if straightforward, but it is acceptable to defer
  deep effect serialization to a later PR.
- Future `apply_effect` must account for `ImageFlag` effects and `Clip::NeedsCacherReconfigure()`.

## Recommended first PR file layout

Suggested files:

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
- `scripts/automation_smoke.py` or `tools/automation_smoke.py`
- `docs/automation.md`

For the smallest PR, `mcp_tools.*` can be folded into `commands.*` if that keeps review easier. The important boundary
is not the number of files; it is the separation between:

- stdio framing/protocol parsing,
- command dispatch,
- GUI-thread state access,
- JSON serialization of Amber objects.

## CMake integration recommendation

Current CMake shape verified:

- Root CMake file is `src/CMakeLists.txt`.
- `amber-engine` is an `OBJECT` library containing engine/effects/rendering/project/global non-UI sources.
- UI app sources are collected in `set(UI_SOURCES ...)`, including `global/global.cpp`, panels, widgets, and `main.cpp`.
- Executable target is `${AMBER_TARGET}`, normally `amber-editor`, `Amber` on Apple.
- Tests are enabled at the bottom via:
  - `enable_testing()`
  - `add_subdirectory(tests)`
- Existing tests link `amber-engine` and use `src/tests/test_ui_stubs.cpp` to satisfy UI-layer symbols.

First PR CMake shape:

```cmake
add_subdirectory(automation)

target_link_libraries(${AMBER_TARGET} PRIVATE amber-automation)
```

Inside `src/automation/CMakeLists.txt`:

```cmake
add_library(amber-automation STATIC
  automationserver.cpp automationserver.h
  jsonrpc.cpp jsonrpc.h
  commands.cpp commands.h
  serialize.cpp serialize.h
)

target_include_directories(amber-automation PUBLIC ${CMAKE_SOURCE_DIR})
target_link_libraries(amber-automation PUBLIC amber-engine Qt6::Core Qt6::Widgets)
target_compile_definitions(amber-automation PUBLIC ${AMBER_DEFINITIONS})
```

Notes:

- Keep it linked only into the app target at first. Do not force tests to link UI panels unless needed.
- If the automation library references `MainWindow` or panel globals, it is no longer a clean engine-level library.
  Keep PR 1 command handlers focused on global state and serializable project data to avoid this.
- If `Q_OBJECT` is used in automation classes, the global `CMAKE_AUTOMOC ON` already supports it.

## Startup parsing and lifecycle recommendation

Recommended PR 1 startup sequence:

1. Parse `--automation-stdio` into `bool automation_stdio`.
2. Construct `QApplication` and `MainWindow` as today.
3. Connect `MainWindow::finished_first_paint` to `AmberGlobal::finished_initialize` as today.
4. After `MainWindow` exists, create `AutomationServer` only if `automation_stdio` is true.
5. Start stdio server after first paint or after `finished_initialize` so project-on-launch has a chance to run.
6. Keep the window behavior conservative:
   - For PR 1, still call `showMaximized()` / `showFullScreen()` exactly as today.
   - Later, add `--automation-minimized` or `--automation-headless` only after testing Qt/RHI behavior.

Why after first paint: `finished_initialize()` is currently tied to `MainWindow::finished_first_paint`, and project loading
from a positional filename is deferred via `AmberGlobal::load_project_on_launch()`. Starting command handling too early
could produce inconsistent snapshots.

## Threading and command dispatch shape

Required invariant:

- Automation I/O may run on a worker thread.
- All reads and future mutations of Amber project state should run on the GUI thread.

Recommended PR 1 implementation pattern:

- `AutomationServer` owns the stdio reader/writer and protocol loop.
- For each `tools/call`, parse request on the automation thread.
- Use `QMetaObject::invokeMethod(..., Qt::BlockingQueuedConnection, ...)` to call a GUI-thread command handler for fast
  read-only commands.
- The GUI handler builds a `QJsonObject` snapshot and returns it to the automation thread.
- Long-running tasks are out of scope for PR 1; future preview/export tools should return `task_id`.

Avoid:

- Calling `amber::ActiveSequence`, `amber::project_model`, `panel_timeline`, `Clip`, `Cacher`, or QRhi objects directly
  from the stdio thread.
- Holding raw pointers across async requests.
- Returning pointers/addresses in JSON.

## Protocol surface for first PR

Use JSON-RPC 2.0 messages over stdio with MCP-style framing. Prefer `Content-Length: <n>\r\n\r\n<json>` framing because
it matches common MCP/LSP stdio clients better than newline-delimited JSON.

Minimum methods:

### `initialize`

Response should include:

- protocol/version string,
- app name/version if available,
- capability summary,
- tool count.

### `tools/list`

Return tool descriptors for:

- `inspect_project`
- `list_sequences`
- `get_active_sequence`
- `inspect_timeline`

### `tools/call`

Dispatch by tool name. Unknown tool returns a structured JSON-RPC error.

### `inspect_project`

Return:

- `project_file`
- `modified`
- `has_active_sequence`
- media root summary if safe
- sequence count if available

### `list_sequences`

Return:

- sequence id or stable index for this process,
- name,
- width/height,
- frame rate,
- duration/end frame,
- track limits.

### `get_active_sequence`

Return either `null` plus reason, or active sequence summary.

### `inspect_timeline`

Input:

- optional sequence id/index; default active sequence.

Return:

- sequence summary,
- clips array with timeline range, source range, track, media name/path if available, linked ids if safe,
- markers/guides if straightforward.

## Smoke test shape

Add a smoke script that validates the protocol without relying on media files:

1. Build Amber.
2. Launch:

   ```bash
   ./build/amber-editor --automation-stdio --no-debug --rhi-backend opengl
   ```

3. Send `initialize`.
4. Send `tools/list`.
5. Send `tools/call` for `inspect_project`.
6. Assert:
   - process responds with valid JSON-RPC,
   - `tools/list` includes the four read-only tools,
   - `inspect_project` returns `has_active_sequence: false` or a valid active sequence object,
   - no stderr fatal error,
   - process exits when stdin closes or when a future `shutdown` method is called.

Suggested command:

```bash
python3 scripts/automation_smoke.py --amber ./build/amber-editor
```

For PR 1, this can be a manually run smoke script rather than a CI-gated test if the GUI/RHI environment is not reliable
in GitHub Actions. The script should be deterministic enough for later CI once an offscreen/headless mode exists.

## Automated tests to include in first PR

Existing test system verified:

- `src/tests/CMakeLists.txt`
- Qt Test targets:
  - `amber-tests`
  - `amber-test-path`
  - `amber-test-audio`
  - `amber-test-headers`
  - `amber-engine-tests`
  - `amber-test-srt`
  - `amber-test-effects`
  - `amber-test-effect-xml-parse`
  - `amber-test-projectio`
  - `amber-test-rhi-smoke`
  - `amber-test-rendering`
- `src/tests/test_ui_stubs.cpp` supplies UI-layer stub symbols for headless engine tests.

Recommended first PR tests:

- Unit-test `jsonrpc` parsing/framing without launching Qt UI.
- Unit-test command dispatch error behavior:
  - invalid JSON,
  - missing method,
  - unknown method,
  - unknown tool,
  - malformed params.
- Do not unit-test `main.cpp` parser by including `main.cpp` in tests. If parser coverage is desired, extract argument
  parsing to a tiny `startup_options.{h,cpp}` in a later cleanup or include a black-box smoke check for `--help`.

Validation commands:

```bash
cmake -S src -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
ctest --test-dir build --output-on-failure
python3 scripts/automation_smoke.py --amber ./build/amber-editor
./build/amber-editor --help | rg -- '--automation-stdio'
```

For this assessment-only document, I did not run these build/test commands.

## CI assessment

Verified workflows:

- `.github/workflows/build.yml`
  - manual/release packaging workflow,
  - builds AppImage via Docker,
  - cross-builds Windows installer via Docker,
  - builds macOS bundles on macOS runners.
- `.github/workflows/preview.yml`
  - currently triggers only on pushes to `2.0.x`,
  - only builds when commit message contains `[preview]`,
  - moves the `v2.0.0-preview` tag and updates prerelease artifacts.

CI gap for automation PRs:

- No PR workflow currently runs `cmake --build` + `ctest` on pull requests.
- `preview.yml` does not run for `2.0.lawmight`.
- Packaging workflows are too heavy as the only validation path for a small automation PR.

Recommended CI addition, ideally in the first or immediately following PR:

- Add `.github/workflows/tests.yml` for `pull_request` and pushes to `2.0.lawmight`:
  - install Qt 6 + FFmpeg dependencies,
  - configure CMake,
  - build,
  - run `ctest --output-on-failure`.
- Do not make GUI automation smoke CI-gated until the first smoke script is proven stable locally.

If CI setup becomes too invasive due Qt 6.8+ dependency availability, keep it as a follow-up PR and document local
validation commands in `docs/automation.md`.

## Rollback strategy

PR 1 should be easy to revert:

- All new code lives under `src/automation/`.
- Startup impact is limited to one flag branch in `src/main.cpp`.
- CMake impact is limited to `add_subdirectory(automation)` and linking the automation library to `${AMBER_TARGET}`.
- No project file format changes.
- No timeline mutation behavior changes.
- No render/export changes.
- No normal launch behavior changes when `--automation-stdio` is absent.

Rollback options:

1. Disable at runtime: do not pass `--automation-stdio`.
2. Disable at build time if needed: wrap automation CMake in `option(AMBER_AUTOMATION "Build automation stdio support" ON)`.
3. Revert the PR cleanly: remove `src/automation/`, the smoke script/docs, and the small `main.cpp`/CMake hooks.

## Checklist for later Cursor agents

Before editing:

- Confirm branch is based on `2.0.lawmight`.
- Keep the work to one reviewable layer.
- Do not implement Cursor SDK inside Amber.
- Do not add HTTP before stdio works.
- Do not add headless mode in the first automation PR.

When touching startup:

- Update `print_help()`.
- Preserve positional project filename behavior in `parse_args()`.
- Verify `--help`, `--version`, and normal launch still work.
- Keep automation behind `--automation-stdio`.

When touching CMake:

- Keep automation sources separate from `amber-engine` unless they are engine-safe.
- Avoid making tests link the full UI app by accident.
- Run `cmake -S src -B build -DCMAKE_BUILD_TYPE=Release`.

When touching project/timeline state:

- Dispatch to GUI thread.
- Read snapshots on GUI thread.
- Route mutations through `ComboAction`/existing undo commands and `amber::UndoStack`.
- Never directly mutate `Clip` internals from automation code.
- Never touch `Cacher` internals or QRhi textures from automation code.

When adding tools:

- Add schema/descriptor to `tools/list`.
- Validate params and return structured JSON-RPC errors.
- Prefer stable process-local ids or explicit indexes over raw pointers.
- Add a smoke assertion for every new tool.

When adding mutation tools:

- Start with `undo`/`redo` and one small timeline mutation.
- Confirm undo/redo restores user-visible state.
- Mark project modified through the same paths existing UI commands use.
- Include rollback notes in the PR description.

When adding preview/export tools:

- Return task ids for long operations.
- Return file paths for preview images/segments, not raw media blobs.
- Keep QRhi resources owned/deleted by rendering code.
- Add timeout/cancel behavior.

## First PR definition of done

- `amber-editor` builds with automation enabled.
- `amber-editor` launches normally without `--automation-stdio`.
- `amber-editor --help` lists `--automation-stdio`.
- `amber-editor --automation-stdio` responds to `initialize`.
- `tools/list` returns the four read-only tool descriptors.
- `inspect_project` works on a fresh empty project.
- `list_sequences`, `get_active_sequence`, and `inspect_timeline` return structured empty/null states when no sequence is
  active rather than crashing.
- `ctest --test-dir build --output-on-failure` passes, or failures are documented as unrelated existing environment
  issues.
- Smoke script output is included in the PR description.
