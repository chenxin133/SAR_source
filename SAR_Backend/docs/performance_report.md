# 性能压测报告（模板）

## 1. 版本信息

- 代码版本：________
- 后端镜像：________
- 数据库：PostgreSQL 16
- Redis：7.x
- 对象存储：MinIO

## 2. 测试目标与指标

- API 延迟：P95/P99（ms）
- 错误率：< 1%
- 吞吐：QPS
- 任务处理：
  - 缩略图生成成功率
  - 单任务耗时分布（P95/P99）

## 3. 测试环境

- CPU：________
- 内存：________
- 磁盘：________
- 网络：________

## 4. 测试方法

### 4.1 Locust（API 压测）

目录：`SAR_Backend/perf/locustfile.py`

运行示例：

```bash
pip install -r SAR_Backend/perf/requirements.txt
locust -f SAR_Backend/perf/locustfile.py --host http://localhost:8000
```

### 4.2 任务压测（缩略图生成）

- 数据集：small/medium/large/huge GeoTIFF/InSAR
- 并发：worker `-c N`，同时提交 M 个 `process` 任务
- 采集指标：任务耗时、失败率、重试次数、队列积压

## 5. 结果记录

### 5.1 API

| 场景 | 并发用户 | RPS | P50 | P95 | P99 | 错误率 |
|---|---:|---:|---:|---:|---:|---:|
| list images |  |  |  |  |  |  |
| healthz |  |  |  |  |  |  |

### 5.2 任务处理

| 文件 | 大小 | 输出缩略图级别 | 平均耗时 | P95 | 失败率 | 重试率 |
|---|---:|---|---:|---:|---:|---:|
|  |  |  |  |  |  |  |

## 6. 结论与改进项

- 结论：________
- 风险：________
- 改进：________

