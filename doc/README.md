# BookSim2 CHI NoC 仿真项目说明

本文档是 **booksim2** 目录下 CHI 一致性流量仿真的总览：背景、目录结构、使用方法、配置与结果解读、代码结构。更细的操作步骤见 [`simulation_guide.md`](simulation_guide.md)。

---

## 1. 背景介绍

### 1.1 项目目标

在 [BookSim 2.0](https://github.com/booksim/booksim2) 周期精确 NoC 仿真器上，建模 **CHI 类 coherent 互联流量**，重点评估 **SN（DDR / 内存控制器）** 在读/写路径上的终端链路利用率、端到端吞吐与 packet latency，为 ZCN 等 mesh 拓扑选型提供量化依据。

BookSim 本身不提供 trace 注入；本项目通过 **合成 traffic class** 把 CHI 事务流（REQ/RSP/SNP/DAT）展开为多条 BookSim 流量类，并映射到 4 个 channel subnet（`class_subnet` patch）。

### 1.2 系统模型

| 组件 | 角色 |
|------|------|
| **RN**（Request Node） | 发起读/写/dataless/CMO 事务 |
| **HN**（Home Node） | 集成 L3，处理一致性、转发到 SN |
| **SN**（Slave Node / DDR） | 仅在 Read DMT miss、L3 异步 evict、CleanInvalid dirty writeback 等场景参与 |
| **Router mesh** | anynet 拓扑，XY 或 min 路由 |

每个 router 挂 **2 RN + 2 HN**；4 个 SN 挂在指定 router 上（拓扑可配，见 §3.2）。

### 1.3 已完成的典型场景

| 场景 | 前缀 | 拓扑 | SN 位置 | 报告 |
|------|------|------|---------|------|
| ZCN（历史） | `zcn_*` | 6×7 mesh | 顶边 R1/R2/R4/R5 | [`zcn_sim_report.pdf`](zcn_sim_report.pdf) |
| ZCN-LP（当前默认） | `zcn_lp_*` | 7×6 mesh | 左右边中部 R18/R24/R23/R29 | [`zcn_lp_sim_report.pdf`](zcn_lp_sim_report.pdf) |

两种拓扑节点数相同（172），仿真参数一致（`vc_buf=4`, `DATA_FLITS=2`, XY, `link_latency=2`）。对比见 [`zcn_topology_comparison.md`](zcn_topology_comparison.md)。

### 1.4 核心结论（摘要）

- SN 终端利用率在 wormhole + credit 流控下 **难以达到 100%**；读 ~65–78%、写 ~84–88% 为正常平台上限（详见 [`upbound_analysis.md`](upbound_analysis.md)）。
- **Packet latency**（`atime − ctime`，含源排队）随 λ 上升；**Flit latency**（仅网络传输）在读路径上可能“假性”很平。
- **UNSTBL** 表示 BookSim 窗口间吞吐/延迟未收敛，通常意味着 offered load 已超过饱和吞吐；平台 **accepted util** 才是上限证据（见 [`simulation_guide.md`](simulation_guide.md) §9）。

---

## 2. 目录结构

```
booksim2/
├── README.md                 # 上游 BookSim 简介
├── src/                      # BookSim C++ 源码（需 make 编译）
│   └── booksim               # 仿真可执行文件
├── runfiles/                 # ★ 仿真脚本与运行时配置（工作目录）
│   ├── gen_chi_traffic.py    # 生成 chi_traffic + chi_traffic_anynet
│   ├── sweep_sn_local_peak.py
│   ├── sweep_sn_throughput.py
│   ├── sweep_vc_buf.py       # vc_buf 敏感性（可选）
│   ├── analyze_bottleneck.py
│   ├── chi_traffic           # BookSim 主配置（生成物）
│   ├── chi_traffic_anynet    # mesh 拓扑（生成物）
│   ├── sn_local_stats.m      # 最近一次 per-node 统计（生成物）
│   └── archive/              # 早期 mesh/扫描脚本归档
└── doc/                      # ★ 文档、CSV 结果、报告脚本
    ├── README.md             # 本文档
    ├── simulation_guide.md   # 操作手册（参数、命令、FAQ）
    ├── upbound_analysis.md   # SN 利用率为何 <100%
    ├── zcn_topology_comparison.md
    ├── zcn_generate_sim_report.py
    ├── zcn_lp_generate_sim_report.py
    ├── zcn_* / zcn_lp_*      # CSV、PDF、PNG 产物
    ├── stats_out/            # 归档的 sn_local_stats.m
    │   ├── README.md         # .m 文件解读
    │   ├── zcn/
    │   └── zcn_lp/
    └── archive/              # v5/v6 历史报告与 CSV
```

---

## 3. 如何使用

### 3.1 前置条件

```bash
cd booksim2/runfiles
```

- 已编译 BookSim：`../src/booksim` 可执行。
- Python 3；生成 PDF 需 matplotlib。
- **所有 sweep / 单点命令默认在 `runfiles/` 下执行**（BookSim cwd = runfiles）。

编译 BookSim（若尚未编译）：

```bash
cd booksim2/src && make
```

### 3.2 数据流概览

```
gen_chi_traffic.py  ──► chi_traffic + chi_traffic_anynet
                              │
                              ▼
                    ../src/booksim chi_traffic
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
   sweep_sn_local_peak.py          sweep_sn_throughput.py
   (SN 本地 peak + stats_out)       (E2E util + packet latency)
              │                               │
              └───────────────┬───────────────┘
                              ▼
              doc/*_generate_sim_report.py  ──► PDF / PNG
```

### 3.3 单点仿真

```bash
cd booksim2/runfiles

CHI_ROUTING=xy CHI_LINK_LATENCY=2 CHI_VC_BUF_SIZE=4 CHI_DATA_FLITS=2 \
CHI_LAMBDA=0.02 \
python3 gen_chi_traffic.py

../src/booksim chi_traffic | tee booksim.log
```

### 3.4 完整扫描 + 报告（ZCN-LP 示例）

```bash
cd booksim2/runfiles

LAMS="0.005 0.01 0.015 0.016 0.018 0.02 0.021 0.022 0.024 0.028 0.03 0.035 0.04 0.043"

# 1) SN 本地峰值（报告第 2 页）
SWEEP_BUFS=4 CHI_DATA_FLITS=2 CHI_VC_BUF_SIZE=4 \
  SWEEP_LAMBDAS="$LAMS" \
  SWEEP_OUT=zcn_lp_sn_local_peak.csv \
  SWEEP_STATS_DIR=stats_out/zcn_lp \
  python3 sweep_sn_local_peak.py

# 2) 读 ceiling E2E + latency（报告第 1 页）
CHI_ROUTING=xy CHI_LINK_LATENCY=2 CHI_VC_BUF_SIZE=4 CHI_DATA_FLITS=2 \
CHI_READ_RATIO=100 CHI_WRITE_RATIO=0 CHI_DATALESS_RATIO=0 CHI_CMO_RATIO=0 \
CHI_READ_SHARED_RATIO=100 CHI_READ_DMT_MISS_RATIO=100 \
CHI_READ_L3_HIT_RATIO=0 CHI_READ_DCT_RATIO=0 \
SWEEP_OUT=zcn_lp_sn_read_ceiling.csv SWEEP_MAX_UNSTBL=999 \
SWEEP_LAMBDAS="$LAMS" \
python3 sweep_sn_throughput.py

# 3) 写 ceiling（改 mix + SWEEP_OUT=zcn_lp_sn_write_ceiling.csv）
CHI_READ_RATIO=0 CHI_WRITE_RATIO=100 \
CHI_WRITE_BACK_RATIO=100 CHI_L3_EVICT_TO_SN_RATE=1.0 \
SWEEP_OUT=zcn_lp_sn_write_ceiling.csv SWEEP_MAX_UNSTBL=999 \
SWEEP_LAMBDAS="$LAMS" \
python3 sweep_sn_throughput.py

# 4) 生成 PDF
cd ../doc && python3 zcn_lp_generate_sim_report.py
```

6×7 历史场景：将前缀改为 `zcn_*`，报告脚本用 `zcn_generate_sim_report.py`；拓扑需：

```bash
CHI_ROWS=6 CHI_COLS=7 CHI_SN_COORDS="0,1;0,2;0,4;0,5" python3 gen_chi_traffic.py
```

---

## 4. 仿真配置说明

### 4.1 拓扑（默认 7×6 ZCN-LP）

| 项 | 默认值 | 环境变量 |
|----|--------|----------|
| 行 × 列 | 7 × 6 | `CHI_ROWS`, `CHI_COLS` |
| SN 坐标 | (3,0),(4,0),(3,5),(4,5) | `CHI_SN_COORDS="3,0;4,0;3,5;4,5"` |
| 每 router | 2 RN + 2 HN | 固定 |
| SN 节点 ID | 168–171 | 由 `sn_base = routers×4` 自动分配 |

### 4.2 网络与路由器

| 变量 | ZCN 常用值 | 说明 |
|------|------------|------|
| `CHI_ROUTING` | `xy` | 维序路由 |
| `CHI_LINK_LATENCY` | `2` | router–router 链路延迟（cycle） |
| `CHI_VC_BUF_SIZE` | `4` | 每 VC buffer 深度（flit） |
| `CHI_VCS` | `2` | VC 数 |
| `CHI_DATA_FLITS` | `2` | 每条 cache line DAT = 2 flit（32 B） |
| `CHI_LATENCY_THRES` | `500` | 平均延迟超阈值则 abort |
| `CHI_MAX_SAMPLES` | `50` | 最大采样窗口数 |
| `CHI_STATS_OUT` | `sn_local_stats.m` | per-node 统计；空字符串关闭 |

分配器（写在生成的 `chi_traffic` 中）：`vc_allocator=islip`，`sw_allocator=separable_output_first(round_robin)`，`alloc_iters=1`。

### 4.3 负载与 mix

| 变量 | 默认 | 说明 |
|------|------|------|
| `CHI_LAMBDA` | `0.001` | 每 RN 事务发起率（txn/node/cycle） |
| `CHI_READ/WRITE/DATALESS/CMO_RATIO` | 55/30/10/5 | 事务大类占比（%） |
| `CHI_NODE_NORMALIZE` | `1` | 按源节点数归一化注入（**务必开启**，否则 SN 源流量低估 ~21×） |

**Ceiling mix**（扫描脚本内置或手动设置）：

- **读**：100% ReadShared + DMT miss → CompData SN→RN
- **写**：100% WriteBack + `CHI_L3_EVICT_TO_SN_RATE=1.0`

完整 `CHI_*` 列表见 `runfiles/gen_chi_traffic.py` 顶部。

### 4.4 扫描专用环境变量

| 变量 | 脚本 | 说明 |
|------|------|------|
| `SWEEP_LAMBDAS` | local_peak, throughput | λ 列表 |
| `SWEEP_OUT` | 两者 | 输出 CSV 名（写入 `doc/`） |
| `SWEEP_BUFS` | local_peak | 如 `4` 或 `2 4 8` |
| `SWEEP_STATS_DIR` | local_peak | stats 归档子目录 |
| `SWEEP_MAX_UNSTBL` | throughput | 连续 UNSTBL 点数上限（ceiling 建议 999） |

---

## 5. 结果说明

### 5.1 主要输出文件

| 文件 | 内容 |
|------|------|
| `*_sn_local_peak.csv` | 每个 mix 在扫描中 **SN DAT avg 最高** 的 λ* 及指标 |
| `*_sn_local_peak_sweep.csv` | 全部 λ 点的 SN local 指标 |
| `*_sn_read_ceiling.csv` | 读专项：E2E `read_util`、`read_plat`（packet latency） |
| `*_sn_write_ceiling.csv` | 写专项：E2E `write_util`、`write_plat` |
| `*_sim_report.pdf` | 2 页：P1 拓扑+延迟曲线，P2 SN util 柱状图+λ 扫描+汇总表 |
| `stats_out/*/*.m` | BookSim `stats_out` 原始 per-node 统计 |

### 5.2 关键指标含义

| 指标 | 含义 | 读 / 写看哪里 |
|------|------|----------------|
| **SN DAT peak / avg** | SN 终端 DAT 链路 flit/cycle（相对 1.0 = 100%） | 读：`sent_flits@SN`；写：`accepted_flits@SN` |
| **SN REQ peak / avg** | 到达 SN 的 REQ 通道 util | `accepted_flits@SN` on REQ class |
| **E2E DAT util** | 全网 DAT accepted 聚合 / 4 SN | BookSim log Overall 或 DisplayStats |
| **read_plat / write_plat** | Packet latency 加权平均 | `atime − ctime`，含源排队 |
| **state: ok / UNSTBL** | 仿真是否收敛 | ok=Overall 块；UNSTBL=最后一次 DisplayStats |

λ* 选择标准：**SN DAT avg 最大**（不是 peak，也不是 E2E）。

### 5.3 当前参考结果

**6×7（`zcn`）**

| 路径 | λ* | SN DAT avg | E2E 平台 |
|------|-----|------------|----------|
| Read | 0.021 | 65.2% | ~62% |
| Write | 0.042 | 87.3% | ~75% |

**7×6（`zcn_lp`，当前默认拓扑）**

| 路径 | λ* | SN DAT avg | E2E 平台 |
|------|-----|------------|----------|
| Read | 0.024 | 78.3% | ~77% |
| Write | 0.040 | 84.1% | ~71% |

7×6 显著改善读路径、缩小读写不对称（Write/Read DAT avg 比 1.08× vs 1.34×）。

### 5.4 延伸阅读

| 文档 | 主题 |
|------|------|
| [`simulation_guide.md`](simulation_guide.md) | 命令、参数、unstable 判定、FAQ |
| [`upbound_analysis.md`](upbound_analysis.md) | SN 利用率 <100% 的原因 |
| [`zcn_topology_comparison.md`](zcn_topology_comparison.md) | 6×7 vs 7×6 对比 |
| [`stats_out/README.md`](stats_out/README.md) | `sn_local_stats.m` 格式与 class 编号 |

---

## 6. 仿真代码结构

### 6.1 `gen_chi_traffic.py`（配置生成器）

**职责**：根据环境变量生成 BookSim 配置与 anynet 拓扑。

| 阶段 | 内容 |
|------|------|
| 拓扑 | 写 `chi_traffic_anynet`：router 连接、node 挂载、链路权重 |
| 事务展开 | 按 category → subtype → scenario 生成 CHI 消息列表 |
| Class 映射 | 每条消息 → 一个 traffic class；`class_subnet` 映射 REQ/RSP/SNP/DAT |
| 注入归一化 | `CHI_NODE_NORMALIZE`：按 `N_RN/N_source` 缩放 per-node `injection_rate` |
| 输出 | `chi_traffic`：classes、injection_rate、traffic hotspot、sim 参数 |

关键常量：`CHANNEL_SUBNET = {REQ:0, RSP:1, SNP:2, DAT:3}`；`DATA_FLITS=2`，控制 flit=1。

### 6.2 `sweep_sn_local_peak.py`（SN 本地峰值扫描）

**流程**（每个 λ × read/write mix × vc_buf）：

1. `set_chi_env()` + `regen(lam)` → 重新生成 `chi_traffic`
2. `enable_stats_out()` → 注入 `stats_out = sn_local_stats.m`
3. 运行 `booksim chi_traffic`
4. `parse_matlab_rates()` 从 `.m` 取 SN 的 sent/accepted；失败则 log fallback
5. 记录全扫描到 `*_sweep.csv`；**λ* = SN DAT avg 最大** 的点写入 `*_local_peak.csv` 并归档 stats

**内置 mix**：`READ_MIX`（读 ceiling）、`WRITE_MIX`（写 ceiling）。

### 6.3 `sweep_sn_throughput.py`（E2E 吞吐 + 延迟扫描）

**流程**（每个 λ）：

1. `regen(lam)` → 生成配置
2. 运行 BookSim，解析 log：
   - 优先 `Overall Traffic Statistics`
   - 失败则 `parse_last_display()`（UNSTBL 快照）
3. 按 class 自动识别读/写 DAT（`class_subnet` + source/dest）
4. 聚合 `read_util` / `write_util`、`read_plat` / `write_plat`（packet latency 加权）

不依赖 `stats_out`；适合 latency vs λ 曲线。

### 6.4 报告脚本

| 脚本 | 输入 | 输出 |
|------|------|------|
| `zcn_generate_sim_report.py` | `zcn_*` CSV | `zcn_sim_report.pdf` |
| `zcn_lp_generate_sim_report.py` | `zcn_lp_*` CSV | `zcn_lp_sim_report.pdf` |

P1：`draw_topology()` + read/write packet latency 曲线（ok 实线 / UNSTBL 虚线）。  
P2：λ* 柱状图、SN DAT avg vs λ、汇总表。

### 6.5 BookSim 侧（`src/`）

| 模块 | 说明 |
|------|------|
| `trafficmanager.cpp` | 注入、采样、收敛/unstable 判定、stats 输出 |
| `networks/anynet.cpp` | 从 `chi_traffic_anynet` 建 mesh |
| `booksim_config.cpp` | 默认 `sample_period=1000`、`stopping_thres=0.05`、`alloc_iters=1` 等 |

CHI 仿真依赖 **class_subnet** 相关 patch（多 subnet 路由）；配置注释中会标注 `Requires the class_subnet source patch`。

### 6.6 辅助脚本

| 脚本 | 用途 |
|------|------|
| `sweep_vc_buf.py` | 扫描多种 `vc_buf_size` |
| `analyze_bottleneck.py` | 单次 run 的 per-class / per-node 快照分析 |
| `runfiles/archive/*` | v1–v5 早期 mesh 生成与 subnet 扫描（历史参考） |

---

## 7. 文档索引

| 文档 | 用途 |
|------|------|
| **本文 `README.md`** | 项目总览 |
| [`simulation_guide.md`](simulation_guide.md) | 详细操作与 FAQ |
| [`upbound_analysis.md`](upbound_analysis.md) | SN 利用率上限分析 |
| [`zcn_topology_comparison.md`](zcn_topology_comparison.md) | 拓扑 A/B 对比 |
| [`stats_out/README.md`](stats_out/README.md) | per-node 统计文件解读 |

---

## 8. 常见问题（速查）

- **读/写 SN 流量差 20×？** → 检查 `CHI_NODE_NORMALIZE=1`。
- **CSV 只有表头？** → 高 λ abort 或 stats 未写出；看 sweep 诊断输出，或降低 λ 密度。
- **延迟曲线很平？** → 确认用的是 `read_plat`/`write_plat`（packet latency），不是 flit latency。
- **BookSim 退出码 255？** → 本仓库中 **成功运行也常返回 -1（255）**；以 log 中是否有 Overall / stats 为准，勿仅凭 exit code 判失败。

更多见 [`simulation_guide.md`](simulation_guide.md) §10。
