# Tools

Every MCP tool this server exposes, grouped by domain. Each row lists
the tool name, the HTTP verb + path it wraps, and the capability scope
required to call it.

## Legend

- **Scope**: which `ROBOFLOW_MCP_MODE` lets the tool run.
  - `readonly` — readonly | curate | full
  - `curate` — curate | full
  - `full` — full only
- **Destructive** tools additionally require `confirm="yes"`.
- Every tool accepts `dry_run=True` to preview the HTTP request without
  calling the API.

## Workspace + project

| Tool | Scope | Wraps |
|---|---|---|
| `roboflow_get_workspace` | readonly | `GET /{workspace}` |
| `roboflow_list_projects` | readonly | projection of `GET /{workspace}` |
| `roboflow_get_project` | readonly | `GET /{workspace}/{project}` |

## Image search + tagging (v0.1)

| Tool | Scope | Wraps |
|---|---|---|
| `roboflow_search_images` | readonly | `POST /{ws}/{project}/search` |
| `roboflow_add_image_tags` | curate | `POST /{ws}/{project}/images/{id}/tags` (op=add) |
| `roboflow_remove_image_tags` | curate (destructive) | …(op=remove) |
| `roboflow_set_image_tags` | curate (destructive) | …(op=set) |

## Image ingestion (v0.3)

| Tool | Scope | Wraps |
|---|---|---|
| `roboflow_upload_image` | curate | `POST /dataset/{project}/upload` (multipart) |
| `roboflow_upload_images_batch` | curate | fan-out w/ concurrency=1–16 |
| `roboflow_delete_image` | curate (destructive) | `DELETE /{ws}/{project}/images/{id}` |
| `roboflow_upload_annotation` | curate | `POST /dataset/{project}/annotate/{id}` (COCO / YOLO / Pascal VOC / CreateML / Roboflow JSON) |
| `roboflow_get_image` | readonly | `GET /{ws}/{project}/images/{id}` |
| `roboflow_list_image_batches` | readonly | `GET /{ws}/{project}/batches` |

### Image source format

Every image-accepting tool takes a discriminated `source` union:

```jsonc
{"kind": "url", "url": "https://..."}
{"kind": "path", "path": "/absolute/path/img.jpg"}  // under ROBOFLOW_MCP_UPLOAD_ROOTS
{"kind": "base64", "data": "...", "filename": "img.jpg"}
```

Every mode runs through the URL / path / image guards before the HTTP
request is built. See `docs/SECURITY_MODEL.md` threats T3/T4/T8.

## Dataset versions (v0.3)

| Tool | Scope | Wraps |
|---|---|---|
| `roboflow_list_versions` | readonly | parses `versions[]` from `GET /{ws}/{project}` |
| `roboflow_get_version` | readonly | `GET /{ws}/{project}/{version}` |
| `roboflow_create_version` | full (destructive-of-quota) | `POST /{ws}/{project}/generate` (async) |
| `roboflow_get_version_generation_status` | readonly | poll `GET /{ws}/{project}/{version}` |
| `roboflow_export_version` | readonly | `GET /{ws}/{project}/{version}/{format}` |
| `roboflow_delete_version` | full (destructive) | `DELETE /{ws}/{project}/{version}` |
| `roboflow_download_export` | full (destructive-to-fs) | streams the signed zip URL to local disk |

### Supported export formats

`coco`, `yolov5`, `yolov8`, `yolov11`, `pascal-voc`, `createml`,
`tfrecord`, `multiclass`.

## Resources

| URI | Status | Description |
|---|---|---|
| `roboflow://workspace/{ws}/projects/{project}/versions/{version}` | alpha | Markdown summary of a dataset version |

## Prompts

| Name | Status | Description |
|---|---|---|
| _none yet_ | | First one lands in v0.5 (`train_model`). |

## Status legend

- **alpha**: signature or behaviour may change without notice.
- **beta**: stable signature, minor behaviour may still change.
- **stable**: covered by semver — breaking changes need a major bump.

Current default status is **alpha** until v1.0.
