#!/usr/bin/env python3
"""Generate a BookSim traffic config for a CHI coherent workload.

The model is scenario-table driven. Requests are split into four large
categories (read/write/dataless/cmo). Each category contains subtypes, and each
subtype expands through mutually exclusive CHI-like scenarios. The L3 cache is
integrated in HN-F, SN-F is an independent memory-controller node, and SN-F only
participates on L3 miss, asynchronous L3 eviction, or CleanInvalid dirty
writeback.

BookSim has no trace-injection mode; the importable "traffic file" is a config
with synthetic traffic classes. Each generated message in a flow becomes one
BookSim traffic class mapped to a CHI channel subnet via the class_subnet patch.
"""
import os

# ----- topology knobs -----
ROWS = int(os.environ.get("CHI_ROWS", 7))
COLS = int(os.environ.get("CHI_COLS", 6))
RN_PER, HN_PER = 2, 2
FLIT_BYTES   = 16          # network flit width
LINE_BYTES   = 64          # cache line

def _parse_sn_coords(s):
    """Parse CHI_SN_COORDS like '3,0;4,0;3,5;4,5' -> list of (row,col)."""
    if not s:
        return None
    out = []
    for part in s.replace(" ", "").split(";"):
        if not part:
            continue
        r, c = part.split(",")
        out.append((int(r), int(c)))
    return out

_sn_env = _parse_sn_coords(os.environ.get("CHI_SN_COORDS", ""))
SN_ROUTER_COORDS = _sn_env if _sn_env else [(3, 0), (4, 0), (3, 5), (4, 5)]
NUM_VCS      = int(os.environ.get("CHI_VCS", 2))
VC_BUF_SIZE  = int(os.environ.get("CHI_VC_BUF_SIZE", 2))
SW_ALLOCATOR = os.environ.get("CHI_SW_ALLOCATOR", "separable_output_first(round_robin)")
VC_ALLOCATOR = os.environ.get("CHI_VC_ALLOCATOR", "islip")
# routing base name: "min" = Dijkstra minimal table (default), "xy" = XY
# dimension-order. BookSim appends "_anynet" to form the routing function name.
ROUTING      = os.environ.get("CHI_ROUTING", "min")
# inter-router (router<->router) link latency in cycles. anynet stores this per
# directed link in the topology file (default 1 when omitted); we emit all four
# neighbours with the weight so the latency is symmetric in both directions.
LINK_LAT     = int(os.environ.get("CHI_LINK_LATENCY", 1))
# Router pipeline delays (BookSim defaults: RC=1 VA=1 SA=1 ST=1 → 4-cycle router).
# Note: BookSim forbids vc_alloc_delay=0 and sw_alloc_delay=0.
# For ~1-cycle router on REQ custom, see gen_req_custom_traffic.py
# (speculative=1, RC=0, VA=1, SA=1, ST=0).
SPECULATIVE      = int(os.environ.get("CHI_SPECULATIVE", 0))
ROUTING_DELAY    = int(os.environ.get("CHI_ROUTING_DELAY", 1))
VC_ALLOC_DELAY   = int(os.environ.get("CHI_VC_ALLOC_DELAY", 1))
SW_ALLOC_DELAY   = int(os.environ.get("CHI_SW_ALLOC_DELAY", 1))
ST_PREPARE_DELAY = int(os.environ.get("CHI_ST_PREPARE_DELAY", 0))
ST_FINAL_DELAY   = int(os.environ.get("CHI_ST_FINAL_DELAY", 1))
# sim convergence controls: raising these lets a near-saturation point still
# produce steady-state stats instead of aborting on the default 500-cycle guard.
# format as float so BookSim parses latency_thres as a float field
LATENCY_THRES = repr(float(os.environ.get("CHI_LATENCY_THRES", 500.0)))
MAX_SAMPLES   = int(os.environ.get("CHI_MAX_SAMPLES", 50))
STATS_OUT     = os.environ.get("CHI_STATS_OUT", "sn_local_stats.m")

# ----- transaction mix knobs -----
# CHI_LAMBDA is total transaction-start rate per node. Category, subtype, and
# scenario ratios are normalized, so they do not need to sum to 1.
LAMBDA = float(os.environ.get("CHI_LAMBDA", 0.001))

CATEGORY_RATIO = {
    "read":     float(os.environ.get("CHI_READ_RATIO", 55)),
    "write":    float(os.environ.get("CHI_WRITE_RATIO", 30)),
    "dataless": float(os.environ.get("CHI_DATALESS_RATIO", 10)),
    "cmo":      float(os.environ.get("CHI_CMO_RATIO", 5)),
}

SUBTYPE_RATIO = {
    "read": {
        "ReadShared": float(os.environ.get("CHI_READ_SHARED_RATIO", 70)),
        "ReadUnique": float(os.environ.get("CHI_READ_UNIQUE_RATIO", 25)),
        "ReadNoSnp":  float(os.environ.get("CHI_READ_NOSNP_RATIO", 5)),
    },
    "write": {
        "WriteUnique": float(os.environ.get("CHI_WRITE_UNIQUE_RATIO", 45)),
        "WriteBack":   float(os.environ.get("CHI_WRITE_BACK_RATIO", 25)),
        "WriteClean":  float(os.environ.get("CHI_WRITE_CLEAN_RATIO", 15)),
        "WriteEvict":  float(os.environ.get("CHI_WRITE_EVICT_RATIO", 15)),
    },
    "dataless": {
        "CleanUnique": float(os.environ.get("CHI_CLEAN_UNIQUE_RATIO", 55)),
        "MakeUnique":  float(os.environ.get("CHI_MAKE_UNIQUE_RATIO", 45)),
    },
    "cmo": {
        "CleanShared":  float(os.environ.get("CHI_CMO_CLEAN_SHARED_RATIO", 35)),
        "CleanInvalid": float(os.environ.get("CHI_CMO_CLEAN_INVALID_RATIO", 35)),
        "MakeInvalid":  float(os.environ.get("CHI_CMO_MAKE_INVALID_RATIO", 30)),
    },
}

# Scenario ratios. These describe mutually exclusive paths from the user's CHI
# flow table, not independent additive factors.
READ_SCENARIO_RATIO = {
    "l3_hit":   float(os.environ.get("CHI_READ_L3_HIT_RATIO", 70)),
    "dmt_miss": float(os.environ.get("CHI_READ_DMT_MISS_RATIO", 20)),
    "dct":      float(os.environ.get("CHI_READ_DCT_RATIO", 10)),
}
READ_NOSNP_SCENARIO_RATIO = {
    "l3_hit":   float(os.environ.get("CHI_READ_NOSNP_L3_HIT_RATIO", 75)),
    "dmt_miss": float(os.environ.get("CHI_READ_NOSNP_DMT_MISS_RATIO", 25)),
}
WRITE_UNIQUE_SCENARIO_RATIO = {
    "no_sharer":    float(os.environ.get("CHI_WU_NO_SHARER_RATIO", 60)),
    "clean_sharer": float(os.environ.get("CHI_WU_CLEAN_SHARER_RATIO", 30)),
    "dirty_sharer": float(os.environ.get("CHI_WU_DIRTY_SHARER_RATIO", 10)),
}
WRITE_EVICT_SCENARIO_RATIO = {
    "accept": float(os.environ.get("CHI_WE_ACCEPT_RATIO", 70)),
    "reject": float(os.environ.get("CHI_WE_REJECT_RATIO", 30)),
}
DATALLESS_SCENARIO_RATIO = {
    "no_sharer":    float(os.environ.get("CHI_DATALESS_NO_SHARER_RATIO", 60)),
    "clean_sharer": float(os.environ.get("CHI_DATALESS_CLEAN_SHARER_RATIO", 30)),
    "dirty_sharer": float(os.environ.get("CHI_DATALESS_DIRTY_SHARER_RATIO", 10)),
}
CMO_SCENARIO_RATIO = {
    "l3_clean":      float(os.environ.get("CHI_CMO_L3_CLEAN_RATIO", 60)),
    "clean_sharer": float(os.environ.get("CHI_CMO_CLEAN_SHARER_RATIO", 30)),
    "dirty_sharer": float(os.environ.get("CHI_CMO_DIRTY_SHARER_RATIO", 10)),
}
L3_EVICT_TO_SN_RATE = float(os.environ.get("CHI_L3_EVICT_TO_SN_RATE", 0.20))

# Use the user's CHI channel accounting by default: each data transfer consumes
# 2 DAT flits/beats. Override CHI_DATA_FLITS=5 to model 64B over a 16B network
# flit plus header, as in the earlier bandwidth-oriented model.
DATA_FLITS = int(os.environ.get("CHI_DATA_FLITS", 2))
CTRL_FLITS = 1

CHANNEL_SUBNET = {"REQ": 0, "RSP": 1, "SNP": 2, "DAT": 3}

D, C = DATA_FLITS, CTRL_FLITS

here = os.path.dirname(os.path.abspath(__file__))

def rid(r, c):
    return r * COLS + c

PER = RN_PER + HN_PER
n_routers = ROWS * COLS
sn_routers = [rid(r, c) for r, c in SN_ROUTER_COORDS]
rn_nodes, hn_nodes, sn_nodes = [], [], []
for i in range(n_routers):
    base = PER * i
    rn_nodes += [base + k for k in range(RN_PER)]
    hn_nodes += [base + RN_PER + k for k in range(HN_PER)]
sn_base = n_routers * PER
for idx, _router in enumerate(sn_routers):
    sn_nodes.append(sn_base + idx)
total_nodes = n_routers * PER + len(sn_nodes)
role_set = {"RN": rn_nodes, "HN": hn_nodes, "SN": sn_nodes}

# ---- topology ----
lines = []
for r in range(ROWS):
    for c in range(COLS):
        i = rid(r, c)
        base = PER * i
        parts = [f"router {i}"] + [f"node {base + k}" for k in range(PER)]
        if i in sn_routers:
            parts.append(f"node {sn_nodes[sn_routers.index(i)]}")
        # list all four mesh neighbours with the link weight so router<->router
        # latency is symmetric (anynet router-router latency is per-directed-link).
        for nb in ((rid(r, c + 1) if c + 1 < COLS else None),   # east
                   (rid(r, c - 1) if c - 1 >= 0 else None),     # west
                   (rid(r + 1, c) if r + 1 < ROWS else None),   # south
                   (rid(r - 1, c) if r - 1 >= 0 else None)):    # north
            if nb is not None:
                parts.append(f"router {nb} {LINK_LAT}")
        lines.append(" ".join(parts))
topo_path = os.path.join(here, "chi_traffic_anynet")
with open(topo_path, "w") as f:
    f.write("\n".join(lines) + "\n")

def vec(xs):
    return "{" + ",".join(map(str, xs)) + "}"

def normalize(weights):
    total = sum(max(v, 0.0) for v in weights.values())
    if total <= 0.0:
        raise ValueError(f"Invalid all-zero weights: {weights}")
    return {k: max(v, 0.0) / total for k, v in weights.items()}

def clamp01(v):
    return min(1.0, max(0.0, v))

cat_share = normalize(CATEGORY_RATIO)
sub_share = {cat: normalize(vals) for cat, vals in SUBTYPE_RATIO.items()}
read_scenario_share = normalize(READ_SCENARIO_RATIO)
read_nosnp_scenario_share = normalize(READ_NOSNP_SCENARIO_RATIO)
wu_scenario_share = normalize(WRITE_UNIQUE_SCENARIO_RATIO)
we_scenario_share = normalize(WRITE_EVICT_SCENARIO_RATIO)
dataless_scenario_share = normalize(DATALLESS_SCENARIO_RATIO)
cmo_scenario_share = normalize(CMO_SCENARIO_RATIO)
l3_evict_to_sn = clamp01(L3_EVICT_TO_SN_RATE)

messages = []

def add(category, subtype, message, channel, src, dst, size, rate, note=""):
    if rate <= 0.0:
        return
    messages.append({
        "category": category,
        "subtype": subtype,
        "message": message,
        "channel": channel,
        "src": src,
        "dst": dst,
        "size": size,
        "rate": rate,
        "note": note,
    })

# ---- scenario helpers from the user-provided CHI flow table ----
def flow_read_l3_hit(category, subtype, r):
    txn = subtype.split(".")[0]
    add(category, subtype, txn, "REQ", "RN", "HN", C, r, "RN request to HN/L3")
    add(category, subtype, "CompData_L3Hit", "DAT", "HN", "RN", D, r, "L3 data")
    add(category, subtype, "CompAck", "RSP", "RN", "HN", C, r, "requester ack")

def flow_read_dmt(category, subtype, r):
    txn = subtype.split(".")[0]
    add(category, subtype, txn, "REQ", "RN", "HN", C, r, "RN request to HN")
    add(category, subtype, "ReadNoSnp_DMT", "REQ", "HN", "SN", C, r, "HN forwards to SN")
    add(category, subtype, "CompData_DMT", "DAT", "SN", "RN", D, r, "SN direct data to RN")
    add(category, subtype, "ReadReceipt", "RSP", "SN", "HN", C, r, "SN receipt to HN")
    add(category, subtype, "CompAck", "RSP", "RN", "HN", C, r, "requester ack")

def flow_read_dct(category, subtype, r):
    txn = subtype.split(".")[0]
    add(category, subtype, txn, "REQ", "RN", "HN", C, r, "request to HN/SF")
    add(category, subtype, "SnpFwd", "SNP", "HN", "RN", C, r, "forwarding snoop")
    add(category, subtype, "CompData_DCT", "DAT", "RN", "RN", D, r, "owner/sharer direct data")
    add(category, subtype, "SnpRespFwded", "RSP", "RN", "HN", C, r, "snoop forwarded response")
    add(category, subtype, "Comp", "RSP", "HN", "RN", C, r, "HN completion")
    add(category, subtype, "CompAck", "RSP", "RN", "HN", C, r, "requester ack")

def flow_write_data(category, subtype, r, message):
    txn = subtype.split(".")[0]
    add(category, subtype, txn, "REQ", "RN", "HN", C, r, "write request")
    add(category, subtype, "DBIDResp", "RSP", "HN", "RN", C, r, "data buffer grant")
    add(category, subtype, message, "DAT", "RN", "HN", D, r, "write data to HN/L3")
    add(category, subtype, "Comp", "RSP", "HN", "RN", C, r, "write completion")

def flow_l3_evict_to_sn(category, subtype, r):
    add(category, subtype, "L3EvictReq", "REQ", "HN", "SN", C, r, "async dirty L3 eviction")
    add(category, subtype, "L3EvictData", "DAT", "HN", "SN", D, r, "dirty data to SN")
    add(category, subtype, "L3EvictComp", "RSP", "SN", "HN", C, r, "SN write completion")

def flow_invalidate_clean(category, subtype, r):
    add(category, subtype, "SnpMakeInvalid", "SNP", "HN", "RN", C, r, "invalidate clean sharer")
    add(category, subtype, "SnpResp_I", "RSP", "RN", "HN", C, r, "clean invalidated")

def flow_invalidate_dirty(category, subtype, r):
    add(category, subtype, "SnpMakeInvalid", "SNP", "HN", "RN", C, r, "invalidate dirty sharer")
    add(category, subtype, "SnpRespData_I", "DAT", "RN", "HN", D, r, "dirty data to HN/L3")
    add(category, subtype, "SnpResp_I_Ctrl", "RSP", "RN", "HN", C, r, "dirty response control")

def flow_dataless_base(category, subtype, r):
    txn = subtype.split(".")[0]
    add(category, subtype, txn, "REQ", "RN", "HN", C, r, "dataless request")
    add(category, subtype, "Comp", "RSP", "HN", "RN", C, r, "completion")
    add(category, subtype, "CompAck", "RSP", "RN", "HN", C, r, "completion ack")

# ---- expand complete flows from transaction categories/subtypes ----
for subtype, share in sub_share["read"].items():
    r = LAMBDA * cat_share["read"] * share
    if subtype == "ReadNoSnp":
        flow_read_l3_hit("read", subtype + ".l3_hit", r * read_nosnp_scenario_share["l3_hit"])
        flow_read_dmt("read", subtype + ".dmt_miss", r * read_nosnp_scenario_share["dmt_miss"])
    else:
        flow_read_l3_hit("read", subtype + ".l3_hit", r * read_scenario_share["l3_hit"])
        flow_read_dmt("read", subtype + ".dmt_miss", r * read_scenario_share["dmt_miss"])
        flow_read_dct("read", subtype + ".dct", r * read_scenario_share["dct"])

for subtype, share in sub_share["write"].items():
    r = LAMBDA * cat_share["write"] * share
    if subtype == "WriteUnique":
        flow_write_data("write", "WriteUnique.no_sharer",
                        r * wu_scenario_share["no_sharer"], "WriteData")
        rc = r * wu_scenario_share["clean_sharer"]
        add("write", "WriteUnique.clean_sharer", "WriteUnique", "REQ", "RN", "HN", C, rc)
        flow_invalidate_clean("write", "WriteUnique.clean_sharer", rc)
        add("write", "WriteUnique.clean_sharer", "DBIDResp", "RSP", "HN", "RN", C, rc)
        add("write", "WriteUnique.clean_sharer", "WriteData", "DAT", "RN", "HN", D, rc)
        add("write", "WriteUnique.clean_sharer", "Comp", "RSP", "HN", "RN", C, rc)
        rd = r * wu_scenario_share["dirty_sharer"]
        add("write", "WriteUnique.dirty_sharer", "WriteUnique", "REQ", "RN", "HN", C, rd)
        flow_invalidate_dirty("write", "WriteUnique.dirty_sharer", rd)
        add("write", "WriteUnique.dirty_sharer", "DBIDResp", "RSP", "HN", "RN", C, rd)
        add("write", "WriteUnique.dirty_sharer", "WriteData", "DAT", "RN", "HN", D, rd)
        add("write", "WriteUnique.dirty_sharer", "Comp", "RSP", "HN", "RN", C, rd)
    elif subtype == "WriteBack":
        flow_write_data("write", "WriteBack.l3_accept", r, "CopyBackWriteData")
        flow_l3_evict_to_sn("write", "WriteBack.async_l3_evict", r * l3_evict_to_sn)
    elif subtype == "WriteClean":
        flow_write_data("write", "WriteClean.l3_hit", r, "WriteData")
    elif subtype == "WriteEvict":
        flow_write_data("write", "WriteEvict.accept", r * we_scenario_share["accept"], "WriteData")
        rr = r * we_scenario_share["reject"]
        add("write", "WriteEvict.reject", "WriteEvict", "REQ", "RN", "HN", C, rr)
        add("write", "WriteEvict.reject", "CompReject", "RSP", "HN", "RN", C, rr)
    else:
        raise ValueError(f"Unsupported write subtype: {subtype}")

for subtype, share in sub_share["dataless"].items():
    r = LAMBDA * cat_share["dataless"] * share
    flow_dataless_base("dataless", subtype + ".no_sharer",
                       r * dataless_scenario_share["no_sharer"])
    rc = r * dataless_scenario_share["clean_sharer"]
    add("dataless", subtype + ".clean_sharer", subtype, "REQ", "RN", "HN", C, rc)
    flow_invalidate_clean("dataless", subtype + ".clean_sharer", rc)
    add("dataless", subtype + ".clean_sharer", "Comp", "RSP", "HN", "RN", C, rc)
    add("dataless", subtype + ".clean_sharer", "CompAck", "RSP", "RN", "HN", C, rc)
    rd = r * dataless_scenario_share["dirty_sharer"]
    add("dataless", subtype + ".dirty_sharer", subtype, "REQ", "RN", "HN", C, rd)
    flow_invalidate_dirty("dataless", subtype + ".dirty_sharer", rd)
    add("dataless", subtype + ".dirty_sharer", "Comp", "RSP", "HN", "RN", C, rd)
    add("dataless", subtype + ".dirty_sharer", "CompAck", "RSP", "RN", "HN", C, rd)

for subtype, share in sub_share["cmo"].items():
    r = LAMBDA * cat_share["cmo"] * share
    rl = r * cmo_scenario_share["l3_clean"]
    add("cmo", subtype + ".l3_clean", subtype, "REQ", "RN", "HN", C, rl)
    add("cmo", subtype + ".l3_clean", "Comp", "RSP", "HN", "RN", C, rl)
    rc = r * cmo_scenario_share["clean_sharer"]
    add("cmo", subtype + ".clean_sharer", subtype, "REQ", "RN", "HN", C, rc)
    add("cmo", subtype + ".clean_sharer", "SnpClean", "SNP", "HN", "RN", C, rc)
    add("cmo", subtype + ".clean_sharer", "SnpResp", "RSP", "RN", "HN", C, rc)
    add("cmo", subtype + ".clean_sharer", "Comp", "RSP", "HN", "RN", C, rc)
    rd = r * cmo_scenario_share["dirty_sharer"]
    add("cmo", subtype + ".dirty_sharer", subtype, "REQ", "RN", "HN", C, rd)
    if subtype == "MakeInvalid":
        add("cmo", subtype + ".dirty_sharer", "SnpMakeInvalid", "SNP", "HN", "RN", C, rd)
        add("cmo", subtype + ".dirty_sharer", "SnpResp_I", "RSP", "RN", "HN", C, rd)
        add("cmo", subtype + ".dirty_sharer", "Comp", "RSP", "HN", "RN", C, rd)
    elif subtype == "CleanInvalid":
        add("cmo", subtype + ".dirty_sharer", "SnpCleanInvalid", "SNP", "HN", "RN", C, rd)
        add("cmo", subtype + ".dirty_sharer", "SnpRespData_I", "DAT", "RN", "HN", D, rd)
        add("cmo", subtype + ".dirty_sharer", "CleanInvalidWriteback", "DAT", "HN", "SN", D, rd)
        add("cmo", subtype + ".dirty_sharer", "Comp", "RSP", "HN", "RN", C, rd)
    else:
        add("cmo", subtype + ".dirty_sharer", "SnpCleanShared", "SNP", "HN", "RN", C, rd)
        add("cmo", subtype + ".dirty_sharer", "SnpRespData_SC", "DAT", "RN", "HN", D, rd)
        add("cmo", subtype + ".dirty_sharer", "Comp", "RSP", "HN", "RN", C, rd)

classes      = len(messages)
class_subnet = [CHANNEL_SUBNET[m["channel"]] for m in messages]
packet_size  = [m["size"] for m in messages]
use_rw       = [0] * classes

# --- per-source-node normalization -------------------------------------------
# BookSim's injection_rate is PER SOURCE NODE, and the total offered load of a
# class is injection_rate * (number of source nodes). LAMBDA is calibrated as a
# per-RN transaction-start rate, so a message's system-wide rate should be
# N_RN * r, spread over its own source set. Without this, an SN-sourced message
# (only 4 SN vs 84 RN) carries 84/4 = 21x too little traffic, so the data a SN
# emits (CompData_DMT) is grossly under-represented relative to the requests it
# receives. Scale each per-node rate by N_RN / N_source to conserve transaction
# counts. Disable with CHI_NODE_NORMALIZE=0 to reproduce the old (unbalanced)
# behavior.
NODE_NORMALIZE = os.environ.get("CHI_NODE_NORMALIZE", "1") not in ("0", "false", "False", "")
REF_SRC = len(rn_nodes)  # LAMBDA is per-RN (request initiator)


def norm_rate(m):
    r = m["rate"]
    if NODE_NORMALIZE:
        r = r * REF_SRC / len(role_set[m["src"]])
    return round(r, 10)


inj_rate     = [norm_rate(m) for m in messages]
traffic      = []
class_source = []
for m in messages:
    src_nodes = role_set[m["src"]]
    dst_nodes = role_set[m["dst"]]
    class_source.append("{" + ",".join(map(str, src_nodes)) + "}")
    # NOTE: double braces are required. BookSim's tokenize_str strips one brace
    # level, so hotspot({a,b,c}) collapses to params[0]=a (single hotspot). The
    # inner {{...}} keeps the whole node list as params[0] -> uniform over the set.
    traffic.append("hotspot({{" + ",".join(map(str, dst_nodes)) + "}})")

comment_rows = "\n".join(
    f"//   c{i:<2} {m['category']}.{m['subtype']}.{m['message']:<26} "
    f"{m['channel']:<3} {m['src']}->{m['dst']} size={m['size']} inj={inj_rate[i]}"
    for i, m in enumerate(messages))

sn_comment = ", ".join(
    f"R{router}=node{sn_nodes[idx]}@({SN_ROUTER_COORDS[idx][0]},{SN_ROUTER_COORDS[idx][1]})"
    for idx, router in enumerate(sn_routers)
)

cfg = f"""// CHI coherent-workload traffic file for BookSim (auto-generated by gen_chi_traffic.py).
// Requires the class_subnet source patch. Mix is generated from transaction categories.
// {n_routers} routers x {PER} RN/HN terminals + {len(sn_nodes)} DDR SN terminals = {total_nodes} nodes.
// SN placement: {sn_comment}.
// channels -> subnets: REQ=0 RSP=1 SNP=2 DAT=3 ; data={DATA_FLITS} flit, ctrl=1 flit.
// total transaction rate LAMBDA={LAMBDA}; scenario-table driven from CHI HN-F/L3/SF flows.
// node-count normalization = {NODE_NORMALIZE} (per-node inj scaled by N_RN/N_source; RN={len(rn_nodes)} HN={len(hn_nodes)} SN={len(sn_nodes)}).
// SN participates only in Read DMT miss, async L3 eviction, and CleanInvalid dirty writeback.
//
// class -> category.subtype.message:
{comment_rows}

topology     = anynet;
network_file = chi_traffic_anynet;
routing_function = {ROUTING};
anynet_cols  = {COLS};   // mesh width, used by xy_anynet to recover (row,col)

classes        = {classes};
use_read_write = {vec(use_rw)};
subnets        = 4;
class_subnet   = {vec(class_subnet)};   // REQ=0 RSP=1 SNP=2 DAT=3
class_source   = {{{','.join(class_source)}}};   // allowed source nodes per class
packet_size    = {vec(packet_size)};
injection_rate = {vec(inj_rate)};       // per-message rates derived from full flows
traffic        = {{{','.join(traffic)}}};

num_vcs     = {NUM_VCS};
vc_buf_size = {VC_BUF_SIZE};
vc_allocator = {VC_ALLOCATOR};
sw_allocator = {SW_ALLOCATOR};
alloc_iters  = 1;

speculative      = {SPECULATIVE};
routing_delay    = {ROUTING_DELAY};
vc_alloc_delay   = {VC_ALLOC_DELAY};
sw_alloc_delay   = {SW_ALLOC_DELAY};
st_prepare_delay = {ST_PREPARE_DELAY};
st_final_delay   = {ST_FINAL_DELAY};

sim_type       = latency;
sample_period  = 1000;
warmup_periods = 3;
sim_count      = 1;
max_samples    = {MAX_SAMPLES};
latency_thres  = {LATENCY_THRES};
"""
if STATS_OUT:
    cfg += f"stats_out = {STATS_OUT};\n"
cfg_path = os.path.join(here, "chi_traffic")
with open(cfg_path, "w") as f:
    f.write(cfg)

# ---- report ----
print(f"Wrote {topo_path} ({len(lines)} routers, {total_nodes} nodes)")
print(f"Wrote {cfg_path}  (classes={classes}, total offered LAMBDA={LAMBDA} pkt/node)\n")
print("DDR SN placement:")
for idx, router in enumerate(sn_routers):
    print(f"  router {router} coord={SN_ROUTER_COORDS[idx]} -> SN node {sn_nodes[idx]}")
print()
print("transaction category shares:")
for cat in ["read", "write", "dataless", "cmo"]:
    print(f"  {cat:<8} {cat_share[cat]:6.1%}  subtypes={sub_share[cat]}")
print("\nscenario shares:")
print(f"  read            {read_scenario_share}")
print(f"  read_nosnp      {read_nosnp_scenario_share}")
print(f"  write_unique    {wu_scenario_share}")
print(f"  write_evict     {we_scenario_share}")
print(f"  dataless        {dataless_scenario_share}")
print(f"  cmo             {cmo_scenario_share}")
print(f"  async_l3_evict_to_sn={l3_evict_to_sn:.1%}\n")
print(f"{'cls':>3} {'category.subtype.message':<42} {'ch':<3} {'dir':<8} "
      f"{'size':>4} {'inj_rate':>10}")
chan_flit = {}
cat_flit = {}
for i, m in enumerate(messages):
    chan_flit[m["channel"]] = chan_flit.get(m["channel"], 0.0) + inj_rate[i] * m["size"]
    cat_flit[m["category"]] = cat_flit.get(m["category"], 0.0) + inj_rate[i] * m["size"]
    full_name = f"{m['category']}.{m['subtype']}.{m['message']}"
    print(f"c{i:<2} {full_name:<42} {m['channel']:<3} "
          f"{m['src']+'->'+m['dst']:<8} {m['size']:>4} {inj_rate[i]:>10}")
print("\nper-category offered FLIT rate / node:")
for cat in ["read", "write", "dataless", "cmo"]:
    print(f"  {cat}: {cat_flit.get(cat,0):.5f}")
print("\nper-channel offered FLIT rate / node:")
for ch in ["REQ", "RSP", "SNP", "DAT"]:
    print(f"  {ch}: {chan_flit.get(ch,0):.5f}")
