# SN 利用率上限分析（upbound_analysis）

本文解释：在当前 BookSim CHI 仿真配置下，为何 SN（DDR）终端链路的 **accepted / sent flit 利用率无法达到 100%**，以及观测到的 ~62%–88% 平台值来自哪些结构性限制。

相关数据与报告：

| 文档 / 数据 | 说明 |
|-------------|------|
| [`zcn_topology_comparison.md`](zcn_topology_comparison.md) | 6×7 vs 7×6 拓扑下的 SN util 对比 |
| [`simulation_guide.md`](simulation_guide.md) §9 | BookSim unstable 判定与“饱和”含义 |
| `doc/archive/v6_repair_vc_buf_sweep.csv` | vc_buf 敏感性扫描 |
| `zcn_*` / `zcn_lp_*` ceiling CSV | 读/写专项饱和扫描 |

---

## 1. 问题陈述

在 read/write ceiling 专项（100% 读 DMT miss 或 100% WriteBack+L3EvictToSN）下，即使 λ 继续增大、仿真进入 UNSTBL，**SN 侧 DAT 利用率仍停在一个平台**，例如：

| 拓扑 | Read SN DAT avg @ λ* | Write SN DAT avg @ λ* | Read E2E 平台 | Write E2E 平台 |
|------|----------------------|------------------------|---------------|----------------|
| 6×7 (`zcn`) | 65.2% | 87.3% | ~62% | ~75% |
| 7×6 (`zcn_lp`) | 78.3% | 84.1% | ~77% | ~71% |

直觉上：若所有节点都向少数 SN 发请求，SN 端口应能“每 cycle 都有 flit 进出”，即 **1 flit/cycle = 100%**。该直觉在**理想输出排队、无限缓冲、完美调度**的模型下成立；当前仿真使用的是 **input-buffered wormhole + credit 流控 + 有限 VC buffer**，因此平台值低于 100% 是预期行为，而非测量错误。

---

## 2. 理想模型 vs 当前模型

| 假设 | 理想 hotspot 模型 | 当前 BookSim 配置 |
|------|-------------------|-------------------|
| 缓冲 | 输出无限队列，吸收到达波动 | 输入 VC buffer，深度有限 |
| 流控 | 无反压或瞬时 credit | Credit 往返延迟（RTT） |
| 交换 | 每 cycle 最大匹配 | 启发式分配器，单轮迭代 |
| 分组 | 可独立调度 | Wormhole，队头阻塞（HoL） |
| 到达 | 可编排为每 cycle 1 flit | 每节点 Bernoulli 注入，随机起伏 |

在理想模型下，超额 offered load 会把出口队列灌满，**平均出口速率 → 链路物理上限 1 flit/cycle**。在当前模型下，**波峰被上游反压截断、波谷无法被后续补投**，出口平均利用率必然 **< 1**。

---

## 3. 当前仿真配置（ZCN 基准）

| 参数 | 值 | 来源 |
|------|-----|------|
| `vc_buf_size` | 4 | `CHI_VC_BUF_SIZE` |
| `num_vcs` | 2 | `CHI_VCS` |
| `link_latency` | 2（router–router） | `CHI_LINK_LATENCY` |
| `vc_allocator` | `islip` | `CHI_VC_ALLOCATOR` |
| `sw_allocator` | `separable_output_first(round_robin)` | `CHI_SW_ALLOCATOR` |
| `alloc_iters` | 1 | `gen_chi_traffic.py` / `booksim_config.cpp` |
| 路由器流水线 | routing 1 + vc_alloc 1 + sw_alloc 1 + st 1 cycle | `booksim_config.cpp` |
| `credit_delay` | 0 | 默认 |
| `input_speedup` / `output_speedup` | 1 | 无 crossbar 加速 |
| SN 链路模型 | 1 flit/cycle 终端带宽（`LINK_CEILING=1.0`） | sweep 脚本 |

---

## 4. 利用率低于 100% 的机制

### 4.1 Credit 往返时延 vs VC buffer 深度（主因之一）

链路采用 **credit-based 流控**：上游每发 1 flit 消耗 1 credit；credit 在下游 buffer 腾出位置后经链路返回。

粗略 credit RTT（单跳）：

```
RTT ≈ link_latency × 2 + 路由器流水线
    ≈ 2×2 + (1+1+1+1) = 8 cycle
```

`vc_buf_size = 4` 时，单 VC 在途 flit 上限为 4，credit 耗尽后必须等待返回。单 VC 可持续吞吐近似：

```
μ_vc ≈ vc_buf_size / RTT ≈ 4/8 = 0.5 flit/cycle
```

2 个 VC 理论上界为 1.0 flit/cycle，但要求两 VC **持续并行占满且仲裁每拍成功**——实际达不到，故读方向（SN **注入口**单通道）常明显低于写方向。

**实验证据**（`v6_repair_vc_buf_sweep.csv`，6×7 拓扑 era）：

| vc_buf | Read util | Write util |
|--------|-----------|------------|
| 2 | 33% | 53% |
| 4 | 62% | 88% |
| 8 | 69% | 91% |
| 16 | 70% | 91% |
| 32 | 69% | 91% |

- buf 从 2→8：**利用率随 buffer 加深而上升**（credit 限制被放松）。
- buf ≥ 8：**平台不再随 buffer 增大**，说明瓶颈从 credit 转为 HoL / 分配器 / 到达随机性等。

### 4.2 Wormhole 队头阻塞（HoL blocking）

Wormhole 路由中，同一 input VC 内 flit 按序前进。若队头 flit 因目标方向无 credit 或输出被占而停滞，**同 VC 后续 flit 即使目标端口空闲也无法绕过**。

写路径（HN→SN fan-in）尤其严重：多源流量在共享链路上混排，去 SN168 的包可能被去 SN169 的包挡在队头，导致 SN eject 端口出现空 cycle。饱和时拥塞沿树状向外扩散，HoL 加剧，**损失带宽无法通过“加大注入”补回**。

### 4.3 分配器非理想匹配

- **`vc_allocator = islip`**：受全局 `alloc_iters` 影响。`alloc_iters = 1` 时只做一轮 grant/accept，多输入争同一输出时可能漏配，crossbar 空转。
- **`sw_allocator = separable_output_first`**：**不受** `alloc_iters` 影响；为可分离启发式，非最大匹配。

`alloc_iters` 含义：迭代式分配器（iSLIP、PIM、select）每 cycle 内重复多轮“grant → accept”，在尚未匹配的输入/输出间补配，更接近 maximal matching。iSLIP 文献中约 **log₂N 轮**趋于收敛；5 端口 mesh 路由器通常 2–3 轮。当前仅 1 轮，VC 分配在争用下效率偏低。

### 4.4 随机到达 vs 完美调度

注入为 **per-node 概率 λ**，瞬时到达有起伏。在输出排队模型中，队列可平滑波动、维持出口满负荷；在 **input 排队 + 有限 buffer + 反压** 模型中：

- 波峰：上游 buffer 满，反压阻止继续注入；
- 波谷：下游已空闲，但上游没有 ready flit；

出口 **cycle 级空泡** 无法被统计平均“补投”消除，长期平均 util **< 1**。

### 4.5 读 / 写 不对称（fan-out vs fan-in）

| 路径 | 流量形态 | SN 侧瓶颈 | 典型平台（6×7 / 7×6） |
|------|----------|-----------|------------------------|
| Read | 4 SN → 84 RN **fan-out** | SN **inject**（单 terminal、单 input port） | ~62% / ~77% |
| Write | 多 HN → 4 SN **fan-in** | SN **eject**；多输入争用最后一跳 | ~75% / ~71% |

- **读**：SN 注入口是单点，credit RTT + 浅 buffer 限制最直接，平台偏低。
- **写**：最后一跳路由器有多个输入同时向 SN 排队，出口仲裁更容易每 cycle 服务一个 flit，故 util 可更高（6×7 下 ~88% SN local）。
- **7×6** 将 SN 分到左右边中部，读 fan-out 改善（~78%），写略降，读写比从 1.34× 缩至 1.08×（见拓扑对比文档）。

---

## 5. 与 “unstable” 的关系

高 λ 下仿真常标 **UNSTBL**：窗口间吞吐/延迟相对变化 > 5%，无法在 `max_samples` 内收敛（见 `simulation_guide.md` §9）。这表示 **offered load 已超过网络可稳定疏导的速率**，与“SN 利用率到平台”一致。

注意：

- **UNSTBL ≠ 延迟一定很高**；读路径在平台区 packet latency 可仍上升（源队列排队）。
- **平台 util 才是饱和吞吐的证据**；λ 再加，accepted 不再涨，只有 latency 恶化。

---

## 6. 为何不是 “SN 物理带宽不够”

仿真中 SN 终端链路按 **1 flit/cycle** 计量（100% = 1.0）。观测到的 62%–88% 是 **在 wormhole + credit + 浅 buffer + 争用路由下 achievable 的 sustained 吞吐**，不是把链路时钟降频或 SN 控制器降频的结果。

若要做 **物理上限** 对照实验，需改用：

- 极大 `vc_buf_size`（≥ RTT 覆盖）；
- 更大 `num_vcs`、更高 `alloc_iters`；
- 或理想化流量（同步注入、无竞争路径）。

vc_buf 扫描已表明：即使 buf=32，读仍 ~69%、写 ~91%，说明 **buffer 加深 alone 无法到 100%**。

---

## 7. 若要逼近 100% 可调整的方向

按预期收益排序（仿真中可试，硬件需权衡时序/面积）：

| 手段 | 作用 | 备注 |
|------|------|------|
| 增大 `vc_buf_size`（≥ 8） | 覆盖 credit RTT，减轻单 VC 吞吐上限 | 8 以上收益递减 |
| 增大 `num_vcs` | 分流，减轻 HoL | 读 inject 仍可能单端口受限 |
| 提高 `alloc_iters` 或 `vc_allocator = islip(3)` | 改善 VC 匹配 | 仅影响 vc_allocator；sw 需换 islip/wavefront |
| 换 `sw_allocator` 为 `islip` / `wavefront` | 改善 switch 匹配 | 与 separable_output_first 对比 |
| SN 多 terminal / 多 inject 端口（读） | 从架构上消除单点 inject | 需改拓扑与 traffic class |
| 更大 `link_latency` 下同步加大 buffer | 保持 `buf ≥ RTT` 比例 | RTT 变长时 buf 需同比增大 |

在 **vc_buf=4、alloc_iters=1、2 VC** 的 ZCN 配置下，**~85%–90%（写）与 ~65%–78%（读）** 可视为该 mesh hotspot 流量的正常 achievable 上限，而非仿真 bug。

---

## 8. 结论摘要

1. **100% 直觉**适用于理想输出排队交换机；**当前模型**为 input-buffered wormhole + credit，存在结构性空泡。
2. **Credit RTT vs vc_buf=4** 使单 VC 理论吞吐约 0.5 flit/cycle，是读方向主因之一；vc_buf 扫描验证 buf↑ → util↑ 直至平台。
3. **HoL、分配器单轮迭代、随机注入** 进一步压低平均 util，且在 buf 足够大后成为主瓶颈。
4. **写 fan-in** 因多输入并行争用最后一跳，util 高于 **读 fan-out** 的单 inject 端口。
5. 拓扑优化（7×6 SN 左右分布）可**提高读平台上限**，但不改变“难以到 100%”的本质，除非放宽 buffer/VC/分配器或架构。

---

## 9. 复现与延伸阅读

```bash
# vc_buf 敏感性（需使用 archive 中对应 sweep 脚本与 6×7 拓扑）
# 见 doc/archive/v6_repair_vc_buf_sweep.csv

# 当前 ZCN / ZCN-LP ceiling 与 local peak
cd booksim2/runfiles
python3 sweep_sn_throughput.py    # SWEEP_OUT=zcn_lp_sn_read_ceiling.csv 等
python3 sweep_sn_local_peak.py    # SWEEP_OUT=zcn_lp_sn_local_peak.csv
```

- 拓扑对比：[`zcn_topology_comparison.md`](zcn_topology_comparison.md)
- 仿真流程：[`simulation_guide.md`](simulation_guide.md)
- BookSim 默认流水线与 `alloc_iters`：`src/booksim_config.cpp`
- iSLIP 迭代实现：`src/allocators/islip.cpp`（`for (iter = 0; iter < _iSLIP_iter; ++iter)`）
