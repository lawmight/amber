# Amber automation MCP/API assessment

This assessment is a corrective second pass revised from the full
`amber-agent-context.md` supplied for the Amber 2.0.lawmight automation plan. The
previous MCP/API assessment did not receive that full local context; this
document treats the supplied context as source material and grounds the proposed
API against symbols verified in this checkout.

No production code is proposed here. The recommendation remains: expose Amber as
a deterministic local editing tool surface first, and run the Cursor SDK agent as
an external orchestration process.

## Verified local seams

The following files and symbols were inspected locally and should shape the
automation API:

- `src/main.cpp`
  - `parse_args`, `handle_flag`, and `main` define the current launch path.
  - Current flags include `--rhi-backend`, `--disable-shaders`,
    `--no-debug`, `--disable-blend-modes`, and `--translation`; there is no
    automation flag today.
  - `main` constructs `QApplication`, `MainWindow`, RHI setup, and enters
    `a.exec()`. An automation mode should not change normal launch behavior.
- `src/global/global.h`
  - `AmberGlobal` owns app-level actions and project lifecycle slots.
  - Verified slots/methods include `undo`, `redo`, `new_project`,
    `OpenProject`, `ImportProject`, `save_project_as`, `save_project`,
    `open_export_dialog`, `clear_undo_stack`, `finished_initialize`, and
    `set_sequence(SequencePtr s, bool record_history = false)`.
- `src/core/appcontext.h` and `src/ui/appcontextimpl.cpp`
  - `AppContext` is an existing UI/engine seam.
  - Verified methods useful for automation include `listAllSequences()` and
    `processFileList(QStringList& files, bool recursive, MediaPtr replace,
    Media* parent)`.
  - `AppContextImpl::listAllSequences` delegates to
    `panel_project->list_all_project_sequences()`.
  - `AppContextImpl::processFileList` delegates to
    `panel_project->process_file_list(...)`.
- `src/project/projectmodel.h` and `src/project/media.h`
  - `amber::project_model` is the global project tree model.
  - `Media` exposes `get_type`, `get_name`, `to_footage`, `to_sequence`,
    `childCount`, `child`, `temp_id`, and marker access.
  - `MediaType` values are `MEDIA_TYPE_FOOTAGE`, `MEDIA_TYPE_SEQUENCE`, and
    `MEDIA_TYPE_FOLDER`.
- `src/panels/project.h` and `src/panels/project.cpp`
  - `create_sequence_from_media(QVector<amber::timeline::MediaImportData>&)`
    builds `Sequence` settings from imported media or config defaults.
  - `Project::create_sequence_internal(ComboAction*, SequencePtr, bool open,
    Media* parent)`, `Project::process_file_list`, `Project::save_project`,
    and `Project::list_all_project_sequences` are relevant seams.
- `src/engine/sequence.h`
  - `Sequence` is a plain C++ object, not a `QObject`.
  - Verified state includes `name`, `width`, `height`, `frame_rate`,
    `audio_frequency`, `audio_layout`, `playhead`, `workarea_*`, `save_id`,
    `markers`, `guides`, `selections`, and `QVector<ClipPtr> clips`.
- `src/engine/clip.h`
  - `Clip` owns timeline state, `effects`, links, transitions, a private
    `Cacher`, and QRhi texture/resource fields.
  - Safe movement API exists as
    `Clip::move(ComboAction*, long iin, long iout, long iclip_in, int itrack,
    bool verify_transitions = true, bool relative = false)`.
  - Rendering-sensitive members include `Cacher`, `QRhiTexture*` fields, and
    `NeedsCpuRgba()` / `NeedsCacherReconfigure()`.
- `src/panels/timeline.h`
  - Existing timeline verbs include `ripple_clips`, `split_clip`,
    `split_selection`, `split_all_clips_at_point`, `split_clip_and_relink`,
    `delete_areas_and_relink`, `create_ghosts_from_media`,
    `add_clips_from_ghosts`, `ripple_delete`, `ripple_to_in_point`,
    `edit_to_in_point`, `three_point_insert`, and `three_point_overwrite`.
- `src/effects/effect.h` and `src/effects/effect.cpp`
  - Verified symbols include `EffectMeta`, global `effects`,
    `get_meta_from_name`, `Effect::Create`, `Effect::GetInternalMeta`,
    `Effect::save_to_string`, `Effect::load_from_string`, and
    `VideoEffectFlags` including `ImageFlag`.
- `src/engine/undo/comboaction.h` and `src/engine/undo/undostack.h`
  - `ComboAction` groups multiple `QUndoCommand`s into one undoable user
    action.
  - `amber::UndoStack` is the global `QUndoStack`.
- `src/rendering/renderthread.h`
  - `RenderThread::start_render(Sequence* s, int playback_speed, const QString&
    save = nullptr, void* pixels = nullptr, int pixel_linesize = 0,
    int idivider = 0, bool scrubbing = false)` can back preview-frame
    rendering.
  - `RenderThread::DeferRhiResourceDeletion` confirms QRhi resource deletion
    must remain render-thread aware.
- `src/rendering/exportthread.h`
  - `ExportThread` is a `QThread` with `ExportParams`, progress signals,
    `Interrupt`, and internal `RenderThread` usage; automation export should be
    async.
- `src/CMakeLists.txt`
  - Sources are grouped as `amber-engine` object sources plus UI sources.
    A future `src/automation/` module can be added without reworking the engine.

## Architectural conclusion

The correct first API is a local stdio JSON-RPC 2.0 server that speaks MCP
methods. It should be launched by an external process with:

```bash
amber --automation-stdio
```

The process trust model is "trusted parent launched this local Amber instance."
That matches MCP stdio clients, avoids a listening port, avoids DNS rebinding and
local-network exposure, and lets Cursor SDK remain outside Amber. HTTP JSON-RPC
can be added later if remote operation is explicitly needed.

Automation should be implemented as a narrow adapter, not a rewrite:

```text
src/automation/
  CMakeLists.txt
  automationserver.h/.cpp   # stdio reader/writer thread and lifecycle
  jsonrpc.h/.cpp            # JSON-RPC 2.0 envelopes and validation
  commands.h/.cpp           # command registry and GUI-thread dispatch
  serialize.h/.cpp          # Project/Media/Sequence/Clip/Effect JSON snapshots
  mcp_tools.h/.cpp          # initialize, tools/list, tools/call adapters
```

All project reads and writes should execute on the GUI thread. Fast commands can
use `QMetaObject::invokeMethod(..., Qt::BlockingQueuedConnection, ...)` from the
automation thread into a GUI-thread command object. Long-running jobs should
return immediately with a `task_id` and report status by polling and later MCP
notifications.

## Stable ID strategy

Amber has save-time IDs (`Sequence::save_id`, `Footage::save_id` in project save
paths, and `Media::temp_id`) but they are not enough for a live automation API:
some are assigned during save, some are temporary, and clips do not expose a
stable public ID. The API should introduce an automation ID registry that maps
live C++ objects to stable session IDs without changing project serialization in
the MVP.

Recommended ID forms:

```text
project:current
media:<uuid-or-session-counter>
sequence:<uuid-or-session-counter>
clip:<sequence-id>:<session-counter>
effect:<clip-id>:<effect-id-or-index>
marker:<sequence-id>:<index-or-session-counter>
task:<uuid>
```

Properties:

- IDs are opaque strings to clients.
- IDs are stable for the life of the Amber process.
- Save/load persistence can come later by adding explicit automation metadata to
  `.ove` only after compatibility is designed.
- Response objects may include legacy fields like `save_id`, `media_type`, or
  clip indexes for debugging, but clients must not use those as primary IDs.
- Clip IDs should survive timeline movement and trimming. If a clip is split,
  the pre-split clip keeps its ID and the post-split clip receives a new ID.
- If an undo deletes and then redo restores an object, the registry should reuse
  the previous ID when the same shared object instance is restored; if that is
  not practical initially, responses must include `invalidated_ids`.

## JSON conventions

### Core scalar conventions

- Frames are integer timeline frames in the sequence frame rate.
- Time values may also be accepted as seconds when explicitly named `_seconds`,
  but the canonical mutation surface should use frames.
- File paths are absolute local paths unless a tool explicitly documents
  project-relative behavior.
- Track indexes match Amber's internal convention: video/audio distinction should
  be explicit in the API even if internal `Clip::track()` is a signed/int track.
- Effects are referred to by stable `effect_id` plus optional human-readable
  `effect_name`.

### Snapshot schema outline

```json
{
  "project": {
    "id": "project:current",
    "path": "/home/user/project.ove",
    "modified": true
  },
  "media": [
    {
      "id": "media:1",
      "type": "footage",
      "name": "interview.mp4",
      "path": "/home/user/interview.mp4",
      "ready": true,
      "streams": [
        {
          "index": 0,
          "kind": "video",
          "width": 1920,
          "height": 1080,
          "frame_rate": 29.97,
          "duration_frames": 17982
        }
      ]
    }
  ],
  "sequences": [
    {
      "id": "sequence:1",
      "name": "Sequence 01",
      "width": 1920,
      "height": 1080,
      "frame_rate": 29.97,
      "audio_frequency": 48000,
      "playhead": 0,
      "workarea": null
    }
  ],
  "active_sequence_id": "sequence:1"
}
```

### Timeline schema outline

```json
{
  "sequence": {
    "id": "sequence:1",
    "name": "Sequence 01",
    "frame_rate": 29.97,
    "duration_frames": 1800,
    "tracks": [
      { "kind": "video", "index": 0 },
      { "kind": "audio", "index": 0 }
    ],
    "clips": [
      {
        "id": "clip:sequence:1:4",
        "name": "interview.mp4",
        "media_id": "media:1",
        "media_stream": 0,
        "track": { "kind": "video", "index": 0 },
        "timeline_in": 0,
        "timeline_out": 300,
        "source_in": 150,
        "duration": 300,
        "enabled": true,
        "linked_clip_ids": ["clip:sequence:1:5"],
        "effects": [
          {
            "id": "effect:clip:sequence:1:4:0",
            "name": "Transform",
            "type": "video",
            "enabled": true,
            "flags": ["shader", "coords"]
          }
        ]
      }
    ],
    "markers": [],
    "guides": []
  }
}
```

## MCP framing

Amber should speak JSON-RPC 2.0 over stdio with MCP method names. Each message is
one JSON-RPC object framed using MCP's standard stream framing. The server should
support at least:

- `initialize`
- `tools/list`
- `tools/call`
- optionally `notifications/initialized`
- later `notifications/progress` and `notifications/resources/updated`

### `initialize` request

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {
      "name": "cursor-sdk-amber-agent",
      "version": "0.1.0"
    }
  }
}
```

### `initialize` response

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {
        "listChanged": false
      }
    },
    "serverInfo": {
      "name": "amber",
      "version": "2.0.lawmight"
    }
  }
}
```

### `tools/list` response excerpt

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "inspect_project",
        "description": "Return project, media-bin, sequence, and active-sequence metadata.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "include_media": { "type": "boolean", "default": true },
            "include_sequences": { "type": "boolean", "default": true }
          },
          "additionalProperties": false
        }
      },
      {
        "name": "move_clip",
        "description": "Move or trim a clip through the undo system.",
        "inputSchema": {
          "type": "object",
          "required": ["clip_id", "timeline_in", "timeline_out", "track"],
          "properties": {
            "clip_id": { "type": "string" },
            "timeline_in": { "type": "integer", "minimum": 0 },
            "timeline_out": { "type": "integer", "minimum": 1 },
            "source_in": { "type": "integer", "minimum": 0 },
            "track": {
              "type": "object",
              "required": ["kind", "index"],
              "properties": {
                "kind": { "enum": ["video", "audio"] },
                "index": { "type": "integer", "minimum": 0 }
              },
              "additionalProperties": false
            },
            "ripple": { "type": "boolean", "default": false }
          },
          "additionalProperties": false
        }
      }
    ]
  }
}
```

### `tools/call` request

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "inspect_timeline",
    "arguments": {
      "sequence_id": "sequence:1",
      "include_effects": true
    }
  }
}
```

### `tools/call` response

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"sequence\":{\"id\":\"sequence:1\",\"name\":\"Sequence 01\",\"clips\":[]}}"
      }
    ],
    "structuredContent": {
      "sequence": {
        "id": "sequence:1",
        "name": "Sequence 01",
        "clips": []
      }
    },
    "isError": false
  }
}
```

Use `structuredContent` for clients that support it and keep a compact JSON text
fallback for broader MCP compatibility.

## Tool set assessment

### Phase 1: read-only tools

These are the safest first tools because they only serialize GUI-thread state:

| Tool | Verified backing structures | Notes |
| --- | --- | --- |
| `inspect_project` | `AmberGlobal::is_modified`, `amber::project_model`, `Media` | Returns project path if exposed by `ProjectIO`/global state, modified status, media, sequences, active sequence. |
| `list_media` | `ProjectModel::child`, `Media::get_type`, `Media::get_name`, `Footage` | Include stream metadata only when `Footage` is ready. |
| `list_sequences` | `AppContext::listAllSequences`, `Media::to_sequence`, `Sequence` | Return stable sequence IDs plus dimensions/rate/duration. |
| `get_active_sequence` | `amber::ActiveSequence` usages verified across timeline/viewer code | Return null if no active sequence. |
| `inspect_timeline` | `Sequence::clips`, `Clip` getters | Main agent state snapshot. |
| `inspect_clip` | `Clip` getters and `effects` list | Include source range, linked clips, transitions, effect summaries. |
| `inspect_effects` | `Effect`, `EffectRow`, `EffectField`, `save_to_string` | Start with summary and raw serialized preset string if field introspection is not ready. |

Example `inspect_timeline` call:

```json
{
  "name": "inspect_timeline",
  "arguments": {
    "sequence_id": "sequence:1",
    "include_effects": true,
    "include_markers": true
  }
}
```

Example result:

```json
{
  "sequence": {
    "id": "sequence:1",
    "name": "Short Cut",
    "width": 1080,
    "height": 1920,
    "frame_rate": 30,
    "playhead": 0,
    "duration_frames": 900,
    "clips": [
      {
        "id": "clip:sequence:1:1",
        "media_id": "media:1",
        "track": { "kind": "video", "index": 0 },
        "timeline_in": 0,
        "timeline_out": 120,
        "source_in": 300,
        "enabled": true
      }
    ]
  }
}
```

### Phase 2: mutation tools

Mutation tools must run on the GUI thread and push `ComboAction` into
`amber::UndoStack` where an undoable edit is possible. The API should reject a
mutation if it would require direct `Clip` field writes, direct `Cacher` access,
or direct QRhi resource manipulation.

| Tool | Backing seam | Implementation constraint |
| --- | --- | --- |
| `import_media` | `AppContext::processFileList` / `Project::process_file_list` | Avoid file dialogs; return imported `media_id`s. |
| `create_sequence` | `Project::create_sequence_internal`, `create_sequence_from_media` | Use `ComboAction`; optionally set active via `AmberGlobal::set_sequence`. |
| `add_clip` | `Timeline::create_ghosts_from_media`, `Timeline::add_clips_from_ghosts`, `AddClipCommand` paths | Prefer existing ghost/import path to preserve link handling. |
| `move_clip` | `Clip::move(ComboAction*, ...)` | Do not call raw setters except inside existing undo commands. |
| `split_clip` | `Timeline::split_clip`, `split_clip_and_relink`, `split_all_clips_at_point` | Return new post-split `clip_id`. |
| `ripple_delete` | `Timeline::delete_areas_and_relink`, `ripple_clips`, `Timeline::ripple_delete` | Prefer explicit range arguments over current UI selection state. |
| `apply_effect` | `get_meta_from_name`, `Effect::Create`, `undo_effect` commands | Account for `ImageFlag`/Frei0r cacher reconfigure risk. |
| `set_effect_param` | `EffectRow` / `EffectField` and undo effect commands | Needs field schema discovery before broad exposure. |
| `set_keyframe` | `EffectField` keyframe structures | Should be deferred until effect-field schemas are robust. |
| `undo` / `redo` | `AmberGlobal::undo`, `AmberGlobal::redo`, `amber::UndoStack` | Return changed/unchanged state and invalidated IDs. |
| `save_project` | `AmberGlobal::save_project` | For unsaved projects, require explicit `path` to avoid modal save dialog. |

Example `move_clip` call:

```json
{
  "name": "move_clip",
  "arguments": {
    "clip_id": "clip:sequence:1:1",
    "timeline_in": 60,
    "timeline_out": 180,
    "source_in": 300,
    "track": { "kind": "video", "index": 0 },
    "ripple": false
  }
}
```

Example result:

```json
{
  "clip": {
    "id": "clip:sequence:1:1",
    "timeline_in": 60,
    "timeline_out": 180,
    "source_in": 300,
    "track": { "kind": "video", "index": 0 }
  },
  "undo": {
    "pushed": true,
    "label": "Move Clip"
  },
  "invalidated_ids": []
}
```

### Phase 3: preview and export tools

Preview and export are important for an agentic loop but higher risk than
read-only inspection.

| Tool | Backing seam | Recommended behavior |
| --- | --- | --- |
| `render_preview_frame` | `RenderThread::start_render` | Return a PNG/JPEG path, frame number, dimensions, and task or synchronous completion. Keep all QRhi ownership on render thread. |
| `start_export_task` | `ExportThread`, `ExportParams` | Return `task_id` immediately. Emit/poll progress. |
| `get_task_status` | automation task registry | Return `queued`, `running`, `succeeded`, `failed`, or `cancelled`. |
| `cancel_task` | `ExportThread::Interrupt`, `RenderThread::cancel` where appropriate | Must be idempotent. |
| `export_sequence` | wrapper around async export | May block only if a timeout is specified and short enough. |

Example preview call:

```json
{
  "name": "render_preview_frame",
  "arguments": {
    "sequence_id": "sequence:1",
    "frame": 90,
    "output_path": "/tmp/amber-previews/frame-000090.png",
    "scale": 0.5,
    "timeout_ms": 10000
  }
}
```

Example preview result:

```json
{
  "preview": {
    "path": "/tmp/amber-previews/frame-000090.png",
    "sequence_id": "sequence:1",
    "frame": 90,
    "width": 960,
    "height": 540,
    "format": "png"
  }
}
```

## Error handling

Use JSON-RPC errors for protocol-level failures and MCP tool results with
`isError: true` for tool-level failures.

Recommended JSON-RPC error codes:

| Code | Name | Meaning |
| --- | --- | --- |
| `-32700` | Parse error | Invalid JSON/framing. |
| `-32600` | Invalid request | Not a JSON-RPC 2.0 request. |
| `-32601` | Method not found | Unsupported MCP method. |
| `-32602` | Invalid params | Params fail schema validation. |
| `-32603` | Internal error | Unhandled Amber/server failure. |
| `-32001` | Tool not found | `tools/call` references unknown tool. |
| `-32002` | Tool validation failed | Tool arguments fail schema or semantic validation. |
| `-32003` | Project state conflict | Missing active sequence, stale ID, media not ready, or edit conflict. |
| `-32004` | Operation rejected | Unsafe operation, unsupported direct mutation, or modal UI required. |
| `-32005` | Timeout | GUI-thread command or render/export exceeded timeout. |
| `-32006` | Task not found | Unknown `task_id`. |

Tool error response example:

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "No active sequence. Create or open a sequence before calling add_clip."
      }
    ],
    "structuredContent": {
      "error": {
        "code": "NO_ACTIVE_SEQUENCE",
        "message": "No active sequence. Create or open a sequence before calling add_clip.",
        "recoverable": true,
        "details": {
          "suggested_tools": ["list_sequences", "create_sequence"]
        }
      }
    },
    "isError": true
  }
}
```

Validation rules should be strict:

- Reject unknown properties in tool arguments.
- Reject negative frames and zero/negative durations.
- Reject stale IDs.
- Reject media paths outside allowed roots if sandboxing is configured.
- Reject save/export paths that overwrite existing files unless
  `overwrite: true` is explicit.
- Reject operations that would show modal dialogs in automation mode.
- Return clear recovery hints for agent planning.

## Threading and state safety

The source confirms that Amber is not designed for arbitrary background mutation:

- `Sequence` is a plain object with public vectors and fields.
- `Clip` owns a private `Cacher`, atomics, mutexes, and QRhi resource pointers.
- `RenderThread` and `ExportThread` own worker-thread render/export lifecycles.
- UI panels use globals such as `amber::ActiveSequence`, `panel_project`, and
  `panel_timeline`.

Therefore:

1. The automation stdio reader/writer may live on its own `QThread`.
2. It may parse JSON off the GUI thread.
3. It must dispatch all project snapshots and mutations to a GUI-thread command
   handler.
4. The GUI-thread handler must build snapshots or `ComboAction`s and return
   value JSON, not raw pointers.
5. It must never directly touch `Clip::Cacher`, `QRhiTexture*`, or render
   resources.
6. QRhi resource deletion should remain on the render path via existing
   `RenderThread::DeferRhiResourceDeletion`.
7. Export/preview commands should use task indirection rather than blocking the
   agent indefinitely.

## Stdio viability

Stdio is viable for the MVP because:

- The launch path is centralized in `src/main.cpp`; adding
  `--automation-stdio` is straightforward and can preserve normal UI launch.
- MCP stdio avoids binding a localhost port.
- The parent process model is a reasonable trust boundary for a local editor.
- JSON payload sizes for timeline state are manageable for early projects.
- Binary preview data does not need to cross stdio; tools can return file paths.

Stdio limitations:

- A crashed Amber process terminates the tool connection.
- Large timeline snapshots may become expensive; add pagination or
  `include_*` flags before projects grow.
- Progress notifications over stdio need careful framing and flushing.
- The server must not write arbitrary logs to stdout in automation mode. Logs
  should go to stderr or Amber's internal logger; stdout must be protocol-only.

## External Cursor SDK launch/connect design

The Cursor SDK agent should remain outside Amber:

```text
Cursor SDK runner
  launches: amber --automation-stdio <optional project.ove>
  connects: MCP stdio transport
  calls: inspect/list/mutate/render tools
  invokes: sidecar perception tools as separate processes
  evaluates: preview frames or segments
  iterates: undo/redo or project snapshots
```

Recommended runner responsibilities:

- Launch Amber with a known working directory and environment.
- Capture stderr logs separately from MCP stdout.
- Wait for `initialize` and `tools/list`.
- Load media and sidecar analysis outputs such as ffprobe, Whisper, scene
  detection, silence detection, OCR, and CLIP/image embeddings.
- Keep its own edit plan and reasoning outside Amber.
- Call Amber tools for deterministic edits.
- Request preview images or segments and use a vision/perception evaluator.
- Save or export only after validation.

Amber should not know about Cursor-specific model APIs. It should expose a
general local MCP server that Cursor SDK, Claude Desktop, test scripts, or other
agents can drive.

## Security and trust boundaries

MVP trust boundary:

- The MCP client is trusted because it launched Amber as a child process or was
  launched by the same user session.
- The file system is not fully trusted: media paths, project paths, and export
  paths must still be validated.
- Media content is untrusted: FFmpeg parsing and effect loading already carry
  normal media-editor risk, so automation should not widen the attack surface.

Required safety rules:

- No TCP listener in the MVP.
- No unauthenticated HTTP control API in the MVP.
- No shell execution tool inside Amber.
- No arbitrary scripting language embedded into Amber for the first phase.
- No direct `.ove` XML editing through the automation API.
- No direct pointer/object address exposure in responses.
- No stdout logging in automation mode.
- File operations should support allowlists or workspace roots once the runner
  design matures.
- Add explicit `overwrite` fields for destructive save/export operations.
- Keep imported media and output previews on local paths; do not fetch remote
  URLs in Amber itself.

If HTTP is added later, it should require an explicit flag, random loopback bind
token, origin checks, no external interface by default, and a clear warning in
the UI.

## Prior art influence

The prior art listed in the full context should influence the API shape, but not
push Amber toward speculative implementation:

- `burningion/video-editing-mcp`
  - Borrow MCP shape, resource-style IDs/URIs, preview resources, and defensive
    polling for long-running video operations.
- `samuelgursky/davinci-resolve-mcp`
  - Use a mature NLE split between granular timeline tools and later compound
    workflow tools.
- OpenTimelineIO
  - Borrow vocabulary and semantics for insert, overwrite, trim, slice, slip,
    slide, ripple, roll, fill, and remove. This reduces ambiguity for agents and
    future interoperability.
- OpenShot
  - Its `UpdateAction` command bus with `type`, `key`, `values`, `old_values`,
    and transaction concepts is a useful model for a future internal command IR,
    especially if Amber later adds watchers or collaborative state updates.
- Kdenlive
  - Keep heavyweight AI/perception helpers as sidecars. Amber can exchange JSON
    with Python tools without embedding a scripting runtime.
- MLT
  - Treat headless/automation as a serious engine contract, but do not attempt
    to turn Amber into MLT in the first PR.
- MoviePy
  - A fluent high-level SDK can be layered above MCP later; keep the Amber tool
    surface lower-level and deterministic.
- CapCut/Jianying draft APIs
  - Useful for social-video workflow schemas and compound tools, but their
    draft-file mutation approach is fragile and should not drive Amber's MVP
    because Amber can mutate real in-memory editor structures safely through
    undo commands.

## Deferred tools

These should not be in the first implementation despite being important later:

- `create_rough_cut_from_transcript`
- `make_short_variant`
- `remove_silence`
- `add_caption_style`
- `apply_reference_style`
- `generate_preview_pack`
- OTIO import/export
- transcript alignment and caption generation
- audio beat detection
- scene/shot detection
- face/object-aware reframing
- multi-agent critique loops
- remote HTTP control
- persistent automation IDs in `.ove`
- direct effect-field editing for every effect type
- headless mode

Reason: the local code has enough seams for read-only state and safe basic
mutations, but compound editing quality depends on perception sidecars, preview
evaluation, and a stable primitive tool layer.

## Key risks

1. **GUI-thread violations**
   - Risk: automation mutates `Sequence::clips` or `Clip` fields from the stdio
     thread.
   - Mitigation: one GUI-thread command handler; all reads/writes go through it.

2. **Undo bypass**
   - Risk: agent edits cannot be undone by users.
   - Mitigation: mutations build `ComboAction`s and push to `amber::UndoStack`.

3. **Clip/Cacher/QRhi ownership bugs**
   - Risk: preview or effect tools touch render resources from the wrong thread.
   - Mitigation: never expose those internals; use `RenderThread::start_render`
     and existing deferred deletion paths.

4. **Modal UI deadlocks**
   - Risk: tools call save/open/import paths that show dialogs while the MCP
     client waits.
   - Mitigation: automation variants require explicit paths and reject modal
     flows.

5. **Unstable IDs**
   - Risk: clients act on stale clip indexes after edits.
   - Mitigation: opaque automation IDs and `invalidated_ids` in mutation
     responses.

6. **Oversized snapshots**
   - Risk: large projects produce huge JSON responses over stdio.
   - Mitigation: `include_*` flags, pagination, and per-resource inspection.

7. **Effect schema complexity**
   - Risk: exposing every effect parameter too early creates invalid states.
   - Mitigation: start with effect summaries and preset serialization; add typed
     field schemas incrementally.

8. **Automation logs corrupt protocol**
   - Risk: debug output on stdout breaks MCP framing.
   - Mitigation: automation mode routes logs to stderr/internal log only.

9. **Normal launch regression**
   - Risk: adding automation changes desktop startup.
   - Mitigation: `--automation-stdio` must be opt-in and tests should verify
     regular `amber --help` and normal argument parsing still work.

## Recommended first implementation slice

The first production PR should be deliberately narrow:

1. Add `--automation-stdio` flag in `src/main.cpp`.
2. Add `src/automation/` with JSON-RPC/MCP framing.
3. Implement `initialize`, `tools/list`, and `tools/call`.
4. Implement four read-only tools:
   - `inspect_project`
   - `list_media`
   - `list_sequences`
   - `inspect_timeline`
5. Implement two safe mutation tools:
   - `undo`
   - `redo`
6. Add one non-modal mutation only if the undo path is proven:
   - either `save_project` with explicit path semantics, or `create_sequence`
     through `Project::create_sequence_internal`.
7. Add a smoke test or script that launches Amber in automation mode, calls
   `inspect_project`, calls one mutation, and verifies a valid JSON-RPC
   response.

This slice demonstrates the architecture without risking render internals,
effect-field complexity, or timeline-edit semantics before the server contract is
stable.
