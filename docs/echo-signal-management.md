# 回波信号管理

入口：左侧「数据管理 → 回波信号」。使用当前项目的数据库和对象存储持久化，支持导入、仿真、名称查询、来源/频段筛选、分页、详情、编辑名称与备注、下载和删除。

## 二进制 dat 约定

文件头为有符号 32 位 Na（脉冲数）、Nr（每个脉冲的复采样点数），两者均大于 0。随后依次写入 Na 条脉冲，每条脉冲为 uint32 iGate 和 Nr 对交错的 uint16 I、Q。字段间没有填充字节。

```
int32 Na
int32 Nr
uint32 iGate[0], uint16 I[0,0], uint16 Q[0,0], ...
...
uint32 iGate[Na-1], uint16 I[Na-1,0], uint16 Q[Na-1,0], ...
```

精确文件长度：`8 + Na × (4 + 4 × Nr)` 字节。最大 64 MiB。截断、附加字节、非法维度和长度不匹配均被拒绝。默认小端，可在导入时选择大端；不自动猜测。

dat 本身没有频率、采样率、PRF 或偏置字段，导入时频段只能人工标注，中心频率保留未知；iGate 作为采样波门延迟个数原值保存。频段与仿真参数保存在数据库，下载 dat 后重新导入时需重新填写其频段和偏置。

I/Q 始终按 uint16 原值保存。偏置 32768 用于偏置二进制；偏置 0 用于原始无符号数。系统不将 uint16 重新解释为 int16。幅度为 `hypot(I-offset,Q-offset)`，相位为 `atan2(Q-offset,I-offset)`，单位弧度。

幅度预览最多均匀取 256 条脉冲、512 个距离点，以 `20log10(max(幅度,1))` 逐文件归一化，不能用于跨文件绝对能量比较。单脉冲曲线和采样表最多均匀取 1024 点，显示真实索引。原始 dat 不降采样。

## 四频段仿真

| 频段 | 预设中心频率 |
| --- | --- |
| C | 5.3 GHz |
| X | 9.6 GHz |
| Ku | 15 GHz |
| Ka | 35 GHz |

预设值是本项目的仿真参数，并非对某一真实雷达的标定。频段归属可参考 [NASA 雷达频段说明](https://www.nasa.gov/general/what-are-the-spectrum-band-designators-and-bandwidths/)。

模型 `baseband-lfm-three-point-targets-v2`：三个点目标的距离中心为 Nr 的 0.25、0.52、0.76 倍，幅度为 11000、8000、6000。采用有限长度余弦包络的线性调频复回波，加入二次距离迁移、目标径向速度（0.2、−0.35、0.5 m/s）及独立 I/Q 高斯噪声。中心频率 fc 参与双程传播相位 `−4πfcR/c`，因此相同种子、尺寸和场景在不同频段下也产生不同 I/Q。

固定采样率 120 MHz、调频带宽 80 MHz、PRF 2000 Hz，脉冲持续时间为 `max(4,Nr/8)/120e6` 秒。输出加 32768 偏置、四舍五入、裁剪到 [0,65535]，保存为小端 uint16。参数与随机种子入库，可复现。最多 4,194,304 个复采样点。

这是一组教学与数据管理验证信号，未模拟真实轨道、天线、散射或完整成像过程，不作为物理精度和成像算法验收数据。

界面点击「生成仿真回波」，选择频段后生成并入库；也可离线生成再导入：

```powershell
cd F:\SAR_publish\SAR_Backend
python scripts/generate_echo.py F:\SAR_desktop_packaging_workspace\artifacts\echo-Ku.dat --band Ku --na 512 --nr 1024 --seed 20261023
```

## 持久化与升级

新表 `echo_signals` 保存元数据；dat 与 PNG 位于 `echoes/<project-id>/<echo-id>/`。SQLite 桌面版启动时自动创建新表。PostgreSQL 在后端目录执行 `alembic upgrade head`，迁移为 `20261023_0007`。

新版 Electron 桌面壳将业务数据保存在软件目录下的 `data`，包含 `sar.db`、`storage` 与未完成上传分片。Windows 当前路径为 `E:\GF\Desktop\SAR Desktop\data`；Ubuntu 安装版为 `/opt/SAR Desktop/data`；Windows portable 和 Linux AppImage 使用启动文件旁的 `data`。软件目录必须可写。退出软件后复制整个程序文件夹即可在同系统迁移数据；跨系统需换用对应系统程序并复制 `data`。

首次升级时，新目录为空会从原用户目录 `sar-desktop-shell/runtime/backend/data` 复制完整数据，逐文件 SHA-256 校验后启用，保留原目录作为备份。已有目标数据库不会被覆盖。日志仍在用户配置目录下的 `sar-desktop-shell/logs`。Windows 新安装器在升级和卸载时保留 `data`；不要用旧安装器覆盖已迁移的数据。资源热更新不会更新 Electron 壳的数据目录逻辑，需安装新版完整安装包。Linux `/opt` 安装需管理员为使用者授予安装目录写权限，包管理器升级前请备份数据。详细路径及迁移规则见打包仓库 `docs/storage-and-package-size.md`。个人数据不提交 Git，也不进入安装包。

样本管理的本地上传同时支持 PNG、JPG/JPEG、WEBP、TIF/TIFF（含大写扩展名）。TIFF 原文件及其数值精度保留，预览单独生成 PNG；“原格式”导出返回上传原文件。样本文件位于 `data/storage/sar/samples`，回波文件位于 `data/storage/sar/echoes`，标注及管理记录位于 `data/sar.db`。

## API

路径前缀 `/api/v1/echoes`，遵循现有 X-Project-Id 项目选择机制：

| 方法 | 路径 | 功能 |
| --- | --- | --- |
| GET | 空路径 | q/source/frequency_band/limit/offset 查询，返回 data 与 total |
| POST | /upload | multipart file/name/remark/byte_order/iq_offset/frequency_band |
| POST | /simulate | JSON 仿真并入库 |
| GET | /{id} | 元数据 |
| GET | /{id}/pulse?pulse=0 | I/Q 原值、幅度、相位、iGate |
| GET | /{id}/download | 原始 dat |
| PATCH | /{id} | 编辑 name、remark |
| DELETE | /{id} | 删除元数据及文件 |

## 测试

```powershell
cd F:\SAR_publish\SAR_Backend
$env:DATABASE_URL='sqlite:///:memory:'
python -m pytest tests -o addopts= -q --disable-warnings
python -m pytest tests/test_echoes.py -o addopts= --cov=app.echo_service --cov=app.api.routes.echoes --cov=app.schemas.echoes --cov-fail-under=80
cd ..\SAR_Front
npm run build
```
