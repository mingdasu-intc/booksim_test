# 6×7 Mesh 仿真说明（BookSim2）

本文档总结在 BookSim2 上搭建的 **6×7（42 节点）mesh** 仿真：拓扑构建、配置参数含义、运行方式、以及一致性流量（uniform vs hotspot）的对比结果。

---

## 1. 概览

| 项目 | 内容 |
|---|---|
| 模拟器 | BookSim 2.0（周期精确互连网络模拟器） |
| 拓扑 | 6 行 × 7 列 mesh，42 个路由器，每个挂 1 个 PE 终端 |
| 拓扑实现 | `anynet`（任意拓扑，从文件读连接） |
| 路由 | 最小路径路由表（`min`） |

> 为什么用 `anynet` 而不是内置 `mesh`：内置 `mesh` 是对称的 k-ary n-cube（节点数 = k^n），只能做 k×k 方形网格，无法表示非对称的 6×7。`anynet` 通过拓扑文件显式描述 42 个节点的网格连接。

拓扑结构图见 `mesh6x7_topology.png` / `.pdf`。路由器编号 `id = row×7 + col`；节点度数：角 2、边 3、内部 4。

---

## 2. 文件清单

### 配置与拓扑（`runfiles/`）
| 文件 | 说明 |
|---|---|
| `mesh6x7_anynet` | 6×7 网格拓扑描述（42 路由器 + 链路） |
| `mesh6x7config` | 基础 mesh 仿真（uniform 单向流量） |
| `mesh6x7_coh_uniform` | 一致性流量 + uniform（分布式目录） |
| `mesh6x7_coh_hotspot` | 一致性流量 + hotspot（4 个集中目录节点） |

### 文档与产物（`doc/`）
| 文件 | 说明 |
|---|---|
| `mesh6x7_simulation_notes.md` | 本文档 |
| `mesh6x7_topology.png` / `.pdf` | 网络结构图 |
| `mesh6x7_coherence_report.pdf` | uniform vs hotspot 对比报告（2 页） |
| `draw_mesh6x7.py` | 拓扑绘图脚本 |
| `generate_coherence_report.py` | 对比报告生成脚本 |

---

## 3. 配置参数详解

以最完整的 `mesh6x7_coh_hotspot` 为主线。其它配置是其子集或不同取值。

### 3.1 拓扑
```
topology         = anynet;          // 任意拓扑模式
network_file     = mesh6x7_anynet;  // 拓扑描述文件
routing_function = min;             // 最小路径路由表（anynet 专用）
```

### 3.2 一致性事务流量（请求/应答）
```
use_read_write = 1;        // 开启请求-应答：请求到达后自动产生返回源的应答
write_fraction = 0.3;      // 30% 写、70% 读

read_request_size  = 1;    // 读请求 = 地址（控制包，1 flit）
read_reply_size    = 5;    // 读响应 = 一条 cache line（数据包，5 flit）
write_request_size = 5;    // 写请求携带数据（5 flit）
write_reply_size   = 1;    // 写应答 = ack（1 flit）
```
- 假设：16B/flit，64B cache line = 4 数据 flit + 1 头 flit = 5 flit。
- 体现一致性流量典型的**控制包小、数据包大**的不对称特征。
- 基础配置 `mesh6x7config` 用 `use_read_write = 0`（普通单向流量）。

### 3.3 多子网（虚拟网络，防协议死锁）
```
subnets = 2;                  // 复制 2 套完整网络
read_request_subnet  = 0;     // 请求走子网 0
write_request_subnet = 0;
read_reply_subnet    = 1;     // 响应走子网 1
write_reply_subnet   = 1;
```
- 请求与响应**物理隔离**，打破"请求等响应、响应等请求"的协议级死锁，对应真实协议的独立虚拟网络（vnet）。

### 3.4 VC 分区
```
read_request_begin_vc  = 0;  read_request_end_vc  = 3;
write_request_begin_vc = 0;  write_request_end_vc = 3;
read_reply_begin_vc    = 0;  read_reply_end_vc    = 3;
write_reply_begin_vc   = 0;  write_reply_end_vc   = 3;
```
- `use_read_write` 模式下路由函数按消息类型分区 VC，**默认范围假设 16 个 VC**。本配置只有 4 个 VC，故需显式把四种类型都设为 0–3；死锁隔离已由子网完成。
- 注意：若省略这几行而 `num_vcs < 16`，会触发断言 `vc_end < _vcs` 崩溃。

### 3.5 流控与路由器微架构
```
num_vcs     = 4;       // 每输入端口每子网 4 条虚拟通道
vc_buf_size = 8;       // 每条 VC 缓冲深度 8 flit
vc_allocator = islip;  // VC 分配器 = iSLIP
sw_allocator = islip;  // 交叉开关分配器 = iSLIP
alloc_iters  = 1;      // 分配器迭代次数
```
路由器流水线延迟（一致性配置用默认值，基础配置显式列出）：
```
credit_delay   = 2;    // 信用回传延迟
routing_delay  = 0;    // 路由计算
vc_alloc_delay = 1;    // VC 分配
sw_alloc_delay = 1;    // 交叉开关分配
st_final_delay = 1;    // 最终交换
input_speedup  = 1;  output_speedup = 1;  internal_speedup = 1.0;  // 加速比（1 = 无加速）
wait_for_tail_credit = 1;  // 等包尾信用返回才释放 VC
```

### 3.6 流量模式与仿真控制
```
sim_type       = latency;                 // 延迟测量模式（饱和时超阈值中止）
traffic        = hotspot({{8,12,29,33}}); // 集中目录；uniform 配置为 uniform
packet_size    = 1;                       // read_write 模式下被 *_size 覆盖
sample_period  = 1000;                    // 每 1000 周期采样/判收敛
warmup_periods = 3;                       // 热身 3 个采样周期后清零开始测量
sim_count      = 1;                       // 仿真次数（多次取平均）
injection_rate = 0.05;                    // 每节点每周期注入的请求包数（offered load）
```

### 3.7 三个配置对比
| 参数 | mesh6x7config | coh_uniform | coh_hotspot |
|---|---|---|---|
| use_read_write | 0 | 1 | 1 |
| traffic | uniform | uniform | hotspot(4 节点) |
| num_vcs | 8 | 4 | 4 |
| subnets | 1（默认） | 2 | 2 |
| routing | min | min | min |

---

## 4. 运行方式

```bash
# 编译（首次）
cd booksim2/src && make

# 运行单个配置
cd booksim2/runfiles
../src/booksim mesh6x7_coh_uniform

# 注入率扫描（延迟-吞吐曲线，自动定位饱和点）
../utils/sweep.sh ../src/booksim mesh6x7_coh_uniform
```

> 进程退出码 255 是 BookSim 正常返回值；只要打印了 "Overall Traffic Statistics" 即为正常完成。

---

## 5. 关键指标说明

- **Throughput（吞吐量）** = `Accepted flit rate average` = 总接收 flit 数 ÷ 测量周期数 ÷ 节点数，单位 flits/node/cycle。
- **Latency（延迟）** = 逐包平均，从包创建（含源队列等待）到到达。
- **sim_type 区别**：`latency` 模式在延迟超阈值时中止、收敛要求延迟+吞吐都稳定、结束时排空所有测量包；`throughput` 模式饱和时继续跑、只看吞吐稳定、不排空——用于压到饱和读吞吐上限。

---

## 6. 实验结果：uniform vs hotspot（一致性流量）

对两个配置各做注入率扫描的结果（详见 `mesh6x7_coherence_report.pdf`）：

| 指标 | Uniform（分布式） | Hotspot（4 目录） | 差距 |
|---|---|---|---|
| 饱和注入率 (pkt/node/cyc) | 0.067 | 0.023 | ≈2.9× |
| 峰值吞吐 (flit/node/cyc) | 0.40 | 0.14 | ≈2.9× |
| 零负载延迟 (cyc) | ~30.4 | ~30.2 | 基本相同 |
| 饱和处延迟跳变 | 平滑到 ~40 | 突增到 281 | hotspot 更陡 |

**结论**：低负载下两者几乎一致（平均跳数都约 5.1）。但 hotspot 把所有请求挤向 4 个目录节点，这些节点的 ejection 端口和周边链路成为瓶颈，导致它在约 1/3 的负载下就饱和、延迟急剧爆炸。说明**集中式目录是吞吐瓶颈，分布式 home node 对可扩展的一致性流量至关重要**。
