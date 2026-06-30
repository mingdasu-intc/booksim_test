# CHI 事务分类统计 + BookSim 流量文件生成器

本文说明新的 CHI 流量生成方式：先把请求按 **read / write / dataless / cmo**
四个大类划分，每个大类再分子类；每个子类会展开成一条**完整消息流程**，再转成
BookSim traffic classes。L3 与 HN 在一起，因此 **L3/HN hit rate** 会决定流程是否访问
SN/DDR。

> BookSim 没有 trace 注入模式，它"导入"的流量就是配置里的合成流量描述。
> 生成器把**每种 CHI 消息类型编码成一个 traffic class**，借助 `class_subnet`
> 源码补丁（见 [`v3_mesh6x7_chi_v2_classsubnet.md`](v3_mesh6x7_chi_v2_classsubnet.md)）
> 把它落到对应 CHI 通道的物理子网上。

---

## 1. CHI 四通道与子网映射

| CHI 通道 | 含义 | 方向（典型） | 子网 |
|---|---|---|---|
| REQ | 请求 | RN → HN | 0 |
| RSP | 控制响应 | 双向 | 1 |
| SNP | 监听 | HN → RN | 2 |
| DAT | 数据 | 双向 | 3 |

包长（默认 16B/flit，64B cache line）：控制消息 = **1 flit**；数据消息 = **5 flit**
（4 个数据 flit + 1 个头 flit，可在脚本里改 `FLIT_BYTES` / `LINE_BYTES`）。

### SN / DDR 节点放置

在原 6×7 mesh、每 router 2RN+2HN 的基础上，额外挂 4 个 **SN**（Subordinate Node）
用于访问 DDR：

| router 坐标 | router id | SN node id | 说明 |
|---|---:|---:|---|
| (0,1) | 1 | 168 | 顶部直连 DDR SN |
| (0,2) | 2 | 169 | 顶部直连 DDR SN |
| (0,4) | 4 | 170 | 顶部直连 DDR SN |
| (0,5) | 5 | 171 | 顶部直连 DDR SN |

因此总节点数从 168 变为 **172**：84 RN + 84 HN + 4 SN。

---

## 2. 四大类与子类

`CHI_LAMBDA` 是总事务起始率（transactions/node/cycle）。四大类比例会归一化，子类比例也
会在各自大类内归一化。

| 大类 | 默认比例 | 子类 | 默认子类比例 |
|---|---:|---|---|
| read | 55% | ReadShared / ReadUnique / ReadNoSnp | 70% / 25% / 5% |
| write | 30% | WriteUnique / WriteBack / WriteClean / WriteEvict | 45% / 25% / 15% / 15% |
| dataless | 10% | CleanUnique / MakeUnique | 55% / 45% |
| cmo | 5% | CleanShared / CleanInvalid / MakeInvalid | 35% / 35% / 30% |

### 可配参数

| 参数 | 默认 | 含义 |
|---|---:|---|
| `CHI_LAMBDA` | 0.001 | 总事务起始率 |
| `CHI_READ_RATIO` / `CHI_WRITE_RATIO` / `CHI_DATALESS_RATIO` / `CHI_CMO_RATIO` | 55 / 30 / 10 / 5 | 四大类比例 |
| `CHI_READ_SHARED_RATIO` / `CHI_READ_UNIQUE_RATIO` / `CHI_READ_NOSNP_RATIO` | 70 / 25 / 5 | read 子类比例 |
| `CHI_WRITE_UNIQUE_RATIO` / `CHI_WRITE_BACK_RATIO` / `CHI_WRITE_CLEAN_RATIO` / `CHI_WRITE_EVICT_RATIO` | 45 / 25 / 15 / 15 | write 子类比例 |
| `CHI_CLEAN_UNIQUE_RATIO` / `CHI_MAKE_UNIQUE_RATIO` | 55 / 45 | dataless 子类比例 |
| `CHI_CMO_CLEAN_SHARED_RATIO` / `CHI_CMO_CLEAN_INVALID_RATIO` / `CHI_CMO_MAKE_INVALID_RATIO` | 35 / 35 / 30 | cmo 子类比例 |
| `CHI_READ_L3_HIT_RATIO` / `CHI_READ_DMT_MISS_RATIO` / `CHI_READ_DCT_RATIO` | 70 / 20 / 10 | ReadShared/ReadUnique 场景比例 |
| `CHI_READ_NOSNP_L3_HIT_RATIO` / `CHI_READ_NOSNP_DMT_MISS_RATIO` | 75 / 25 | ReadNoSnp 场景比例 |
| `CHI_WU_NO_SHARER_RATIO` / `CHI_WU_CLEAN_SHARER_RATIO` / `CHI_WU_DIRTY_SHARER_RATIO` | 60 / 30 / 10 | WriteUnique 场景比例 |
| `CHI_WE_ACCEPT_RATIO` / `CHI_WE_REJECT_RATIO` | 70 / 30 | WriteEvict 场景比例 |
| `CHI_DATALESS_NO_SHARER_RATIO` / `CHI_DATALESS_CLEAN_SHARER_RATIO` / `CHI_DATALESS_DIRTY_SHARER_RATIO` | 60 / 30 / 10 | CleanUnique/MakeUnique 场景比例 |
| `CHI_CMO_L3_CLEAN_RATIO` / `CHI_CMO_CLEAN_SHARER_RATIO` / `CHI_CMO_DIRTY_SHARER_RATIO` | 60 / 30 / 10 | CMO 场景比例 |
| `CHI_L3_EVICT_TO_SN_RATE` | 0.20 | WriteBack 触发异步 L3 dirty eviction 到 SN 的比例 |
| `CHI_DATA_FLITS` | 2 | 一次 DAT 数据传输的 BookSim flit/beat 数；设为 5 可恢复 64B/16B+header 口径 |

## 3. 完整流程展开

### Read

ReadShared / ReadUnique：

- `l3_hit`：RN→HN REQ，HN→RN DAT，RN→HN RSP `CompAck`。
- `dmt_miss`：RN→HN REQ，HN→SN REQ `ReadNoSnp_DMT`，SN→RN DAT `CompData_DMT`，SN→HN RSP `ReadReceipt`，RN→HN RSP `CompAck`。
- `dct`：RN→HN REQ，HN→RN-B SNP，RN-B→RN-A DAT，RN-B→HN RSP，HN→RN-A RSP `Comp`，RN-A→HN RSP `CompAck`。

ReadNoSnp：

- `l3_hit`：RN-I→HN-I REQ，HN-I→RN-I DAT，RN-I→HN-I RSP `CompAck`。
- `dmt_miss`：RN-I→HN-I REQ，HN-I→SN REQ，SN→RN-I DAT，SN→HN-I RSP `ReadReceipt`，RN-I→HN-I RSP `CompAck`。

### Write

WriteUnique：

- `no_sharer`：RN→HN REQ，HN→RN RSP `DBIDResp`，RN→HN DAT `WriteData`，HN→RN RSP `Comp`。
- `clean_sharer`：额外 HN→RN-B SNP，RN-B→HN RSP `SnpResp_I`；总计 REQ=1/SNP=1/DAT=1 data transfer/RSP=3。
- `dirty_sharer`：额外 HN→RN-B SNP，RN-B→HN DAT `SnpRespData_I`；模型同时计一个 dirty response control RSP，以匹配用户表的 RSP=3。

WriteBack：

- RN 侧主事务：RN→HN REQ，HN→RN RSP `DBIDResp`，RN→HN DAT `CopyBackWriteData`，HN→RN RSP `Comp`。
- 异步 L3 dirty eviction：HN→SN REQ，HN→SN DAT，SN→HN RSP；由 `CHI_L3_EVICT_TO_SN_RATE` 控制，不计入 RN 关键路径。

WriteClean / WriteEvict：

- WriteClean 按 L3 hit 更新：REQ + DBIDResp + DAT + Comp。
- WriteEvict 分 `accept`（REQ + DBIDResp + DAT + Comp）和 `reject`（REQ + CompReject）。

### Dataless

CleanUnique / MakeUnique：

- `no_sharer`：REQ + Comp + CompAck。
- `clean_sharer`：REQ + SNP + SnpResp + Comp + CompAck。
- `dirty_sharer`：REQ + SNP + SnpRespData DAT + dirty response control + Comp + CompAck；脏数据进 L3，不访问 SN。

### CMO

CleanShared / CleanInvalid / MakeInvalid：

- `l3_clean`：REQ + Comp。
- `clean_sharer`：REQ + SNP + SnpResp + Comp。
- `dirty_sharer`：
  - CleanShared：REQ + SNP + SnpRespData DAT + Comp，脏数据留 L3，不访问 SN。
  - CleanInvalid：REQ + SNP + RN→HN dirty DAT + HN→SN writeback DAT + Comp，必须落 SN。
  - MakeInvalid：REQ + SNP + SnpResp + Comp，不写回 SN。

---

## 4. 生成器用法

脚本：`runfiles/gen_chi_traffic.py`，输出两份文件：

| 输出 | 作用 |
|---|---|
| `runfiles/chi_traffic_anynet` | 拓扑（6×7 mesh，每路由器 2RN+2HN，另有 4 个 SN，共 172 节点） |
| `runfiles/chi_traffic` | BookSim 流量配置（默认 129 个 class，按完整场景表展开） |

### 调比例方式

使用环境变量设置四大类比例、子类比例和命中率。例如：

```bash
cd booksim2/runfiles

# 默认事务混合
python3 gen_chi_traffic.py
../src/booksim chi_traffic

# 读多、更多 L3 hit，较少 DMT miss
CHI_READ_RATIO=70 CHI_WRITE_RATIO=20 CHI_READ_L3_HIT_RATIO=85 CHI_READ_DMT_MISS_RATIO=10 python3 gen_chi_traffic.py

# 写多、WriteUnique 更多 dirty sharer
CHI_WRITE_RATIO=60 CHI_WU_DIRTY_SHARER_RATIO=25 python3 gen_chi_traffic.py
```

运行脚本会打印 SN 放置、四大类/子类比例、命中率参数、展开后的 class 表，以及每大类/每通道 offered flit 率。

### 配置映射原理

生成器从消息表自动推出 BookSim 参数：

```
classes        = 129;                        // 默认比例下展开得到的 class 数
use_read_write = {0,...};                 // 开环单向流
subnets        = 4;
class_subnet   = {...};                    // 每条消息按 REQ/RSP/SNP/DAT 映射子网
class_source   = {{...}, {...}, ...};      // 每条消息允许注入的源节点集合
packet_size    = {...};                    // 控制=1, 数据=CHI_DATA_FLITS(默认2)
injection_rate = {...};                    // 由完整场景表和比例推导
traffic        = {hotspot(终点角色的节点集合), ...};
```

`class_source` 是在 BookSim 中新增的源节点过滤配置。它和 `traffic` 配合使用：

- `class_source` 控制 **谁能发**，例如 `SN->RN DAT` 只允许 node168–171 注入。
- `traffic=hotspot(...)` 控制 **发给谁**，例如目的集合为所有 RN。
- `class_subnet` 控制 **走哪条物理通道**，例如 DAT 走 subnet 3。

因此当前模型已经能准确表达 `RN->HN`、`HN->SN`、`SN->RN`、`SN->HN`、`RN->RN` 等角色方向。

### Router / VC / Buffer / Arbitration 配置

当前生成器默认输出如下 BookSim router 参数：

```text
num_vcs     = 2;
vc_buf_size = 2;
vc_allocator = islip;
sw_allocator = separable_output_first(round_robin);
```

含义：

- 每个输入端口有 `2` 个 VC。
- 每个 VC buffer 深度为 `2` flit。
- 输出 switch 仲裁使用 `separable_output_first(round_robin)`。BookSim 源码没有名为 `lrg` 的 allocator；
  这里用输出端 round-robin arbiter 近似 LRG（Least Recently Granted）行为。
- 参数可通过环境变量覆盖：
  - `CHI_VCS`
  - `CHI_VC_BUF_SIZE`
  - `CHI_VC_ALLOCATOR`
  - `CHI_SW_ALLOCATOR`

拓扑方面，`anynet` 的 router 端口数由连接关系决定：普通内部 router 最多为
`4 mesh links + 4 RN/HN terminals = 8` 个输入/输出端口；挂 SN 的顶行 router 为
`3 mesh links + 4 RN/HN terminals + 1 SN = 8` 个输入/输出端口。

### 路由算法（min / XY 可选）

```text
routing_function = min;       // 默认：Dijkstra 最小跳数表（确定性单路径）
anynet_cols      = 7;         // mesh 宽度，供 XY 还原 (row,col)
```

- `min`（默认）：`anynet` 自带的 `min_anynet`，用 Dijkstra 预计算最小跳数路由表，
  tie-break 由节点遍历顺序固定。
- `xy`：维序（先 X 列、后 Y 行）确定性路由。通过环境变量 `CHI_ROUTING=xy` 让生成器
  输出 `routing_function = xy`，BookSim 自动拼成 `xy_anynet`。

  XY 需要源码补丁（已合入）：
  - `src/networks/anynet.{hpp,cpp}`：新增 `routeXY()`，按 `id = row*cols + col` 计算
    下一跳路由器并用 `router_list` 查端口；`buildRoutingTable()` 在 `routing_function=xy`
    时改用 XY 填表；注册 `xy_anynet` 复用 `min_anynet` 读表器。
  - `src/booksim_config.cpp`：新增整型字段 `anynet_cols`。
  - 改完需在 `src/` 下 `make` 重新编译。

  XY 是维序、无环，天然 deadlock-free。实测在拐点附近（`LAMBDA=0.0045`）XY 比 `min`
  的 RSP/DAT 延迟更低（RSP 89.5→42.5、DAT 54.0→43.9 cycle），但根本饱和点仍≈`0.005`
  （受 4 个 SN / 集中 HN 的弹出带宽限制）。

  用法示例：

```bash
CHI_ROUTING=xy python3 gen_chi_traffic.py && ../src/booksim chi_traffic
```

---

## 5. 验证结果（默认混合，LAMBDA=0.001，全部 drain）

各 class 的 accepted flit rate（throughput，flit/node/cycle）：

| 通道 | 合计吞吐 |
|---|---:|
| REQ | ~0.00113 |
| RSP | ~0.00173 |
| SNP | ~0.00017 |
| **DAT** | **~0.00176** |

默认采用 `CHI_DATA_FLITS=2`，对应用户表里的 DAT=2 口径；如改成 5，DAT 通道压力会显著增加。

BookSim 验证点：

- `chi_traffic.log` 中解析出 `Node 168 Router 1`、`Node 169 Router 2`、
  `Node 170 Router 4`、`Node 171 Router 5`。
- 4 个 `router to router listing` 对应 4 个物理子网。
- 出现 `====== Overall Traffic Statistics ======`，无 `unstable` / `exceeded`，说明默认混合能完整 drain。
- `class_source` 已生效：例如 `CompData_DMT` 为 `SN->RN`，其 injected max node 落在 SN node 169。
- 默认比例下 `CHI_LAMBDA=0.0010` 可 drain。

---

## 6. 局限

- 已支持按 RN/HN/SN 角色门控源（`class_source`），但同一角色内仍是随机/均匀注入；
  例如 `SN->RN` 可以保证只从 SN 节点注入，但不会绑定某个具体 SN 与某个具体 RN 的事务关系。
- **开环、无真正事务因果**：用权重比例近似各消息类型的相对频率，不复现一致性状态机。
- DCT 的 `RN-B -> RN-A` 用 `RN -> RN` 角色级流量近似，不能保证源 RN 和目的 RN 不同或来自同一 cache line。
- 需要完整 CHI 协议事务级仿真请用 gem5 Ruby + Garnet（自带 CHI 实现）。

---

## 7. 相关文件

| 文件 | 作用 |
|---|---|
| `runfiles/gen_chi_traffic.py` | 消息类型表 + 流量文件生成器（本文主角） |
| `runfiles/chi_traffic[_anynet]` | 生成的配置 / 拓扑 |
| `runfiles/chi_traffic.log` | 示例仿真输出 |
| `src/*`（class_subnet 补丁） | 让通道按 class 映射到子网的前置依赖 |
