# Amber MCP/JSON-RPC API Assessment

This report assesses a first automation API for Amber 2.0.lawmight from the MCP, JSON-RPC 2.0, API-contract, and
agent-workflow angle. It is grounded in the current Amber structures and recommends a deterministic stdio transport
where Amber exposes editing tools and an external agent, such as a Cursor SDK process, performs planning, critique, and
iteration. It does not propose embedding a model in Amber for the first implementation.

## Verified repository structures

The current codebase has the right internal concepts for an automation layer, but it does not yet have stable runtime
object IDs suitable for an external API. Important verified symbols:

- Project tree:
  - `amber::project_model` in `src/project/projectmodel.h`.
  - `ProjectModel` stores a tree of `Media` items and exposes Qt model operations such as `appendChild`,
    `moveChild`, `removeChild`, `get_root`, and `getItem`.
  - `Media` in `src/project/media.h` wraps one of `Footage`, `Sequence`, or folder via `MediaType`.
  - `Media::temp_id` and `Media::temp_id2` are temporary folder/load IDs, not durable public IDs.
- Media:
  - `Footage` in `src/project/footage.h` stores `url`, `name`, `length`, `video_tracks`, `audio_tracks`,
    `markers`, proxy fields, in/out points, and `save_id`.
  - `FootageStream::file_index` is the persisted stream ID written as `<video id=...>` / `<audio id=...>`.
- Timeline:
  - `amber::ActiveSequence` is declared in `src/engine/sequence_fwd.h`.
  - `Sequence` in `src/engine/sequence.h` stores `name`, dimensions, frame rate, audio settings, `playhead`,
    work area, `save_id`, `markers`, `guides`, and `QVector<ClipPtr> clips`.
  - There is no separate `Track` object in the current core. Tracks are derived from each `Clip::track()`.
  - `Sequence::getTrackLimits` in `src/engine/sequence.cpp` derives video/audio limits from clip tracks.
- Clips:
  - `Clip` in `src/engine/clip.h` stores `Sequence* sequence`, media pointer/stream, timing (`clip_in`,
    `timeline_in`, `timeline_out`), `track`, `effects`, `linked`, transitions, markers, speed, reverse,
    autoscale, and `load_id`.
  - `Clip::load_id` is a load-time XML reference helper, not a durable public ID.
- Effects:
  - `EffectMeta`, `Effect`, and effect type/internal enums are in `src/effects/effect.h`.
  - `Effect::save` in `src/effects/effect.cpp` writes effect identity as `name = meta->category + "/" + meta->name`
    and writes `enabled`, rows, fields, and keyframes.
  - `EffectField` in `src/effects/effectfield.h` has stable `id()` values used for project load/save and GLSL
    uniforms. It exposes `persistent_data_` and `QVector<EffectKeyframe> keyframes`.
  - `EffectRow` in `src/effects/effectrow.h` groups fields; keyframing is row-level, so setting one field can imply
    row keyframing state.
  - `EffectKeyframe` in `src/core/keyframe.h` stores `type`, `time`, `data`, and bezier handles.
- Save/load ID behavior:
  - `save_sequence_clips` in `src/panels/project.cpp` writes `<clip id="j">`, where `j` is the current index in
    `Sequence::clips`.
  - `save_clip_media_attributes` writes footage references as `media=<Footage::save_id>` and `stream=<file_index>`,
    and nested sequences as `sequence=<Sequence::save_id>`.
  - `save_footage_or_sequence_item` assigns `Footage::save_id` and `Sequence::save_id` during save traversal.
  - `LoadThread::parse_clip` in `src/project/loadthread.cpp` reads `clip/@id` into `Clip::load_id`, then appends the
    clip to the sequence.
  - `LoadThread::correct_clip_links` rewrites `Clip::linked` from `load_id` values to current clip indices.
  - `LoadThread::load_effect` and helpers load effect names, enabled state, row fields, and transition sharing.
- Undo/edit hooks:
  - `amber::UndoStack` is declared in `src/engine/undo/undostack.h`.
  - `AddClipCommand`, `MoveClipAction`, `DeleteClipAction`, `LinkCommand`, etc. are in
    `src/engine/undo/undo_clip.h`.
  - `AddEffectCommand`, `SetEffectData`, `SetIsKeyframing`, `KeyframeAdd`, `KeyframeDataChange`, etc. are in
    `src/engine/undo/undo_effect.h`.
- Preview/export:
  - `RenderThread::start_render`, `get_frame_data`, and `cancel` are in `src/rendering/renderthread.h`.
  - `ExportParams`, `VideoCodecParams`, and `ExportThread` are in `src/rendering/exportthread.h`.
  - `ExportDialog` in `src/dialogs/exportdialog.cpp` builds export params from the active sequence.
- Application/event loop:
  - `main.cpp` constructs `QApplication`, `MainWindow`, and enters `a.exec()`.
  - Command-line parsing currently handles UI/runtime flags but no automation/stdio mode.

## Recommended first-PR scope

The first PR should establish a small, deterministic, read-mostly MCP server with one or two low-risk mutations. It
should prove transport, schemas, stable handles, main-thread dispatch, structured errors, and render-preview plumbing
before exposing broad editing operations.

### Include in the first PR

1. Transport and protocol:
   - `--automation-stdio` command-line flag.
   - JSON-RPC 2.0 over stdio with newline-delimited JSON messages.
   - MCP-compatible `initialize`, `tools/list`, and `tools/call`.
   - A single server-owned request dispatcher that marshals all Amber state access to the Qt GUI thread.
2. Stable public handle model:
   - Server session handle map for `project`, `media`, `sequence`, `clip`, `effect`, and `task`.
   - Public IDs are opaque strings, not pointers, Qt model indices, or raw vector indices.
   - IDs remain valid while the object exists; if an edit removes/replaces an object, the ID becomes stale and
     operations return a typed stale-handle error.
3. Read-only tools:
   - `inspect_project`
   - `list_sequences`
   - `list_media`
   - `get_active_sequence`
   - `inspect_timeline`
   - `inspect_clip`
   - `inspect_effects`
4. Low-risk mutations:
   - `undo`
   - `redo`
   - `save_project`
5. Preview:
   - `render_preview_frame` for a single frame to a server-created PNG/JPG file path.
   - It may be implemented synchronously at first if dispatched safely and bounded by timeout/cancellation.

### Defer from the first PR

Defer these until the handle system and read-only inspection are stable:

- `import_media`: media analysis, missing-file handling, relative paths, proxy/thumbnail generation, and UI model
  insertion have several user-visible edge cases.
- `create_sequence`: doable, but it should wait until project-bin handle semantics are settled.
- `add_clip`, `move_clip`, `split_clip`, `ripple_delete`: these must integrate with `UndoStack`, link correction,
  transitions, overlap rules, and timeline ripple behavior.
- `add_text`, `add_subtitle`: text/subtitle effects are likely implemented as internal effects, but need schema
  decisions for style, duration, and SRT import behavior.
- `apply_effect`, `set_effect_param`, `set_keyframe`: effect field types are stable, but row-level keyframing and
  value conversion need careful validation.
- `export_sequence`, `start_export_task`, `get_task_status`, `cancel_task`: async task lifecycle needs a generic task
  registry first.
- Low-res MP4 segment previews: useful for critique loops, but not needed for the first transport/API contract.

## Identity and handle design

### Problem

Current internal IDs are insufficient as API handles:

- `Footage::save_id` and `Sequence::save_id` are persisted in `.ove`, but assigned during save traversal and can be
  reused or shift if the project structure changes.
- `Clip::load_id` is the XML clip ID read from project files and is converted to current vector indices for links. It
  is not stable after timeline edits.
- `Sequence::clips` vector indices are unstable after add/delete/reorder operations.
- `Media*`, `Sequence*`, `Clip*`, `Effect*`, `QModelIndex`, and `std::shared_ptr` addresses must never cross the API
  boundary.
- Effect instance identity is not saved as a stable instance ID. The saved identity is effect type/name plus ordering
  in a clip's `effects` list.

### Recommendation

The automation server should mint opaque session IDs and maintain an internal handle registry:

```json
{
  "id": "clip_01J7P6P7ZC3WH3M1CM8EGXGZ9D",
  "kind": "clip",
  "generation": 12
}
```

The public string can be compact, e.g. `clip_01...`, while the server stores:

```cpp
struct AutomationHandle {
  AutomationKind kind;
  quint64 generation;
  QPointer<QObject> qobject;      // only for QObject-backed objects, where available
  std::weak_ptr<void> shared;     // for SequencePtr/ClipPtr/MediaPtr when available
  void* raw;                      // private fallback, never serialized
  QString fingerprint;            // used to diagnose stale handles
};
```

For non-`QObject` objects such as `Sequence` and `Clip`, prefer storing `std::weak_ptr` where reachable:

- `Sequence` should be tracked from its `SequencePtr` in `Media::to_sequence()` or `amber::ActiveSequence`.
- `Clip` should be tracked from the `ClipPtr` inside `Sequence::clips`.
- `Media` should ideally be tracked through `MediaPtr` when traversing the `ProjectModel` tree. If the current model
  API only exposes raw `Media*` in some places, the automation server can recover a shared pointer with
  `Media::get_shared_ptr(Media*)`.

Each request should resolve handles by:

1. Kind match.
2. Object still alive.
3. Object still belongs to the current project generation.
4. Optional containment check, e.g. `clip_id` belongs to `sequence_id`.

If any check fails, return `AMBER_STALE_HANDLE` or `AMBER_NOT_FOUND`.

### Stable fingerprints for diagnostics, not identity

For human-readable output and stale-handle diagnostics, include a `fingerprint` object in read responses:

```json
{
  "clip_id": "clip_01J7P6P7ZC3WH3M1CM8EGXGZ9D",
  "fingerprint": {
    "sequence_save_id": 3,
    "clip_index_at_snapshot": 14,
    "timeline_in": 240,
    "timeline_out": 360,
    "track": -1,
    "name": "A-roll closeup"
  }
}
```

Clients must not send fingerprints as IDs. They are only for debugging, logging, and recovery suggestions.

### Suggested public ID prefixes

| Kind | Prefix | Backing object |
| --- | --- | --- |
| Project session | `project_` | Current process/project generation |
| Media item | `media_` | `Media` node |
| Sequence | `seq_` | `SequencePtr` |
| Clip | `clip_` | `ClipPtr` |
| Effect instance | `effect_` | `EffectPtr` found under a `Clip` |
| Effect field | no global ID | Referenced by `effect_id` + `field_id` |
| Task | `task_` | Automation task registry entry |

Do not expose `Footage::save_id`, `Sequence::save_id`, `Clip::load_id`, `Effect::id`, vector indices, or raw pointers as
primary IDs. It is acceptable to include save/index values as metadata fields.

## Common schema conventions

### Time representation

Amber's timeline code uses integer frames for clip and sequence positions. The API should use frames as canonical
inputs and outputs, with optional seconds/timecode metadata for clients:

```json
{
  "frame": 240,
  "seconds": 10.0,
  "timecode": "00:00:10:00",
  "frame_rate": 24.0
}
```

Rules:

- All mutations that affect timeline positions should accept `frame` integers.
- `seconds` and `timecode` may be accepted later, but only if converted to frames using the target sequence frame rate
  and echoed back.
- Effect keyframes should use clip-local frame positions, matching the saved `<key frame=...>` behavior in
  `Effect::save`.

### Track representation

Current tracks are integer values on clips:

- Video tracks are negative in current timeline conventions.
- Audio tracks are zero or positive.

Represent both the raw Amber track and a friendlier normalized descriptor:

```json
{
  "track": {
    "amber_index": -1,
    "kind": "video",
    "number": 1
  }
}
```

The first PR can accept and return `amber_index` only. The normalized `kind`/`number` fields are useful for agents and
should be included in inspection responses.

### Path representation

Return both absolute and project-relative paths when available:

```json
{
  "source_path": "/home/user/media/interview.mov",
  "project_relative_path": "../media/interview.mov"
}
```

For local security, first-PR mutations that create files should write only to:

- A user-provided output path after explicit validation, or
- An Amber-owned automation artifact directory.

Preview output should default to an Amber-created temporary artifact path and return that path.

### Effect parameter values

Use typed JSON values instead of project XML strings:

```json
{
  "field_id": "opacity",
  "type": "double",
  "value": 0.75,
  "keyframes": [
    {
      "frame": 0,
      "type": "linear",
      "value": 0.0
    },
    {
      "frame": 24,
      "type": "linear",
      "value": 1.0
    }
  ]
}
```

Internally, values can still round-trip through each `EffectField`'s conversion methods where needed. For the API
contract, exposing the XML string format as the primary interface would make agents brittle.

## MCP / JSON-RPC method framing

Use JSON-RPC 2.0 requests/responses over stdio. The simplest first implementation is newline-delimited JSON, one
request or response per line. Avoid logging to stdout in automation mode; route logs to stderr or Amber's debug log.

### initialize

Request:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-03-26",
    "clientInfo": {
      "name": "cursor-sdk-agent",
      "version": "0.1.0"
    },
    "capabilities": {
      "tools": {}
    }
  }
}
```

Response:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-03-26",
    "serverInfo": {
      "name": "amber",
      "version": "2.0.lawmight"
    },
    "capabilities": {
      "tools": {
        "listChanged": false
      }
    },
    "automation": {
      "transport": "stdio",
      "project_generation": 1,
      "mutations_enabled": true
    }
  }
}
```

The server should accept `notifications/initialized` and ignore it if no setup is needed:

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized",
  "params": {}
}
```

### tools/list

Request:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

Response, abbreviated:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "inspect_project",
        "description": "Return project metadata, active sequence, media counts, sequence summaries, and capabilities.",
        "inputSchema": {
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "include_media": { "type": "boolean", "default": false },
            "include_sequences": { "type": "boolean", "default": true }
          }
        }
      },
      {
        "name": "inspect_timeline",
        "description": "Return tracks, clips, effects, markers, guides, and render settings for a sequence.",
        "inputSchema": {
          "type": "object",
          "required": ["sequence_id"],
          "additionalProperties": false,
          "properties": {
            "sequence_id": { "type": "string" },
            "include_effects": { "type": "boolean", "default": true },
            "include_keyframes": { "type": "boolean", "default": true }
          }
        }
      }
    ]
  }
}
```

### tools/call

Request:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_active_sequence",
    "arguments": {}
  }
}
```

Response:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"sequence_id\":\"seq_01J7P6V7K7M8K5V5GJ2SQMK3VK\",\"name\":\"Main\",\"frame_rate\":24.0}"
      }
    ],
    "structuredContent": {
      "sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK",
      "name": "Main",
      "frame_rate": 24.0
    },
    "isError": false
  }
}
```

For MCP clients that prefer structured tool output, `structuredContent` should be the authoritative payload. The text
content can contain compact JSON for compatibility with clients that only display `content`.

## First-PR tool schemas and examples

### inspect_project

Purpose: high-level project snapshot.

Input:

```json
{
  "include_media": true,
  "include_sequences": true
}
```

Output:

```json
{
  "project": {
    "project_id": "project_01J7P6NEQZZ8F4CDJ7Y7VE5S3E",
    "filename": "/home/user/projects/edit.ove",
    "modified": true,
    "generation": 1,
    "active_sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK"
  },
  "capabilities": {
    "mutations": ["undo", "redo", "save_project"],
    "preview": ["render_preview_frame"],
    "deferred": ["add_clip", "move_clip", "split_clip", "ripple_delete", "export_sequence"]
  },
  "counts": {
    "media": 12,
    "sequences": 2,
    "folders": 3
  },
  "sequences": [
    {
      "sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK",
      "name": "Main",
      "save_id": 1,
      "width": 1920,
      "height": 1080,
      "frame_rate": 24.0,
      "clip_count": 18,
      "duration_frames": 3456
    }
  ],
  "media": [
    {
      "media_id": "media_01J7P6W1GQC40QFHS8CP16GH8G",
      "type": "footage",
      "name": "interview.mov",
      "save_id": 4,
      "source_path": "/home/user/media/interview.mov"
    }
  ]
}
```

Notes:

- `save_id` is metadata only.
- `generation` increments when a project is cleared/reloaded.

### list_sequences

Input:

```json
{}
```

Output:

```json
{
  "sequences": [
    {
      "sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK",
      "name": "Main",
      "save_id": 1,
      "active": true,
      "settings": {
        "width": 1920,
        "height": 1080,
        "frame_rate": 24.0,
        "audio_frequency": 48000,
        "audio_layout": 3
      },
      "workarea": {
        "enabled": false,
        "in": 0,
        "out": 0
      },
      "duration_frames": 3456,
      "clip_count": 18
    }
  ]
}
```

### list_media

Input:

```json
{
  "include_streams": true,
  "include_folders": true
}
```

Output:

```json
{
  "media": [
    {
      "media_id": "media_01J7P6W1GQC40QFHS8CP16GH8G",
      "type": "footage",
      "name": "interview.mov",
      "save_id": 4,
      "folder_id": "media_01J7P6ZCWQHWR0NYZVJ4B3T84H",
      "source_path": "/home/user/media/interview.mov",
      "duration_timebase": 180000000,
      "ready": true,
      "invalid": false,
      "streams": [
        {
          "stream_id": 0,
          "kind": "video",
          "width": 1920,
          "height": 1080,
          "frame_rate": 24.0,
          "infinite_length": false
        },
        {
          "stream_id": 1,
          "kind": "audio",
          "channels": 2,
          "layout": 3,
          "frequency": 48000
        }
      ]
    },
    {
      "media_id": "media_01J7P6ZCWQHWR0NYZVJ4B3T84H",
      "type": "folder",
      "name": "Sources",
      "children": ["media_01J7P6W1GQC40QFHS8CP16GH8G"]
    }
  ]
}
```

### get_active_sequence

Input:

```json
{}
```

Output when a sequence is active:

```json
{
  "sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK",
  "name": "Main",
  "playhead": {
    "frame": 240,
    "seconds": 10.0,
    "timecode": "00:00:10:00",
    "frame_rate": 24.0
  }
}
```

Output should be a typed error when no sequence is active, not a null success:

```json
{
  "code": "AMBER_NO_ACTIVE_SEQUENCE",
  "message": "No active sequence is selected."
}
```

### inspect_timeline

Input:

```json
{
  "sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK",
  "include_effects": true,
  "include_keyframes": true
}
```

Output:

```json
{
  "sequence": {
    "sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK",
    "name": "Main",
    "save_id": 1,
    "settings": {
      "width": 1920,
      "height": 1080,
      "frame_rate": 24.0,
      "audio_frequency": 48000,
      "audio_layout": 3
    },
    "playhead_frame": 240,
    "duration_frames": 3456,
    "workarea": {
      "enabled": false,
      "in": 0,
      "out": 0
    }
  },
  "tracks": [
    {
      "amber_index": -1,
      "kind": "video",
      "number": 1,
      "clip_ids": ["clip_01J7P71GHFDMVA85W35WK3MXJ1"]
    },
    {
      "amber_index": 0,
      "kind": "audio",
      "number": 1,
      "clip_ids": ["clip_01J7P724S6BDWPM8G7EF5SXH6A"]
    }
  ],
  "clips": [
    {
      "clip_id": "clip_01J7P71GHFDMVA85W35WK3MXJ1",
      "name": "A-roll closeup",
      "enabled": true,
      "track": {
        "amber_index": -1,
        "kind": "video",
        "number": 1
      },
      "timeline": {
        "in": 240,
        "out": 360,
        "duration": 120
      },
      "source": {
        "media_id": "media_01J7P6W1GQC40QFHS8CP16GH8G",
        "stream_id": 0,
        "clip_in": 48,
        "source_path": "/home/user/media/interview.mov"
      },
      "speed": {
        "value": 1.0,
        "maintain_audio_pitch": false,
        "reverse": false
      },
      "linked_clip_ids": ["clip_01J7P724S6BDWPM8G7EF5SXH6A"],
      "effect_ids": ["effect_01J7P78G6PY6V1F2NB8X3EQPSE"],
      "fingerprint": {
        "clip_index_at_snapshot": 0,
        "load_id": 0
      }
    }
  ],
  "markers": [
    {
      "frame": 240,
      "name": "Good take",
      "comment": "",
      "color": "#ffcc00"
    }
  ],
  "guides": [
    {
      "orientation": "vertical",
      "position": 0.5,
      "mirror": true
    }
  ],
  "subtitles": [],
  "render": {
    "preview_resolution_divider": 1
  }
}
```

`subtitles` should be empty in the first PR unless a reliable subtitle representation is implemented. Later, subtitles
can be synthesized from clips with `EFFECT_INTERNAL_SUBTITLE` / subtitle effect metadata after verifying how subtitle
effects store cues.

### inspect_clip

Input:

```json
{
  "clip_id": "clip_01J7P71GHFDMVA85W35WK3MXJ1",
  "include_effects": true
}
```

Output:

```json
{
  "clip": {
    "clip_id": "clip_01J7P71GHFDMVA85W35WK3MXJ1",
    "sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK",
    "name": "A-roll closeup",
    "enabled": true,
    "timeline_in": 240,
    "timeline_out": 360,
    "clip_in": 48,
    "track": -1,
    "media_id": "media_01J7P6W1GQC40QFHS8CP16GH8G",
    "media_stream_id": 0,
    "linked_clip_ids": ["clip_01J7P724S6BDWPM8G7EF5SXH6A"],
    "markers": [],
    "effects": [
      {
        "effect_id": "effect_01J7P78G6PY6V1F2NB8X3EQPSE",
        "name": "Transform",
        "qualified_name": "Internal/Transform",
        "enabled": true
      }
    ]
  }
}
```

### inspect_effects

Input:

```json
{
  "clip_id": "clip_01J7P71GHFDMVA85W35WK3MXJ1",
  "include_keyframes": true
}
```

Output:

```json
{
  "clip_id": "clip_01J7P71GHFDMVA85W35WK3MXJ1",
  "effects": [
    {
      "effect_id": "effect_01J7P78G6PY6V1F2NB8X3EQPSE",
      "name": "Transform",
      "qualified_name": "Internal/Transform",
      "category": "Internal",
      "type": "effect",
      "internal": 0,
      "enabled": true,
      "rows": [
        {
          "name": "Position",
          "keyframing": false,
          "keyframable": true,
          "fields": [
            {
              "field_id": "x",
              "type": "double",
              "value": 0.0,
              "default": 0.0,
              "enabled": true,
              "keyframes": []
            },
            {
              "field_id": "y",
              "type": "double",
              "value": 0.0,
              "default": 0.0,
              "enabled": true,
              "keyframes": []
            }
          ]
        }
      ]
    }
  ]
}
```

### undo

Input:

```json
{}
```

Output:

```json
{
  "ok": true,
  "undo_available": true,
  "redo_available": true,
  "project_modified": true
}
```

If no undo is available, return a success with `ok: false` only if the operation is idempotent by design, or return
`AMBER_UNDO_UNAVAILABLE`. Prefer a typed error so agents can branch explicitly.

### redo

Same as `undo`, using `amber::UndoStack.canRedo()` and `amber::UndoStack.redo()`.

### save_project

Input:

```json
{
  "path": "/home/user/projects/edit.ove"
}
```

Output:

```json
{
  "ok": true,
  "filename": "/home/user/projects/edit.ove",
  "project_modified": false
}
```

First-PR recommendation:

- If `path` is omitted and the project has an existing `amber::ActiveProjectFilename`, save in place.
- If `path` is omitted and the project is unsaved, return `AMBER_PATH_REQUIRED`.
- Do not show a save dialog in automation mode.
- If `path` is supplied, set the project filename and save without UI prompts.

### render_preview_frame

Input:

```json
{
  "sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK",
  "frame": 240,
  "format": "png",
  "scale": {
    "mode": "fit_width",
    "width": 960
  }
}
```

Output:

```json
{
  "frame": {
    "frame": 240,
    "seconds": 10.0,
    "timecode": "00:00:10:00",
    "frame_rate": 24.0
  },
  "image": {
    "path": "/tmp/amber-automation/session_01J7P6/preview_0000000240.png",
    "format": "png",
    "width": 960,
    "height": 540
  },
  "sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK"
}
```

Implementation constraints:

- Dispatch to the main/GUI thread for sequence playhead state changes if needed.
- Use `RenderThread` safely; do not call rendering internals from the stdio reader thread.
- Bound the request with a timeout and return `AMBER_RENDER_TIMEOUT` if rendering does not complete.
- Avoid changing the user's visible playhead if possible. If current rendering requires setting playhead, restore it
  before returning.

## Deferred mutation schemas

These tools are important for the overall vision but should be second-phase or later.

### import_media

Input:

```json
{
  "paths": ["/home/user/media/interview.mov"],
  "folder_id": "media_01J7P6ZCWQHWR0NYZVJ4B3T84H"
}
```

Output:

```json
{
  "imported": [
    {
      "media_id": "media_01J7P6W1GQC40QFHS8CP16GH8G",
      "name": "interview.mov",
      "source_path": "/home/user/media/interview.mov",
      "ready": true
    }
  ],
  "failed": []
}
```

Risk: media analysis may be async and existing import pathways may show dialogs or rely on panel code.

### create_sequence

Input:

```json
{
  "name": "Main",
  "width": 1920,
  "height": 1080,
  "frame_rate": 24.0,
  "audio_frequency": 48000,
  "audio_layout": 3,
  "folder_id": null,
  "make_active": true
}
```

Output:

```json
{
  "sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK",
  "name": "Main"
}
```

Risk: must use existing undo/project model conventions instead of directly appending in ways the UI will not notice.

### add_clip

Input:

```json
{
  "sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK",
  "media_id": "media_01J7P6W1GQC40QFHS8CP16GH8G",
  "stream_id": 0,
  "timeline_in": 240,
  "duration": 120,
  "source_in": 48,
  "track": -1,
  "link_group": "auto"
}
```

Output:

```json
{
  "clip_id": "clip_01J7P71GHFDMVA85W35WK3MXJ1",
  "linked_clip_ids": ["clip_01J7P724S6BDWPM8G7EF5SXH6A"]
}
```

Risk: audio/video linked clip creation, collision behavior, and transition preservation must match UI semantics.

### move_clip

Input:

```json
{
  "clip_id": "clip_01J7P71GHFDMVA85W35WK3MXJ1",
  "timeline_in": 480,
  "track": -2,
  "mode": "overwrite",
  "move_linked": true
}
```

Output:

```json
{
  "clip_id": "clip_01J7P71GHFDMVA85W35WK3MXJ1",
  "timeline_in": 480,
  "timeline_out": 600,
  "track": -2
}
```

Risk: must use `MoveClipAction` / `Clip::move` through `ComboAction`, respect snapping only if requested, and define
collision/ripple behavior explicitly.

### split_clip

Input:

```json
{
  "clip_id": "clip_01J7P71GHFDMVA85W35WK3MXJ1",
  "frame": 300,
  "split_linked": true
}
```

Output:

```json
{
  "left_clip_id": "clip_01J7P71GHFDMVA85W35WK3MXJ1",
  "right_clip_id": "clip_01J7P9V35YJH7X53BNCSBNRT0A"
}
```

Risk: current split behavior appears panel/timeline-oriented (`Timeline::split_clip_at_positions`), so the API should
wrap a command-level helper rather than duplicate UI logic.

### ripple_delete

Input:

```json
{
  "clip_id": "clip_01J7P71GHFDMVA85W35WK3MXJ1",
  "delete_linked": true
}
```

Output:

```json
{
  "deleted_clip_ids": ["clip_01J7P71GHFDMVA85W35WK3MXJ1"],
  "ripple_start": 240,
  "ripple_delta": -120
}
```

Risk: high behavioral risk. Ripple delete changes downstream timing and must match user-visible timeline semantics.

### apply_effect

Input:

```json
{
  "clip_id": "clip_01J7P71GHFDMVA85W35WK3MXJ1",
  "effect": {
    "qualified_name": "Distort/Transform"
  },
  "insert_index": null
}
```

Output:

```json
{
  "effect_id": "effect_01J7P78G6PY6V1F2NB8X3EQPSE",
  "qualified_name": "Distort/Transform"
}
```

Risk: effect lookup should use `get_meta_from_name` / `Effect::GetInternalMeta` patterns and reject ambiguous names.

### set_effect_param

Input:

```json
{
  "effect_id": "effect_01J7P78G6PY6V1F2NB8X3EQPSE",
  "field_id": "opacity",
  "value": 0.75,
  "time": {
    "mode": "persistent"
  }
}
```

Output:

```json
{
  "effect_id": "effect_01J7P78G6PY6V1F2NB8X3EQPSE",
  "field_id": "opacity",
  "value": 0.75
}
```

Risk: field validation must honor `EffectField::type()`, row keyframing state, and `ConvertStringToValue` behavior.

### set_keyframe

Input:

```json
{
  "effect_id": "effect_01J7P78G6PY6V1F2NB8X3EQPSE",
  "field_id": "opacity",
  "frame": 24,
  "value": 1.0,
  "type": "linear"
}
```

Output:

```json
{
  "effect_id": "effect_01J7P78G6PY6V1F2NB8X3EQPSE",
  "field_id": "opacity",
  "frame": 24,
  "type": "linear"
}
```

Risk: because keyframing is row-level in `EffectRow`, setting one field keyframe may need to create/update matching
keyframes across fields in the same row or explicitly document that the API only edits the named field after enabling
row keyframing.

### start_export_task / get_task_status / cancel_task

Start input:

```json
{
  "sequence_id": "seq_01J7P6V7K7M8K5V5GJ2SQMK3VK",
  "output_path": "/home/user/renders/main.mp4",
  "range": {
    "start_frame": 0,
    "end_frame": 3456
  },
  "video": {
    "enabled": true,
    "codec": "h264",
    "width": 1920,
    "height": 1080,
    "frame_rate": 24.0,
    "bitrate": 8000000
  },
  "audio": {
    "enabled": true,
    "codec": "aac",
    "sampling_rate": 48000,
    "bitrate": 192000
  }
}
```

Start output:

```json
{
  "task_id": "task_01J7PBT9D24T45BQW74EAYAXZE",
  "state": "queued"
}
```

Status output:

```json
{
  "task_id": "task_01J7PBT9D24T45BQW74EAYAXZE",
  "kind": "export",
  "state": "running",
  "progress": {
    "percent": 42,
    "remaining_ms": 120000
  },
  "output_path": "/home/user/renders/main.mp4"
}
```

Risk: `ExportThread` already emits `ProgressChanged` and supports `Interrupt`, but automation needs ownership,
lifetime, result/error retention, cancellation semantics, and prevention of concurrent conflicting exports.

## Error handling

Use JSON-RPC's standard `error` for protocol-level failures, and MCP `isError` tool results for tool execution failures.
The tool should include a stable Amber error code in structured content either way.

### JSON-RPC protocol errors

Use standard JSON-RPC codes:

| Code | Meaning |
| --- | --- |
| `-32700` | Parse error |
| `-32600` | Invalid request |
| `-32601` | Method not found |
| `-32602` | Invalid params |
| `-32603` | Internal error |

Example:

```json
{
  "jsonrpc": "2.0",
  "id": 9,
  "error": {
    "code": -32602,
    "message": "Invalid params",
    "data": {
      "code": "AMBER_SCHEMA_VALIDATION_FAILED",
      "field": "sequence_id",
      "detail": "sequence_id is required"
    }
  }
}
```

### Tool execution errors

Example stale handle error:

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Clip handle is stale. The clip may have been deleted or the project may have been reloaded."
      }
    ],
    "structuredContent": {
      "ok": false,
      "error": {
        "code": "AMBER_STALE_HANDLE",
        "message": "Clip handle is stale.",
        "handle": "clip_01J7P71GHFDMVA85W35WK3MXJ1"
      }
    },
    "isError": true
  }
}
```

Recommended Amber-specific codes:

| Code | Use |
| --- | --- |
| `AMBER_SCHEMA_VALIDATION_FAILED` | Tool arguments fail JSON schema or semantic validation |
| `AMBER_UNINITIALIZED` | Request before `initialize` |
| `AMBER_AUTOMATION_DISABLED` | Mutation attempted when automation/mutations disabled |
| `AMBER_NOT_FOUND` | Referenced object/path does not exist |
| `AMBER_STALE_HANDLE` | Handle existed but no longer resolves |
| `AMBER_KIND_MISMATCH` | Handle kind does not match requested object type |
| `AMBER_NO_ACTIVE_SEQUENCE` | No active sequence exists |
| `AMBER_INVALID_TIMELINE_RANGE` | Invalid frame/range/duration |
| `AMBER_INVALID_TRACK` | Track number is invalid for requested operation |
| `AMBER_MEDIA_NOT_READY` | Media exists but analysis/decode info is not ready |
| `AMBER_UNSUPPORTED_MEDIA_TYPE` | Tool cannot operate on footage/sequence/folder kind |
| `AMBER_EFFECT_NOT_FOUND` | Effect instance or effect metadata not found |
| `AMBER_EFFECT_FIELD_NOT_FOUND` | Field ID does not exist on effect |
| `AMBER_EFFECT_FIELD_TYPE_MISMATCH` | JSON value does not match field type |
| `AMBER_UNDO_UNAVAILABLE` | Undo requested when stack cannot undo |
| `AMBER_REDO_UNAVAILABLE` | Redo requested when stack cannot redo |
| `AMBER_PATH_REQUIRED` | Save/export needs a path |
| `AMBER_PATH_NOT_ALLOWED` | Path violates automation security policy |
| `AMBER_RENDER_FAILED` | Preview render failed |
| `AMBER_RENDER_TIMEOUT` | Preview render exceeded timeout |
| `AMBER_TASK_NOT_FOUND` | Task ID unknown |
| `AMBER_TASK_NOT_CANCELABLE` | Task cannot be canceled in current state |
| `AMBER_INTERNAL_ERROR` | Unexpected server-side failure |

All errors should include:

```json
{
  "code": "AMBER_INVALID_TIMELINE_RANGE",
  "message": "timeline_out must be greater than timeline_in.",
  "details": {
    "timeline_in": 360,
    "timeline_out": 240
  },
  "retryable": false
}
```

Avoid free-form-only errors. Agents need stable `code` values.

## Stdio viability with Qt

Stdio is viable, but only if the automation server is integrated carefully with Qt's event loop and logging.

### Recommended architecture

1. Add `--automation-stdio` to `main.cpp` argument parsing.
2. In automation mode, construct the normal `QApplication` and core objects so project, media, effects, and rendering
   remain available.
3. Start an `AutomationStdioServer` after `QApplication` is created and before or after `MainWindow` creation depending
   on the desired mode:
   - Headed mode: keep `MainWindow`; useful for a human watching agent edits.
   - Headless-ish mode: still uses `QApplication` and offscreen rendering but does not show the main window. This may
     require more RHI testing and should not be assumed in the first PR.
4. Use a dedicated reader object/thread for stdin so blocking reads never block the GUI thread.
5. Dispatch all Amber object access and mutations to the GUI/main thread using queued invocations. The worker thread
   should parse/validate JSON and wait on a future/promise for the main-thread result.
6. Write responses to stdout with a serialized writer lock.
7. Send all diagnostics to stderr or the existing debug log. In automation mode, stdout must contain protocol messages
   only.

### Qt APIs that fit

- `QSocketNotifier` on stdin can work on Unix-like systems, but a dedicated `QThread` or `std::thread` reader is more
  portable and isolates blocking reads.
- `QMetaObject::invokeMethod(..., Qt::QueuedConnection)` or a small request queue QObject can marshal work to the GUI
  thread.
- `QJsonDocument`, `QJsonObject`, and `QJsonValue` are sufficient for JSON parsing/serialization.

### Constraints

- Do not access `ProjectModel`, `Sequence::clips`, `Clip::effects`, or Qt UI objects from the stdin worker thread.
- Do not let `qDebug()` / `printf()` write to stdout in automation mode. Current `print_help` and `print_version` use
  stdout; that is fine outside automation, but automation runtime logs must avoid stdout.
- Preview rendering uses `RenderThread`, QRhi, and possibly fallback surfaces. The first implementation should test both
  visible-window and offscreen preview paths before claiming headless support.
- Long operations must not starve the GUI event loop; use async tasks for export and potentially for preview if preview
  can block on decoding.

## External Cursor SDK agent launch/connect workflow

The external agent should own planning and critique. Amber should only expose deterministic tools.

Recommended later workflow:

1. Agent launches Amber as a child process:

   ```bash
   amber --automation-stdio /path/to/project.ove
   ```

2. Agent opens stdin/stdout pipes and sends `initialize`.
3. Agent calls `tools/list` and validates required tools.
4. Agent calls `inspect_project`, `list_media`, and `inspect_timeline`.
5. Agent plans edits outside Amber.
6. Agent applies deterministic tool calls.
7. Agent calls `render_preview_frame` at representative frames.
8. Agent critiques preview images with its own model/tooling.
9. Agent iterates edits.
10. Agent saves or exports when explicitly requested by the user's workflow.

The agent should treat Amber as a stateful editor process. It should not try to edit `.ove` XML directly while Amber is
running because that bypasses undo, UI refresh, cache invalidation, and media/effect validation.

## Security and trust boundaries

Stdio is the right first transport for local automation:

- No local port.
- No DNS rebinding class of issue.
- No browser-origin ambiguity.
- Parent-process trust model: whoever launches Amber with `--automation-stdio` controls the pipes.
- Smaller attack surface than HTTP/WebSocket.
- Natural fit for MCP clients.

Still, local automation can modify projects and write files, so it needs explicit boundaries.

### Recommended first-PR security posture

- Automation is opt-in by command-line flag.
- Mutations are enabled only in automation mode.
- No network listener in the first PR.
- Do not accept commands from inherited stdin unless `--automation-stdio` is set.
- Log an obvious startup message to stderr/debug log that automation is enabled.
- All file writes must be explicit and validated:
  - `save_project` only writes the current project path or a supplied `.ove` path.
  - `render_preview_frame` defaults to an Amber-owned artifact directory.
  - `export` later should require explicit output path and refuse directories or dangerous overwrites unless
    `overwrite: true` is supplied.
- Avoid arbitrary file read tools. `list_media` may reveal source paths from the open project; that is expected.
- Do not expose environment variables, process args beyond safe metadata, or filesystem browsing as generic tools.
- Include a `readonly` option later:

  ```bash
  amber --automation-stdio --automation-readonly project.ove
  ```

- Optionally include a per-session confirmation token in `initialize` response for headed mode UI display, but do not
  overbuild auth for stdio first.

### Trust boundary statement

The stdio API trusts the parent process that launched Amber. It must not trust arbitrary JSON content to be safe:
validate all schemas, ranges, paths, object handles, and effect field types. If a future HTTP transport is added, it
must be a separate security design with explicit local auth, origin protections, CSRF/DNS-rebinding mitigations, and a
disabled-by-default listener.

## Compatibility notes

- The API should identify itself as MCP-compatible but keep Amber-specific structured payloads under tool results.
- `initialize` should include the MCP protocol version supplied by the client if supported, or return a clear protocol
  error if not.
- `tools/list` schemas should set `additionalProperties: false` to prevent silent argument typos.
- Keep `structuredContent` stable; text content is for display and compatibility.
- Version the Amber automation schema independently from the application version:

  ```json
  {
    "automation_schema_version": "0.1.0"
  }
  ```

- Include `project_generation` in inspection outputs. Project reloads should invalidate all old handles.
- Preserve `.ove` compatibility by not changing existing save XML IDs in the first PR. Public automation IDs can be
  session-only first.
- Later, if durable cross-session agent handles are required, add new saved automation UUIDs in a backward-compatible
  way rather than reusing current positional clip IDs.

## Implementation risks

### 1. Clip identity and links

Current clip XML IDs are positional (`save_sequence_clips` writes `id=j`), and `LoadThread::correct_clip_links`
converts link IDs into current indices. Any API exposing clip indices will break after delete/split/ripple operations.

Mitigation: use opaque handles and containment checks; never accept clip vector index as the public identifier.

### 2. Main-thread ownership

Qt models, UI state, and many Amber objects are not safe to mutate from a reader thread.

Mitigation: parse on a worker thread, execute all Amber state access on the GUI thread.

### 3. UI-coupled edit behavior

Some editing behavior lives in panels/widgets rather than pure engine services. For example, splitting and ripple
delete appear to route through timeline/panel code in current callers.

Mitigation: first PR avoids these mutations. Later PRs should extract command-level helpers that both UI and automation
can call.

### 4. Effect value typing

`EffectField` stores values as `QVariant`, and project XML serializes through field-specific string conversion.
Automation needs typed JSON while still honoring field conversion and row keyframing.

Mitigation: start with read-only effect inspection. Add `set_effect_param` only after mapping all field types
(`double`, `color`, `string`, `bool`, `combo`, `font`, `file`) to JSON schemas.

### 5. Preview rendering side effects

Rendering a frame may need playhead changes or clip cache activity. It can also touch QRhi resources and offscreen
surfaces.

Mitigation: first preview implementation should save/restore playhead, serialize preview requests per sequence, and
return clear timeout/failure errors.

### 6. stdout contamination

MCP over stdio requires stdout to contain protocol messages only. Existing code can print version/help and may log via
Qt or C stdio.

Mitigation: in automation mode, route diagnostics to stderr/debug log and audit new automation code for stdout writes.

### 7. Task lifecycle

Export already has `ExportThread`, progress, interruption, and error state, but no API task registry.

Mitigation: defer async export until a generic task registry exists with retained result/error, cancellation,
ownership, and cleanup semantics.

### 8. Save/project prompts

Existing user-facing save/open flows can show dialogs.

Mitigation: automation tools must use non-interactive paths. `save_project` should return `AMBER_PATH_REQUIRED` instead
of opening a dialog for unsaved projects.

## Recommended first-PR acceptance criteria

- Launching with `--automation-stdio` starts Amber without exposing any network listener.
- `initialize`, `tools/list`, and `tools/call` work over newline-delimited JSON-RPC 2.0.
- stdout contains only JSON-RPC messages in automation mode.
- `inspect_project`, `list_sequences`, `list_media`, `get_active_sequence`, `inspect_timeline`, `inspect_clip`, and
  `inspect_effects` return stable opaque handles and structured JSON.
- Handles are invalidated on project reload/clear and stale handles produce `AMBER_STALE_HANDLE`.
- `undo`, `redo`, and `save_project` are non-interactive and return structured errors.
- `render_preview_frame` writes a PNG/JPG artifact and returns frame metadata.
- All Amber object access from protocol requests happens on the Qt main thread.
- No existing `.ove` save format changes are required for the first PR.

## Bottom line

Stdio JSON-RPC framed as MCP is a good first automation transport for Amber. The main contract risk is not transport;
it is identity. The first PR should solve protocol framing, safe Qt dispatch, opaque session handles, read-only timeline
inspection, non-interactive save/undo/redo, and single-frame preview. Timeline mutations and export tasks should come
after that foundation, using the existing undo command system rather than direct vector manipulation.
