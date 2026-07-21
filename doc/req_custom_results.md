# REQ-only 定制流量仿真（req_custom）

单点仿真：仅 REQ 通道，指定 RN→HN，`link_latency=1`，每源 RN `injection_rate=0.2`。

## 配置

| 项 | 值 |
|----|-----|
| 拓扑 | 7×6 mesh（与 ZCN-LP 相同，含 4 个侧边 SN，本 mix 不使用 SN） |
| 路由 | `xy` |
| `link_latency` | **1** |
| `vc_buf_size` | 4 |
| `num_vcs` | 2 |
| 通道 | **仅 REQ**（`class_subnet={0}`），`packet_size=1` |
| 注入 | 每源 RN **0.2** pkt/cycle |

### 发送端（8 个 RN）

| Router | RN 数量 | Node ID |
|--------|---------|---------|
| R4 | 2 | 16, 17 |
| R5 | 2 | 20, 21 |
| R13 | 1 | 52 |
| R14 | 1 | 56 |
| R15 | 1 | 60 |
| R16 | 1 | 64 |

### 接收端（16 个 HN）

“一个 HN”统一取该 router 的 **第一个 HN**（`base+2`）；R4 取两个 HN（`base+2`, `base+3`）。

| Router | HN 数量 | Node ID |
|--------|---------|---------|
| R3 | 1 | 14 |
| R4 | 2 | 18, 19 |
| R5 | 1 | 22 |
| R13–R16 | 各 1 | 54, 58, 62, 66 |
| R25–R28 | 各 1 | 102, 106, 110, 114 |
| R37–R40 | 各 1 | 150, 154, 158, 162 |

流量：`hotspot` 均匀打到上述 16 个 HN。

## 如何复现

```bash
cd booksim2/runfiles
python3 gen_req_custom_traffic.py          # 生成 chi_traffic + chi_traffic_anynet
../src/booksim chi_traffic | tee ../doc/req_custom_booksim.log
```

可选覆盖：`CHI_LINK_LATENCY`、`CUSTOM_INJ` / `CHI_LAMBDA`、`CHI_VC_BUF_SIZE`、`CHI_ROUTING`。

生成脚本：[`../runfiles/gen_req_custom_traffic.py`](../runfiles/gen_req_custom_traffic.py)

## 结果摘要（已收敛 `ok`）

| 指标 | 值 |
|------|-----|
| Packet latency | **28.4** cycles |
| Flit latency | 28.5 cycles |
| 平均 hops | 5.00 |
| 源端 sent 合计 | 1.581 flit/cycle |
| 源端 sent 平均 / 源 | **0.198**（接近配置 0.2） |
| 源端 sent 范围 | 0.189 – 0.209 |
| 目的端 accepted 合计 | 1.589 flit/cycle |
| 目的端 accepted 平均 / 目的 | **0.099**（≈ 1.58/16） |
| 目的端 accepted 范围 | 0.089 – 0.112 |

源端注入接近设定值 0.2，说明在该负载下源注入队列基本未堵死；目的端约按 16 路均分，单 HN ~0.1 flit/cycle。

## 产物

| 文件 | 说明 |
|------|------|
| `req_custom_summary.csv` | 汇总指标 |
| `req_custom_per_node.csv` | 各源/目的节点 sent / accepted |
| `req_custom_stats.m` | BookSim `stats_out` |
| `req_custom_booksim.log` | 完整仿真日志 |
| `req_custom_chi_traffic` | 当时使用的配置备份 |
| `req_custom_chi_traffic_anynet` | 拓扑备份 |
