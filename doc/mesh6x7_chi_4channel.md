# 6x7 Mesh + CHI 四独立物理通道 仿真说明（V1）

> 这是 **V1**：用 BookSim 原生的 4 种消息类型映射 4 条通道，无需改源码，
> 适合"读一致性 + snoop"的快速近似，但**无法建模写一致性数据流**。
> 若需要写事务建模，见 V2：[`mesh6x7_chi_v2_classsubnet.md`](mesh6x7_chi_v2_classsubnet.md)
> （通过 `class_subnet` 补丁让 subnet 按 class 选）。


本文档总结在 BookSim2 上构建的 **6x7 mesh + CHI 风格一致性流量**模型，
其中 CHI 的四条通道（REQ / DAT / SNP / RSP）被映射为 **4 个互相独立的物理网络**，
并给出一次注入率扫描（latency-throughput）的结果。

相关文件：

| 文件 | 作用 |
|---|---|
| `runfiles/gen_chi_mesh.py` | 生成拓扑 + 配置（支持环境变量覆盖参数） |
| `runfiles/mesh6x7_chi_anynet` | 生成的 anynet 拓扑（42 路由器 × 4 终端 = 168 节点） |
| `runfiles/mesh6x7_chi` | 生成的 BookSim 配置 |
| `runfiles/sweep_chi.py` | 注入率扫描脚本 |
| `runfiles/chi_sweep_results.csv` | 扫描结果数据 |

---

## 1. 拓扑

- 6 行 × 7 列 = 42 个路由器的二维 mesh（用 `anynet` 描述，因为 6≠7 非对称）。
- 每个路由器挂 **4 个终端 = 2 RN + 2 HN**：
  - 路由器 `r` → 节点 `4r, 4r+1` 为 **RN**（请求节点 / 核），`4r+2, 4r+3` 为 **HN**（home / 目录）。
  - 共 84 个 RN + 84 个 HN = **168 个节点**。

---

## 2. CHI 四通道 → 4 个独立物理网络

BookSim 的 `subnets` 会把整张网络**物理复制**多份；子网的分配是按它内部的
4 种消息类型（read_request / read_reply / write_request / write_reply）决定的。
因此把 CHI 的四条通道一一对应到这四种类型，并各自独占一个 subnet：

| CHI 通道 | BookSim 消息类型 | subnet | 包长 | 流向 |
|---|---|---|---|---|
| **REQ** | read_request  | 0 | 1 flit（控制） | RN → HN |
| **DAT** | read_reply    | 1 | 5 flit（64B cache line） | HN → RN（REQ 的回包） |
| **SNP** | write_request | 2 | 1 flit（控制） | → RN |
| **RSP** | write_reply   | 3 | 1 flit（控制） | RN →（SNP 的回包） |

### 关键技巧：用 `write_fraction` 把两个 class 锁成纯读 / 纯写

`use_read_write` 下，每个 class 会按 `write_fraction` 在「读请求/读应答」和
「写请求/写应答」之间选择。为了让 4 种类型互不冲突地落到 4 个 subnet，用两个 class：

- **class 0** `write_fraction=0` → 只产生 REQ(read_request) + DAT(read_reply)；目的地 = 所有 HN。
- **class 1** `write_fraction=1` → 只产生 SNP(write_request) + RSP(write_reply)；目的地 = 所有 RN。

于是：subnet0=REQ，subnet1=DAT，subnet2=SNP，subnet3=RSP，
**跨通道完全无 buffer 争用**，最贴近 CHI「四条独立通道」的硬件语义。

### 与之前 2-subnet 版的区别

| | 2-subnet 版 | 4-subnet 版（本文） |
|---|---|---|
| 物理网络数 | 2（请求 / 应答） | 4（每通道独占） |
| REQ 与 SNP | 共享物理网，靠 VC 隔离 | 完全物理隔离 |
| 资源开销 | 2× | 4× |
| 贴合度 | 请求/应答防死锁 | 四通道硬件级独立 |

---

## 3. 核心配置参数

`runfiles/mesh6x7_chi` 关键片段：

```
topology     = anynet;
network_file = mesh6x7_chi_anynet;
routing_function = min;

classes        = 2;
use_read_write = {1,1};
write_fraction = {0,1};            // class0=纯REQ/DAT, class1=纯SNP/RSP
injection_rate = {0.01,0.01};      // {REQ速率, SNP速率}
traffic        = {hotspot({...HN...}), hotspot({...RN...})};

read_request_size  = {1,1};   // REQ
read_reply_size    = {5,1};   // DAT (cache line)
write_request_size = {1,1};   // SNP
write_reply_size   = {1,1};   // RSP

subnets = 4;
read_request_subnet  = 0;   // REQ
read_reply_subnet    = 1;   // DAT
write_request_subnet = 2;   // SNP
write_reply_subnet   = 3;   // RSP

num_vcs     = 2;            // 每个 subnet 的 VC 数
vc_buf_size = 8;
sim_type    = latency;
```

### 可调旋钮（`gen_chi_mesh.py` 顶部，或用环境变量）

| 参数 | 环境变量 | 默认 | 含义 |
|---|---|---|---|
| `SNOOP_FACTOR` | `CHI_SNOOP` | 1.0 | snoop 放大比 = class1 速率 / class0 速率（每个 REQ 平均触发的 SNP 数） |
| `INJ` | `CHI_INJ` | 0.01 | 每节点每类的请求注入率（offered load） |
| `NUM_VCS` | `CHI_VCS` | 2 | 每个 subnet 的 VC 数 |

重新生成：`python3 gen_chi_mesh.py`（或 `CHI_SNOOP=2 python3 gen_chi_mesh.py`）。

---

## 4. 注入率扫描结果（snoop_factor = 1.0）

`sim_type = latency`，对 offered load 逐点扫描，记录每类的平均包延迟与接受 flit 率。
数据来自 `runfiles/chi_sweep_results.csv`。

| offered (每节点/类) | 状态 | REQ/DAT 延迟 | REQ/DAT 接受率 | SNP/RSP 延迟 | SNP/RSP 接受率 |
|---:|:---:|---:|---:|---:|---:|
| 0.004 | ok  | 30.6  | 0.0278 | 28.1  | 0.0040 |
| 0.006 | ok  | 30.5  | 0.0398 | 28.3  | 0.0063 |
| 0.008 | ok  | 31.0  | 0.0536 | 28.6  | 0.0086 |
| 0.010 | ok  | 31.3  | 0.0660 | 28.4  | 0.0109 |
| 0.011 | ok  | 32.0  | 0.0716 | 29.0  | 0.0121 |
| 0.012 | ok  | 32.2  | 0.0779 | 29.3  | 0.0132 |
| 0.013 | ok  | 33.5  | 0.0839 | 29.9  | 0.0143 |
| **0.014** | ok | **37.7** | **0.0875** | **38.2** | **0.0160** |
| 0.015 | ok  | 59.3  | 0.0903 | 105.3 | 0.0176 |
| 0.016 | SAT | —     | —      | —     | —      |

### 解读

- **空载延迟**：REQ/DAT ≈ 30 cycle，SNP/RSP ≈ 28 cycle（DAT 是 5-flit 大包，串行化使其略高）。
- **饱和拐点**：offered load ≈ **0.014 /节点/类**。
  - 0.014 处延迟开始明显抬升（~37 cycle），0.015 已严重排队（SNP/RSP 延迟飙到 105），0.016 直接饱和（latency 模式终止）。
- **饱和吞吐**（拐点处接受 flit 率）：REQ/DAT ≈ **0.088**，SNP/RSP ≈ **0.016**（合计 ≈ 0.10 flit/node/cycle）。
- **瓶颈分析**：DAT 通道（5-flit cache line）承载了绝大部分 flit 流量，是吞吐瓶颈；
  SNP/RSP 均为 1-flit 控制包，flit 负载很轻但同样在拐点附近出现延迟突增，
  说明饱和由共享的路由器交换/链路带宽决定，而非单一物理网。

---

## 5. 复现步骤

```bash
cd booksim2/runfiles
python3 gen_chi_mesh.py          # 生成拓扑 + 配置
../src/booksim mesh6x7_chi       # 单点仿真
python3 sweep_chi.py             # 注入率扫描，结果写入 chi_sweep_results.csv
```

调 snoop 放大比再扫描：

```bash
CHI_SNOOP=2.0 python3 sweep_chi.py
```

---

## 6. 模型局限（重要）

- BookSim 没有 CHI 的协议状态机；本模型只复现**流量特征**（通道、包长、请求-应答、snoop 放大），不复现一致性语义。
- BookSim 每个节点都按相同的每类速率注入，**无法按 RN/HN 角色门控注入**。
  由于每个路由器同时挂 RN 和 HN，源/目的*路由器*仍是全集，网络级延迟/吞吐是合理近似。
- snoop 携带数据（dirty 命中回 DAT）未建模，SNP/RSP 都按 1-flit 控制包处理；
  如需更精确，可让 class 1 的 `write_reply_size` 取 5（RSP 携带 cache line）。
