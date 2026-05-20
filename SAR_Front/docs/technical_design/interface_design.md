# 接口设计文档

## 1. 前端组件接口 (Vue Component)

### 1.1 组件名称：`<TiffThumbnail>`

用于在前端直接根据File对象生成并展示TIFF缩略图。

#### Props

| 属性名 | 类型 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- | :--- |
| `file` | `File` | 是 | - | 用户选择的TIFF文件对象 |
| `maxSize` | `number` | 否 | `256` | 生成缩略图的最大边长 (px) |
| `quality` | `number` | 否 | `0.8` | JPEG/WebP 压缩质量 (0-1) |
| `fallbackSrc` | `string` | 否 | `'/assets/default-tiff.png'` | 加载失败或处理中的占位图 |
| `useWorker` | `boolean` | 否 | `true` | 是否启用Web Worker多线程处理 |

#### Events

| 事件名 | 参数 | 说明 |
| :--- | :--- | :--- |
| `load` | `(blob: Blob)` | 缩略图生成成功，返回Blob对象 |
| `error` | `(error: Error)` | 生成失败，返回错误信息 |
| `progress` | `(percent: number)` | 处理进度 (0-100) |

#### Methods (Exposed)

| 方法名 | 参数 | 说明 |
| :--- | :--- | :--- |
| `generate()` | - | 手动触发重新生成 |
| `clearCache()` | - | 清除IndexedDB中该文件的缓存 |

## 2. 后端API接口 (FastAPI)

### 2.1 基础信息

*   **Base URL**: `/api/v1/tiff`
*   **认证方式**: Bearer Token (JWT)

### 2.2 接口列表

#### 2.2.1 上传并创建压缩任务

*   **Endpoint**: `POST /upload`
*   **Content-Type**: `multipart/form-data`
*   **参数**:
    *   `file`: (File) TIFF文件
    *   `options`: (JSON String, Optional) 压缩参数 `{ "quality": 80, "width": 512, "format": "webp" }`
*   **响应 (202 Accepted)**:
    ```json
    {
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "pending",
      "message": "File uploaded, compression task started."
    }
    ```

#### 2.2.2 查询任务状态

*   **Endpoint**: `GET /tasks/{task_id}`
*   **响应 (200 OK)**:
    ```json
    {
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "processing", // pending, processing, completed, failed
      "progress": 45, // 百分比
      "result_url": null,
      "error": null
    }
    ```
    *   **完成状态 (completed)**:
        ```json
        {
          "task_id": "...",
          "status": "completed",
          "progress": 100,
          "result_url": "https://cdn.example.com/thumbnails/550e8400.webp",
          "original_size": 104857600,
          "compressed_size": 52428,
          "compression_ratio": "0.05%"
        }
        ```

#### 2.2.3 批量查询状态

*   **Endpoint**: `POST /tasks/batch`
*   **Body**: `["task_id_1", "task_id_2"]`
*   **响应**: `[{ "task_id": "...", "status": "..." }]`

#### 2.2.4 WebSocket 实时进度推送

*   **Endpoint**: `WS /ws/tasks/{client_id}`
*   **消息格式**:
    ```json
    {
      "type": "task_update",
      "task_id": "...",
      "status": "processing",
      "progress": 70
    }
    ```

## 3. 存储结构 (Redis / IndexedDB)

### 3.1 前端 IndexedDB (Database: `SAR_TiffCache`)

*   **Store**: `thumbnails`
*   **Key**: `file_hash` (MD5 of first 1KB + file size + lastModified)
*   **Value**: `{ blob: Blob, timestamp: number, params: { width, quality } }`

### 3.2 后端 Redis

*   **Key**: `task:{task_id}`
*   **Value**: JSON String (Task Info)
*   **TTL**: 24小时
