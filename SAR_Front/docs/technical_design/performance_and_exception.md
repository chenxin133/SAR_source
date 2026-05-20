# 性能测试报告与异常处理方案

## 1. 性能测试计划

### 1.1 测试环境

*   **硬件**:
    *   **CPU**: Intel Core i7 (8 cores) / AMD Ryzen 7 (16 cores)
    *   **内存**: 16GB RAM
    *   **浏览器**: Chrome 120+, Firefox 120+, Safari 17+
    *   **后端**: Python 3.11, GDAL 3.8, Pillow-SIMD 10.2
*   **数据集**:
    *   `small.tif` (10MB, 2000x2000, LZW)
    *   `medium.tif` (100MB, 10000x10000, LZW)
    *   `large.tif` (500MB, 20000x20000, JPEG)
    *   `huge.tif` (1GB+, 30000x30000, Deflate)

### 1.2 测试指标

*   **加载耗时**: 从点击文件到显示缩略图的时间 (ms)。
*   **内存峰值**: 处理过程中占用的最大内存 (MB)。
*   **压缩比**: 原始大小 / 缩略图大小。
*   **并发处理**: 同时上传5个文件时的总处理时间。

### 1.3 预期基准 (Benchmark)

| 文件大小 | 前端生成耗时 (预期) | 后端生成耗时 (预期) | 内存峰值 (前端) | 内存峰值 (后端) |
| :--- | :--- | :--- | :--- | :--- |
| **10MB** | < 500ms | < 2s (含上传) | 20MB | 50MB |
| **100MB** | < 3s | < 5s (含上传) | 150MB | 200MB |
| **500MB** | < 10s | < 15s | 400MB | 1GB |
| **1GB+** | N/A (可能崩溃) | < 30s | N/A | 2GB+ (pyvips流式) |

## 2. 异常处理方案

### 2.1 前端异常捕获与降级

#### 2.1.1 异常类型

*   `TypeError: Invalid TIFF format` (格式不支持)
*   `RangeError: Array buffer allocation failed` (内存溢出)
*   `TimeoutError` (处理超时)
*   `SecurityError` (跨域限制/CSP)

#### 2.1.2 处理策略

1.  **自动降级**: 若前端生成失败，**立即**显示占位图，并在后台发起后端生成请求。
2.  **重试机制**:
    *   Web Worker崩溃后，尝试重启一次Worker。
    *   IndexedDB写入失败（QuotaExceeded），尝试清理最旧缓存后重试。
3.  **用户反馈**:
    *   Toast提示: "预览图生成中..." -> "生成失败，已转为后台处理"。
    *   控制台日志记录详细错误堆栈。

### 2.2 后端异常处理

#### 2.2.1 异常类型

*   `UploadError`: 文件上传中断/校验失败。
*   `DecodeError`: GDAL无法读取文件。
*   `MemoryError`: 内存不足。
*   `TimeoutError`: 处理超时（默认300s）。

#### 2.2.2 处理策略 (Celery Task)

1.  **重试队列**:
    *   使用 `autoretry_for=(MemoryError, TimeoutError)`。
    *   指数退避策略: `retry_backoff=True` (例如: 1s, 2s, 4s)。
    *   最大重试次数: `max_retries=3`。
2.  **死信队列 (Dead Letter Queue)**:
    *   重试3次仍失败的任务，移入死信队列，人工排查。
    *   记录错误日志到ELK/Sentry。
3.  **资源隔离**:
    *   限制单个Worker进程的最大内存使用 (如2GB)，超出自动重启。
    *   使用Docker容器限制CPU/内存配额。

## 3. 监控告警机制

*   **前端监控**:
    *   Sentry捕获JS运行时错误。
    *   Performance API记录关键耗时指标。
*   **后端监控**:
    *   **Prometheus + Grafana**:
        *   `tiff_process_latency_seconds`: 处理耗时直方图。
        *   `tiff_process_errors_total`: 错误计数器。
        *   `queue_length`: 任务队列长度。
    *   **告警规则**:
        *   队列积压 > 100 持续 5分钟 -> 邮件/钉钉告警。
        *   错误率 > 5% -> 紧急告警。
