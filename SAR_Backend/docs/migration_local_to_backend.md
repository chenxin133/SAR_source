# 本地 IndexedDB → 后端化（导出/导入）

## 1. 导出（前端 local 模式）

- 确保 `VITE_STORAGE_MODE=local`
- 在“原始影像管理”页面点击“导出本地数据包”
- 生成 `sar_local_export_*.zip`

导出内容：
- `manifest.json`
- `raw_images/<id>/*`：元数据与 file/preview/thumbnail（二进制）
- `samples/<id>/*`：样本 JSON 与 image/thumbnail（二进制）
- `annotations/<id>/*`：标注 JSON

## 2. 导入（后端）

接口：
- `POST /api/v1/imports`（multipart form-data, file 为 zip）

返回：
- `202` + `{ data: { task_id } }`

导入流程：
- zip 上传至对象存储 `imports/<task_id>/package.zip`
- Worker 执行 `import_package`：
  - 为每个 local image 生成新的 UUID image_id，上传原图/预览/缩略图
  - 导入 annotations 与 samples（按 local imageId 做映射）

## 3. 导入后处理

如需重新生成后端多级 WebP，可对导入的 image 执行：
- `POST /api/v1/images/{image_id}/process`

