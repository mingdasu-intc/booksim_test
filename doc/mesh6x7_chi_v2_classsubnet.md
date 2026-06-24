# 6x7 Mesh + CHI 建模 V2：按 class 分子网（class_subnet 补丁）

> V1（基于 BookSim 原生消息类型的 4 子网映射）见
> [`mesh6x7_chi_4channel.md`](mesh6x7_chi_4channel.md)，**保留不动**。
> 本文是 V2：通过一处源码补丁让 subnet 直接按 traffic class 选，从而把
> CHI 的 4 条通道与 BookSim 的"读/写消息类型"彻底解耦，并能建模**写一致性请求**。

---

## 1. 为什么需要 V2

V1 把 CHI 的 REQ/DAT/SNP/RSP 一一映射到 BookSim 仅有的 4 种内置消息类型
（read_request/read_reply/write_request/write_reply），再靠 `*_subnet` 把 4 种类型
分到 4 个 subnet。这有个硬限制：

- **4 种类型被通道占满**，没有第 5 种类型来区分"这是一笔写事务"。
- BookSim 的 `read_reply`（DAT 通道）天生只会 `HN→RN`，而 **CHI 写数据要 `RN→HN`**，
  方向反了也插不进去。

结论：V1 本质是"读一致性 + snoop"模型，**装不下写一致性请求**。

## 2. 补丁：让 subnet 按 class 选，而不是按消息类型

BookSim 原本在 `trafficmanager.cpp` 里这样选 subnet：

```
subnet = (packet_type == ANY_TYPE) ? RandomInt(subnets-1) : _subnet[packet_type];
```

即"按消息类型选"或"随机"。补丁新增一个可选的 `class_subnet` 数组，非空时**按 class 选**：

改动文件（共约 5 行）：

| 文件 | 改动 |
|---|---|
| `src/booksim_config.cpp` | 新增 `AddStrField("class_subnet", "")`（默认空，不影响旧配置） |
| `src/trafficmanager.hpp` | 新增成员 `vector<int> _class_subnet;` |
| `src/trafficmanager.cpp` | 构造函数解析 `_class_subnet = config.GetIntArray("class_subnet")` |
| `src/trafficmanager.cpp` | subnet 选择改为：`_class_subnet` 非空时用 `_class_subnet[cl]`，否则退回原逻辑 |

核心逻辑：

```cpp
int subnetwork;
if (!_class_subnet.empty()) {
    subnetwork = _class_subnet[cl];                       // 按 class 选 subnet
} else {
    subnetwork = (packet_type == Flit::ANY_TYPE) ?
                 RandomInt(_subnets-1) : _subnet[packet_type];
}
```

> 向后兼容：不写 `class_subnet` 时行为与原版完全一致，V1 及所有旧配置不受影响。
> 改完需在 `src/` 下 `make` 重新编译。

## 3. V2 模型：4 通道 = 4 子网 + 可建模写

每条 CHI 通道 = 一个**开环**（`use_read_write=0`）traffic class，经 `class_subnet`
映射到自己的 subnet。DAT 通道是**双向**的，所以拆成两条流共享同一个 DAT 子网：

| class | 通道 | subnet | size | 目的(方向近似) |
|---|---|---|---|---|
| c0 | REQ | 0 | 1 | HN（读+写请求，RN→HN） |
| c1 | DAT (读数据) | 1 | 5 | RN（HN→RN） |
| c2 | SNP | 2 | 1 | RN（→RN） |
| c3 | RSP | 3 | 1 | HN（响应/Comp，→HN） |
| **c4** | **DAT (写数据)** | **1** | **5** | **HN（RN→HN，写一致性数据）** |

**c4 就是 V1 装不下的写一致性数据流**——5-flit 的 cache line 沿 `RN→HN` 方向跑在
DAT 子网上，和读数据 c1 共享同一张物理 DAT 网（贴合真实 CHI 的双向 DAT）。

### 速率比模型（开环近似因果关系）

没有了 `use_read_write` 的自动请求-应答配对，用注入率比例近似事务因果：

```
base req = INJ
DAT_rd = req*(1-wf)        # 每个读请求触发一个读数据
DAT_wr = req*wf            # 每个写请求触发一个写数据
SNP    = req*snoop_factor
RSP    = req*snoop_factor + req*wf   # snoop 响应 + 写完成
```

可调参数（`gen_chi_mesh_v2.py` 顶部或环境变量）：`CHI_INJ` / `CHI_SNOOP` /
`CHI_WFRAC`（写占比，默认 0.3）/ `CHI_VCS`。

## 4. 验证结果

**补丁正确性**：最小用例 `test_class_subnet`（4 class / 4 subnet / 1-flit / uniform，
每 class 独占一个 subnet）在 INJ=0.01 下完全 drain（注入≈接受=0.0099，全 1-flit），
证明 subnet 按 class 选生效。

**V2 模型**（INJ=0.001, snoop=1.0, write_fraction=0.3，全部 drain）：

| class | 通道 | 平均包延迟(cyc) | 包长 | 接受 flit 率 |
|---|---|---:|---:|---:|
| c0 | REQ | 34.5 | 1 | 0.00103 |
| c1 | DAT 读 | 48.1 | 5 | 0.00348 |
| c2 | SNP | 34.7 | 1 | ~0.001 |
| c3 | RSP | 35.2 | 1 | 0.00126 |
| **c4** | **DAT 写** | **46.3** | **5** | **0.00157** |

要点：
- **写数据流（c4）成功跑通**——这是 V2 相对 V1 的核心新增能力。
- **DAT 子网是瓶颈**：它独自承载 c1+c4 两条 5-flit 数据流（≈REQ 子网的 5 倍 flit 负载），
  所以 DAT 最先饱和。这其实是有意义的结论——4 条独立物理通道时，单一 DAT 网的带宽
  是系统瓶颈，正是 CHI 实现者关注的点。
- 注意本 anynet+min 路由的 6x7 网整体饱和点偏低（单子网 uniform 1-flit 在
  ~0.01–0.05 间就到膝点），所以 V2 默认工作点取得较低（INJ=0.001）。

## 5. V1 vs V2 对比

| | V1（消息类型映射） | V2（class_subnet 补丁） |
|---|---|---|
| subnet 选择依据 | BookSim 4 种消息类型 | traffic class（任意） |
| 是否改源码 | 否 | 是（约 5 行，向后兼容） |
| 请求-应答耦合 | 有（use_read_write 自动配对） | 无（开环，用速率比近似） |
| 通道数上限 | 最多 4（被类型卡死） | 任意（只受 subnet 数限制） |
| 能否建模**写数据 RN→HN** | **否** | **是** |
| DAT 双向 | 否（只 HN→RN） | 是（读+写共享 DAT 子网） |
| 适用 | 读一致性 + snoop 的快速近似 | 需要写事务 / 更灵活通道布局 |

## 6. 复现

```bash
# 1) 打补丁后重新编译（若尚未编译）
cd booksim2/src && make

# 2) 生成并运行 V2
cd ../runfiles
python3 gen_chi_mesh_v2.py            # 生成 mesh6x7_chi_v2[_anynet]
../src/booksim mesh6x7_chi_v2

# 调参示例：写占比 0.5、snoop 2 倍
CHI_WFRAC=0.5 CHI_SNOOP=2 python3 gen_chi_mesh_v2.py && ../src/booksim mesh6x7_chi_v2

# 补丁自检
../src/booksim test_class_subnet
```

## 7. 相关文件

| 文件 | 作用 |
|---|---|
| `src/trafficmanager.{hpp,cpp}`, `src/booksim_config.cpp` | `class_subnet` 补丁 |
| `runfiles/gen_chi_mesh_v2.py` | V2 拓扑 + 配置生成器 |
| `runfiles/mesh6x7_chi_v2[_anynet]` | 生成的配置 / 拓扑 |
| `runfiles/test_class_subnet` | 补丁最小自检用例 |
| `runfiles/mesh6x7_chi_v2.log` | V2 仿真输出 |

## 8. 局限（仍然存在）

- 开环模型**没有真正的事务因果**，靠速率比近似；不复现一致性状态机。
- BookSim 所有节点都按每-class 速率注入，**无法按 RN/HN 角色门控源**（方向只能靠
  目的集合近似）。
- 若要完整 CHI 协议事务级仿真（目录态、snoop filter、真实写流水），仍建议
  gem5 Ruby + Garnet（自带 CHI 实现）。
