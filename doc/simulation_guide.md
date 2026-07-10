# BookSim CHI 仿真与报告生成指南

本文说明如何用 `booksim2/runfiles/` 下的脚本，按指定参数跑 CHI 流量仿真、做 SN 读写扫描，并生成 PDF 报告。

---

## 1. 前置条件

```bash
cd booksim2/runfiles
```

- BookSim 已编译：`booksim2/src/booksim` 可执行文件存在。
- Python 3 + matplotlib（生成报告时需要）。
- 所有命令均在 `runfiles/` 目录下执行，除非特别说明。

### 脚本关系

```
gen_chi_traffic.py          生成 chi_traffic + chi_traffic_anynet
        │
        ▼
   src/booksim chi_traffic   单次仿真
        │
        ├── sweep_sn_local_peak.py   SN 本地 inject/accept 峰值扫描
        ├── sweep_sn_throughput.py   SN 读写 E2E 吞吐扫描（可选）
        │
        ▼
doc/*_generate_*_report.py  读取 CSV → PDF/PNG 报告
```

---

## 2. 核心参数（环境变量）

所有 `CHI_*` 变量在调用 `gen_chi_traffic.py` 或扫描脚本时通过环境变量传入。扫描脚本会在每次改变 λ 时自动重新生成 `chi_traffic`。

### 2.1 网络与路由器

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHI_ROUTING` | `min` | 路由函数，常用 `xy` |
| `CHI_LINK_LATENCY` | `1` | 路由器间链路延迟（cycle），常用 `2` |
| `CHI_VC_BUF_SIZE` | `2` | 每个 VC 的 buffer 深度（flit 数） |
| `CHI_VCS` | `2` | VC 数量 |
| `CHI_DATA_FLITS` | `2` | 每个 cache line 占用的 DAT flit 数（2 = 32B/包） |
| `CHI_LATENCY_THRES` | `500` | 延迟阈值，超过则 abort |
| `CHI_MAX_SAMPLES` | `50` | 采样窗口数 |
| `CHI_STATS_OUT` | `sn_local_stats.m` | per-node 统计输出文件；设空字符串可关闭 |

### 2.2 负载与流量比例

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHI_LAMBDA` | `0.001` | 每 RN 节点的事务发起率（txn/node/cycle） |
| `CHI_READ_RATIO` | `55` | 读事务占比（%） |
| `CHI_WRITE_RATIO` | `30` | 写事务占比（%） |
| `CHI_DATALESS_RATIO` | `10` | dataless 占比（%） |
| `CHI_CMO_RATIO` | `5` | CMO 占比（%） |
| `CHI_NODE_NORMALIZE` | `1` | 按源节点数归一化注入率（RN=84, SN=4）；设 `0` 可复现旧行为 |

读/写子类型、场景比例等更多 `CHI_*` 变量见 `gen_chi_traffic.py` 顶部定义。

### 2.3 扫描脚本专用

| 变量 | 脚本 | 说明 |
|------|------|------|
| `SWEEP_LAMBDAS` | 两个 sweep | 空格或逗号分隔的 λ 列表 |
| `SWEEP_OUT` | 两个 sweep | 输出 CSV 文件名（写入 `doc/`） |
| `SWEEP_BUFS` | local_peak | 要扫描的 `vc_buf` 列表，如 `2 4 8` |
| `SWEEP_STATS_DIR` | local_peak | stats 归档子目录，如 `stats_out/zcn` |
| `SWEEP_MAX_UNSTBL` | throughput | 连续饱和/NODATA 点数上限后停止（默认 2，上限扫描建议 `5`） |

---

## 3. 单点手动仿真

适合验证某一组参数下的行为。

### 3.1 生成配置并运行

```bash
cd booksim2/runfiles

# 例：ZCN 参数，读 ceiling，λ=0.02
CHI_ROUTING=xy CHI_LINK_LATENCY=2 \
CHI_VC_BUF_SIZE=4 CHI_DATA_FLITS=2 CHI_LAMBDA=0.02 \
CHI_READ_RATIO=100 CHI_WRITE_RATIO=0 CHI_DATALESS_RATIO=0 CHI_CMO_RATIO=0 \
CHI_READ_SHARED_RATIO=100 CHI_READ_DMT_MISS_RATIO=100 \
CHI_READ_L3_HIT_RATIO=0 CHI_READ_DCT_RATIO=0 \
python3 gen_chi_traffic.py

../src/booksim chi_traffic | tee booksim.log
```

### 3.2 per-node 统计

`gen_chi_traffic.py` 默认在 `chi_traffic` 中写入 `stats_out = sn_local_stats.m;`，
直接运行 BookSim 即可得到 `runfiles/sn_local_stats.m`。关闭输出：

```bash
CHI_STATS_OUT= python3 gen_chi_traffic.py
```

解读见 [`stats_out/README.md`](stats_out/README.md)。

### 3.3 恢复默认基线

扫描脚本结束时会自动恢复；手动恢复可用：

```bash
CHI_ROUTING=xy CHI_LINK_LATENCY=2 CHI_LAMBDA=0.001 python3 gen_chi_traffic.py
```

---

## 4. SN 本地峰值扫描（推荐）

脚本：`sweep_sn_local_peak.py`

对读/写两个 ceiling mix 分别扫描多个 λ，取 **SN 本地 DAT 峰值最高** 的运行点，并归档对应的 `sn_local_stats.m`。

### 4.1 指标含义

| mix | SN DAT 指标 | 来源 |
|-----|-------------|------|
| read | `sn_dat_peak` = max `sent_flits` @ SN | SN inject（CompData SN→RN） |
| write | `sn_dat_peak` = max `accepted_flits` @ SN | SN eject（L3EvictData HN→SN） |
| 两者 | `sn_req_peak` = max `accepted_flits` @ SN on REQ | 到达 SN 的请求 |

### 4.2 基本用法

```bash
cd booksim2/runfiles

SWEEP_BUFS=4 \
CHI_DATA_FLITS=2 \
SWEEP_LAMBDAS="0.005 0.01 0.015 0.02 0.025 0.03" \
SWEEP_OUT=zcn_sn_local_peak.csv \
SWEEP_STATS_DIR=stats_out/zcn \
python3 sweep_sn_local_peak.py
```

输出：
- `doc/zcn_sn_local_peak.csv` — 每个 mix 在扫描中 **SN DAT avg 最高** 的 λ 及对应指标
- `doc/stats_out/zcn/{mix}_buf{N}_D{D}_lam{L}_sn_local_stats.m` — 原始统计

### 4.3 修改流量 mix

`sweep_sn_local_peak.py` 内置两套 mix：

- **读 ceiling**（`READ_MIX`）：100% ReadShared DMT miss
- **写 ceiling**（`WRITE_MIX`）：100% WriteBack + L3EvictToSN=100%

要改 mix，在运行前设置对应的 `CHI_*` 比例变量；脚本内的 `set_chi_env()` 会先清空所有 `CHI_*` 再注入 `BASE` + mix 环境。

---

## 5. SN E2E 吞吐扫描（可选）

脚本：`sweep_sn_throughput.py`

按 λ 扫描，记录 SN 读/写 DAT 的 **全网 E2E accepted 利用率**，以及 DAT class 按 accepted flit 加权的 **Packet latency**（CSV 列 `read_plat` / `write_plat`）。ZCN 报告第 1 页的“Latency vs offered load”曲线即取自这两个 CSV。

> Packet latency = `atime − ctime`，**包含源端注入队列的排队时间**，因此随 λ 增大而上升。BookSim 另有 Flit latency (`atime − itime`) 只计网络传输、不含源排队；早期版本用的是它，故读曲线会“假性”很平。旧 CSV 的 `read_flat`/`write_flat` 列报告仍可回退读取。

```bash
cd booksim2/runfiles

# 读 ceiling E2E 曲线
CHI_ROUTING=xy CHI_LINK_LATENCY=2 CHI_VC_BUF_SIZE=4 CHI_DATA_FLITS=2 \
CHI_READ_RATIO=100 CHI_WRITE_RATIO=0 CHI_DATALESS_RATIO=0 CHI_CMO_RATIO=0 \
CHI_READ_SHARED_RATIO=100 CHI_READ_DMT_MISS_RATIO=100 \
CHI_READ_L3_HIT_RATIO=0 CHI_READ_DCT_RATIO=0 \
SWEEP_OUT=zcn_sn_read_ceiling.csv \
SWEEP_MAX_UNSTBL=5 \
SWEEP_LAMBDAS="0.005 0.01 0.015 0.016 0.018  0.02 0.021 0.022 0.023 0.024 0.025 0.026 0.028 0.03 0.031 0.032 0.033 0.034 0.035"  \
python3 sweep_sn_throughput.py
```

写 ceiling 将 `CHI_READ_RATIO=0 CHI_WRITE_RATIO=100`，并设置 `CHI_WRITE_BACK_RATIO=100 CHI_L3_EVICT_TO_SN_RATE=1.0`，`SWEEP_OUT=zcn_sn_write_ceiling.csv`。

---

## 6. ZCN 场景：完整流程示例

ZCN 场景参数：`vc_buf=4`，`DATA_FLITS=2`，XY 路由，`link_latency=2`。

### 6.1 一步跑扫描

```bash
cd booksim2/runfiles

LAMS="0.002 0.003 0.004 0.005 0.006 0.007 0.008 0.009 0.01 \
0.011 0.012 0.013 0.014 0.015 0.016 0.017 0.018 0.019 0.02 \
0.021 0.022 0.023 0.024 0.025 0.027 0.03"

# SN 本地峰值（报告所需）
SWEEP_BUFS=4 CHI_DATA_FLITS=2 SWEEP_LAMBDAS="$LAMS" \
  SWEEP_OUT=zcn_sn_local_peak.csv SWEEP_STATS_DIR=stats_out/zcn \
  python3 sweep_sn_local_peak.py
```

> 当前 ZCN 报告只依赖 `zcn_sn_local_peak.csv`；E2E ceiling CSV 为可选项。

### 6.2 生成报告

```bash
cd booksim2/doc
python3 zcn_generate_sim_report.py
```

输出：
- `zcn_sim_report.pdf`
- `zcn_sim_report_p1.png`

报告展示 SN local DAT / REQ 峰值柱状图和汇总表。可通过环境变量覆盖显示参数：

```bash
ZCN_VC_BUF=4 ZCN_DATA_FLITS=2 LOCAL_CSV=zcn_sn_local_peak.csv \
  python3 zcn_generate_sim_report.py
```

### 6.3 当前 ZCN 参考结果（node normalize 开启）

| 路径 | λ* (max avg) | SN DAT avg | SN DAT peak |
|------|--------------|------------|-------------|
| Read | 0.021 | 65.2% | 73.0% |
| Write | 0.035 | 85.5% | 87.2% |

---

## 7. 其他报告脚本

| 脚本 | 输入 CSV | 输出 |
|------|----------|------|
| `zcn_generate_sim_report.py` | `zcn_sn_local_peak.csv` | `zcn_sim_report.pdf` |
| `v6_generate_sn_local_peak_report.py` | `v6_repair_sn_local_peak.csv` | 多 buf 对比报告 |
| `v6_generate_sn_report.py` | SN throughput CSV | E2E 读写报告 |
| `v6_generate_vc_buf_report.py` | vc_buf sweep CSV | buffer 敏感性报告 |

用法均为：先跑对应 sweep 生成 CSV，再在 `doc/` 下执行报告脚本。

---

## 8. 输出文件速查

| 路径 | 内容 |
|------|------|
| `runfiles/chi_traffic` | BookSim 主配置（classes、injection_rate、traffic） |
| `runfiles/chi_traffic_anynet` | 6×7 mesh 拓扑 |
| `runfiles/booksim.log` | 最近一次仿真日志（手动运行时） |
| `runfiles/sn_local_stats.m` | 最近一次带 stats_out 的 per-node 统计 |
| `doc/<SWEEP_OUT>.csv` | 扫描汇总 |
| `doc/stats_out/` | 归档的 `sn_local_stats.m`（见 README） |
| `doc/*_report.pdf` | 生成的报告 |

---

## 9. BookSim 如何判定 unstable / 收敛

判定逻辑在 `src/trafficmanager.cpp` 的 `_SingleSim()`，以 **sample window**（默认 `sample_period=1000` cycle）为单位循环。每个被统计的 class（`measure_stats=1`）在每个窗口结束时算两个相对变化量：

- **延迟变化** `|Δlatency| / latency`（latency 用 packet latency，含在途 flit）
- **吞吐变化** `|Δaccepted| / accepted`

对应阈值（`booksim_config.cpp` 默认）：

| 阶段 | 阈值变量 | 默认 |
|------|----------|------|
| warmup 延迟 | `warmup_thres` | 0.05 |
| warmup 吞吐 | `acc_warmup_thres` | 0.05 |
| running 延迟 | `stopping_thres` | 0.05 |
| running 吞吐 | `acc_stopping_thres` | 0.05 |

流程：

1. **warming_up**：两量都 < 5% → 进入 running（并清一次统计）。
2. **running**：连续 **3 个窗口**两量都 < 5% → 判为**收敛**，进入 draining，正常打印 `Overall Traffic Statistics`。
3. 若在 `max_samples`（配置里设 `50`）个窗口内凑不齐 3 个稳定窗口 → 打印 `Too many sample periods needed to converge`，再由 `Run()` 打印 **`Simulation unstable, ending ...`**。
4. **另一条独立的 abort**：任何 class 的平均 packet latency（含在途 flit）> `latency_thres`（`CHI_LATENCY_THRES`，默认 500）→ 打印 `Average latency for class X exceeded ... Aborting simulation.`，写出 stats 后中止。

**关键点**：unstable ≠ 平均延迟高。它主要指**吞吐/延迟在窗口间不收敛**（相对波动 >5%）。所以即便某类 flit 的传输延迟看起来不高，只要 accepted rate 一直抖（源端顶满、注入队列进出不稳），就会被判 unstable。

扫描脚本据此把状态标为：

- `ok` — 收敛，取 `Overall` 块
- `UNSTBL` — 未收敛，回退取最后一次 `DisplayStats` 快照（报告里画虚线 ×）
- `SAT` / `NODATA` — 日志含 `unstable`/`Aborting` 或根本没有效统计
- `SWEEP_MAX_UNSTBL` 控制连续多少个饱和/UNSTBL 点后停止扫描

### unstable 能说明吞吐到上限了吗？

可以，但要说准确：**unstable 基本等价于“offered load 已超过网络饱和吞吐”，但它本身是收敛判据，不是直接的吞吐测量。**

- **直接含义**：`max_samples` 个窗口内吞吐/延迟波动收不到 5% 以内。物理上对应**注入速率 > 网络可疏导速率**，源队列越积越多、延迟单调上升。所以它是“已到/已过饱和点”的可靠信号。
- **真正的上限看 accepted 平台值**，不是看 UNSTBL 标签：λ 再加而 accepted util 不再上升、只有 packet latency 爆炸，那个平台就是饱和吞吐。本次 ZCN ceiling 数据：

  | 路径 | accepted util 平台 | 瓶颈 |
  |------|--------------------|------|
  | Read | ~62% | SN 注入口 + fan-out + VC/buffer/HoL |
  | Write | ~79% | fan-in 汇聚 + SN eject |

**三个 caveat：**

1. 这是**该配置/瓶颈的上限，不是链路 100% 物理带宽**。读 ~62%、写 ~79% 都受 SN 端口、扇入扇出、VC/buffer/HoL、路由限制。
2. **拐点附近的 UNSTBL 可能是临界噪声**——相对波动恰在 5% 上下横跳也会判 unstable，不代表深度饱和。区分方法：看 latency 是温和上升还是直冲几百 cycle。
3. **unstable 也可能来自采样噪声 / 统计没写全（NODATA）**，此时那点没有可信吞吐值，不能当上限。

**结论**：unstable ⇒ 很可能已达/超过该流量与配置下的饱和吞吐；但要“证明到上限”，应引用 **accepted-util 平台值 + latency 拐点**，而非只凭 UNSTBL 标签。要精确定位膝点，可在 0.015–0.03 间把 λ 按步长 0.001 加密。

---

## 10. 常见问题

### λ 扫描在饱和区没有数据（NODATA）

负载过高时仿真在写出有效统计前 abort。对策：
- 在饱和膝部附近加密 λ（如 0.002–0.03，步长 0.001）
- `sweep_sn_throughput.py` 设 `SWEEP_MAX_UNSTBL=5`，多收集几个饱和点再停

### 读/写 SN 流量不对称

确认 `CHI_NODE_NORMALIZE=1`（默认开启）。关闭后 SN 源消息（4 节点）相对 RN（84 节点）会被低估约 21×。可在 `chi_traffic` 头部注释查看 `node-count normalization` 行。

### 如何确认某个 class 对应读还是写

查看 `chi_traffic` 中 `// class ->` 注释行，或参考 [`stats_out/README.md`](stats_out/README.md) 第 5 节。读 DAT 看 SN 的 `sent_flits`；写 DAT 看 SN 的 `accepted_flits`。

### 扫描耗时

每个 λ 点约 2–5 秒。26 个 λ × 2 mix ≈ 1–2 分钟（local_peak）；E2E sweep 类似。

---

## 11. 快速命令索引

```bash
# 单点
CHI_ROUTING=xy CHI_LINK_LATENCY=2 CHI_VC_BUF_SIZE=4 CHI_DATA_FLITS=2 CHI_LAMBDA=0.02 \
  ... python3 gen_chi_traffic.py && ../src/booksim chi_traffic

# ZCN 扫描 + 报告
cd runfiles && SWEEP_BUFS=4 CHI_DATA_FLITS=2 SWEEP_LAMBDAS="..." \
  SWEEP_OUT=zcn_sn_local_peak.csv SWEEP_STATS_DIR=stats_out/zcn \
  python3 sweep_sn_local_peak.py
cd ../doc && python3 zcn_generate_sim_report.py
```
