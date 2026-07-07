# sn_local_stats.m 解读说明

本目录存放 `sweep_sn_local_peak.py` 在每条 CSV 记录对应的最佳 λ 下，BookSim `stats_out` 写出的原始 MATLAB 统计文件。

文件名格式：

```
{mix}_buf{vc_buf}_D{data_flits}_lam{lambda}_sn_local_stats.m
```

示例：`write_buf8_D2_lam0p05_sn_local_stats.m` = 写 ceiling、vc_buf=8、DATA_FLITS=2、λ=0.05。

与汇总表 `../v6_repair_sn_local_peak.csv` 的 `stats_file` 列一一对应。

---

## 1. 文件从哪来

BookSim 在 `chi_traffic` 里设置：

```
stats_out = sn_local_stats.m;
```

仿真在 **warmup 结束后的测量窗口** 内累计计数；若 `latency_thres` 触发 abort，则在 abort 时刻调用 `WriteStats()` 写出本文件。

每个 flit 速率 = 窗口内累计 flit 数 ÷ `(drain_time - reset_time)`，单位 **flit/cycle**。

---

## 2. 文件结构

| 区域 | 内容 |
|------|------|
| 开头 `%` 注释行 | 当时仿真配置快照（buf、λ、routing 等） |
| `%=================================` 分隔块 | 每个 traffic class 一组统计 |
| 每 class | `plat`/`nlat` 延迟、`sent_flits`/`accepted_flits` 等 |

**MATLAB 下标从 1 开始**：文件里的 `sent_flits(3,:)` 对应 BookSim 配置注释里的 **c2**（class id = 下标 − 1）。

---

## 3. 节点下标

`sent_flits(c,:)` / `accepted_flits(c,:)` 是长度 **172** 的向量，**数组下标 = node ID**（0-based）。

CHI 6×7 mesh 上 4 个 SN（DDR）节点：

| Node ID | 位置 |
|---------|------|
| 168 | R1 |
| 169 | R2 |
| 170 | R4 |
| 171 | R5 |

看 SN 终端利用率时，只取这 4 个下标的数值。

---

## 4. sent_flits vs accepted_flits

| 列 | 含义 |
|----|------|
| `sent_flits(c, n)` | class c 的 flit 从节点 n **注入网络**（离开 terminal） |
| `accepted_flits(c, n)` | class c 的 flit **到达节点 n 并被接收**（进入 terminal） |

- **读 DAT（CompData，SN→RN）**：瓶颈看 SN **inject** → `sent_flits` @ SN
- **写 DAT（L3EvictData，HN→SN）**：瓶颈看 SN **eject** → `accepted_flits` @ SN
- **REQ→SN**：看 SN 侧 `accepted_flits`

很多位置为 0 是正常的：`class_source` 限制只有部分节点能 inject 某 class。

---

## 5. 如何找 class 编号

打开**同一次运行**生成的 `chi_traffic`（或看 stats 文件头部 `%class_subnet` / 注释），查 `// class ->` 行，例如写 ceiling：

```
c4  ... REQ HN->SN   (L3EvictReq)   → MATLAB index 5, SN peak 用 accepted_flits(5,:)
c5  ... DAT HN->SN   (L3EvictData)  → MATLAB index 6, SN peak 用 accepted_flits(6,:)
```

读 ceiling（class 更少）示例：

```
c1  ... REQ HN->SN   → accepted_flits(2,:) @ SN
c2  ... DAT SN->RN   (CompData_DMT) → sent_flits(3,:) @ SN
```

`sweep_sn_local_peak.csv` 的 `dat_class` / `req_sn_class` 列给出 BookSim **0-based** class id；MATLAB 行号 = class id + 1。

---

## 6. SN local peak 怎么算

对目标 class 的 SN 四个节点取值，再：

- **peak** = `max(四个 SN 值)`
- **avg** = 四个 SN 值的算术平均

脚本里的 peak **不是**时间轴瞬时最大值，而是测量窗口内 **4 个 SN 里利用率最高的那条终端 link**。

相对单 link 容量 1.0 flit/cycle：0.911 ≈ 91.1% 利用率。

---

## 7. 快速 grep / Python 示例

```bash
# 写 DAT c5 → MATLAB 第 6 行（以你那次 chi_traffic 注释为准）
grep 'accepted_flits(6,:)' write_buf8_D2_lam0p05_sn_local_stats.m | tail -c 80
```

```python
import re
SN = (168, 169, 170, 171)
txt = open("write_buf8_D2_lam0p05_sn_local_stats.m").read()
m = re.search(r"accepted_flits\(6,:\)\s*=\s*\[([^\]]+)\]", txt)
v = [float(x) for x in m.group(1).split()]
sn = [v[i] for i in SN]
print("SN accepted flit/cycle:", sn, "peak:", max(sn))
```

---

## 8. 与 E2E 指标的区别

| 指标 | 来源 | 含义 |
|------|------|------|
| **SN local DAT** | 本目录 `.m` 文件 | 仅 SN 终端 inject/eject |
| **E2E DAT util** | BookSim stdout Overall / DisplayStats | 全网聚合后的端到端 DAT 吞吐 |

读路径常见：SN local DAT > E2E DAT → 瓶颈在 SN 之后的 mesh fan-out，而非 SN 终端本身。

写路径常见：两者接近 → SN 终端 link 即瓶颈。

REQ 与 DAT 分属不同 subnet（`subnets=4`），统计独立，不存在仿真内的 REQ→DAT 因果阻塞。

---

## 9. 重跑并更新本目录

```bash
cd booksim2/runfiles
python3 sweep_sn_local_peak.py
```

输出：`../doc/v6_repair_sn_local_peak.csv` + 本目录下 4 个 `.m` 文件（buf 2/8 × read/write）。
