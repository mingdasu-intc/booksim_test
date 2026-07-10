# ZCN 拓扑对比：6×7 vs 7×6

本文对比两种 CHI mesh 拓扑在相同仿真参数下的 SN 读写性能差异。

| 场景 | 前缀 | 报告 |
|------|------|------|
| 6×7（SN 在顶边） | `zcn_*` | [`zcn_sim_report.pdf`](zcn_sim_report.pdf) |
| 7×6（SN 在左右边中部） | `zcn_lp_*` | [`zcn_lp_sim_report.pdf`](zcn_lp_sim_report.pdf) |

---

## 1. 拓扑差异

两种拓扑节点总数相同：**42 routers × (2 RN + 2 HN) + 4 SN = 172 nodes**。

| 项目 | 6×7 (`zcn`) | 7×6 (`zcn_lp`) |
|------|-------------|----------------|
| Mesh 尺寸 | 6 行 × 7 列 | 7 行 × 6 列 |
| Router 数 | 42 | 42 |
| RN / HN / SN | 84 / 84 / 4 | 84 / 84 / 4 |
| SN 放置 | **顶边** 4 个 router | **左、右两列中部** 各 2 个 router |
| SN 坐标 (row,col) | (0,1), (0,2), (0,4), (0,5) | (3,0), (4,0), (3,5), (4,5) |
| SN router ID | R1, R2, R4, R5 | R18, R24, R23, R29 |
| SN node ID | 168–171 | 168–171 |

### 流量形态（不变）

- **读 ceiling**：100% ReadShared DMT miss → CompData **SN→RN**（4→84 fan-out）
- **写 ceiling**：100% WriteBack + L3EvictToSN → L3EvictData **HN→SN**（多→4 fan-in）

### 拓扑对路径的影响

| 路径 | 6×7 特点 | 7×6 特点 |
|------|----------|----------|
| Read (SN→RN) | 4 个 SN 挤在**同一行顶边**，出口竞争集中 | SN 分布在**左右两侧**，fan-out 更分散 |
| Write (HN→SN) | 流量汇聚到顶边 4 点 | 流量汇聚到左右边 4 点，XY 路径可能更短/更均衡 |

---

## 2. 共同仿真参数

| 参数 | 值 |
|------|-----|
| `CHI_ROUTING` | `xy` |
| `CHI_LINK_LATENCY` | `2` |
| `CHI_VC_BUF_SIZE` | `4` |
| `CHI_DATA_FLITS` | `2`（32 B/packet） |
| `CHI_NODE_NORMALIZE` | `1`（默认） |
| λ 扫描范围 | 0.005 – 0.043（密集表，27 点） |
| 延迟指标 | **Packet latency**（`atime − ctime`，含源端排队） |

---

## 3. SN 本地峰值（λ* = max SN DAT avg）

数据来源：`zcn_sn_local_peak.csv` / `zcn_lp_sn_local_peak.csv`。

| 路径 | 拓扑 | λ* | SN DAT avg | SN DAT peak | SN REQ avg | SN REQ peak | State |
|------|------|-----|------------|-------------|------------|-------------|-------|
| Read | 6×7 | 0.021 | 65.2% | 73.0% | 42.9% | 44.2% | UNSTBL |
| Read | 7×6 | 0.024 | **78.3%** | **79.3%** | **49.7%** | **51.7%** | UNSTBL |
| Write | 6×7 | 0.042 | **87.3%** | **88.8%** | **69.8%** | **71.2%** | UNSTBL |
| Write | 7×6 | 0.040 | 84.1% | 87.5% | 71.2% | 74.0% | UNSTBL |

**Write/Read SN DAT avg 比（λ*）**

| 拓扑 | 比值 |
|------|------|
| 6×7 | 1.34×（87.3% vs 65.2%） |
| 7×6 | 1.08×（84.1% vs 78.3%） |

7×6 下读/写 SN 利用率更接近，不对称性明显减小。

---

## 4. E2E ceiling 吞吐（accepted util 平台）

数据来源：`zcn_sn_read_ceiling.csv` / `zcn_lp_sn_read_ceiling.csv` 等。

### 4.1 饱和膝点（最后一个收敛点 `ok`）

| 路径 | 拓扑 | 最后 ok 的 λ | ok 时 util | 首个 UNSTBL 的 λ |
|------|------|--------------|------------|------------------|
| Read | 6×7 | 0.015 | 60.7% | 0.016 |
| Read | 7×6 | **0.018** | **72.6%** | 0.020 |
| Write | 6×7 | **0.028** | **67.3%** | 0.030 |
| Write | 7×6 | 0.025 | 59.6% | 0.026 |

### 4.2 UNSTBL 区 accepted util 平台（均值）

| 路径 | 6×7 平台 | 7×6 平台 | 变化 |
|------|----------|----------|------|
| Read E2E | ~62% | **~77%** | **+15 pp** |
| Write E2E | **~75%** | ~71% | −4 pp |

读路径 E2E 上限在 7×6 下显著提高；写路径略降，但读/写差距缩小。

### 4.3 Packet latency 拐点

| 路径 | 拓扑 | 低载 λ=0.005 | 膝点（最后 ok） | 高载 λ=0.043 |
|------|------|--------------|-----------------|--------------|
| Read | 6×7 | ~36 cyc | **146 cyc** @ λ=0.015 | ~475 cyc |
| Read | 7×6 | ~34 cyc | **49 cyc** @ λ=0.018 | ~410 cyc |
| Write | 6×7 | ~36 cyc | **51 cyc** @ λ=0.028 | ~286 cyc |
| Write | 7×6 | ~34 cyc | **64 cyc** @ λ=0.025 | ~301 cyc |

7×6 读膝点延迟更低（49 vs 146 cycle），说明 SN 注入口瓶颈缓解后，在更高 λ 下仍能保持较低排队。

---

## 5. 结论

### 读路径：7×6 明显更优

- SN DAT avg 从 65% 提升到 **78%**（+13 pp）
- E2E accepted 平台从 ~62% 提升到 **~77%**（+15 pp）
- λ* 从 0.021 提升到 0.024，饱和膝点延迟从 146 降到 **49 cycle**
- **原因**：SN 从顶边单排 fan-out 改为左右两侧分布，注入口竞争减轻，XY 路由下数据扇出更均衡

### 写路径：6×7 略优，但差距不大

- SN DAT avg：6×7 **87.3%** vs 7×6 84.1%（−3 pp）
- E2E 平台：6×7 **~75%** vs 7×6 ~71%（−4 pp）
- 写仍高于读，但 7×6 下读写比从 1.34× 缩小到 **1.08×**

### 总体建议

若设计目标是**均衡读写 SN 带宽、提高读上限**，7×6（SN 在左右边中部）更优。若写带宽是绝对瓶颈且可接受读/写不对称，6×7 顶边布局写路径略好。

---

## 6. 产物索引

### 6×7 (`zcn`)

| 文件 | 内容 |
|------|------|
| `zcn_sn_local_peak.csv` | λ* 汇总 |
| `zcn_sn_local_peak_sweep.csv` | 完整 λ 扫描 |
| `zcn_sn_read_ceiling.csv` | 读 E2E + packet latency |
| `zcn_sn_write_ceiling.csv` | 写 E2E + packet latency |
| `zcn_sim_report.pdf` | 2 页报告 |
| `stats_out/zcn/` | 归档 stats |

### 7×6 (`zcn_lp`)

| 文件 | 内容 |
|------|------|
| `zcn_lp_sn_local_peak.csv` | λ* 汇总 |
| `zcn_lp_sn_local_peak_sweep.csv` | 完整 λ 扫描 |
| `zcn_lp_sn_read_ceiling.csv` | 读 E2E + packet latency |
| `zcn_lp_sn_write_ceiling.csv` | 写 E2E + packet latency |
| `zcn_lp_sim_report.pdf` | 2 页报告 |
| `stats_out/zcn_lp/` | 归档 stats |

---

## 7. 复现命令

### 切换拓扑

```bash
cd booksim2/runfiles

# 7×6（当前默认）
CHI_ROUTING=xy CHI_LINK_LATENCY=2 python3 gen_chi_traffic.py

# 6×7（历史 zcn 拓扑）
CHI_ROWS=6 CHI_COLS=7 CHI_SN_COORDS="0,1;0,2;0,4;0,5" \
  CHI_ROUTING=xy CHI_LINK_LATENCY=2 python3 gen_chi_traffic.py
```

### 重跑扫描 + 报告

```bash
# 7×6 local peak
SWEEP_BUFS=4 CHI_DATA_FLITS=2 SWEEP_OUT=zcn_lp_sn_local_peak.csv \
  SWEEP_STATS_DIR=stats_out/zcn_lp SWEEP_LAMBDAS="0.005 ... 0.043" \
  python3 sweep_sn_local_peak.py

# 7×6 ceiling（读/写分别设置 CHI_* mix，SWEEP_OUT=zcn_lp_sn_*_ceiling.csv）
python3 sweep_sn_throughput.py

# 报告
cd ../doc && python3 zcn_lp_generate_sim_report.py   # 7×6
cd ../doc && python3 zcn_generate_sim_report.py      # 6×7（需先跑 zcn_* 扫描）
```

更完整的参数说明见 [`simulation_guide.md`](simulation_guide.md)。
