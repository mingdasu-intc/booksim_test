import re, os
CFG = "chi_traffic"
STATS = "sn_local_stats.m"

txt = open(CFG).read()
sn = [int(x) for x in re.findall(r"node(\d+)@", txt)]
print("SN nodes:", sn)

labels = {}
for m in re.finditer(
    r"^//\s*c(\d+)\s+(\S+)\s+(REQ|RSP|SNP|DAT)\s+(\w+)->(\w+)\s+size=(\d+)",
    txt, re.M):
    labels[int(m.group(1))] = dict(chan=m.group(3), src=m.group(4), dst=m.group(5))
print("parsed comment classes:", len(labels))
for c, lb in sorted(labels.items()):
    if lb["chan"] == "DAT" and (lb["src"] == "SN" or lb["dst"] == "SN"):
        print(f"  c{c}: {lb}")

print("stats exists:", os.path.exists(STATS), "size:", os.path.getsize(STATS) if os.path.exists(STATS) else 0)
if os.path.exists(STATS):
    m = open(STATS).read()
    hits = re.findall(r"sent_flits\(\d+,:\)", m)
    print("sent_flits entries:", len(hits))
    if hits:
        mm = re.search(r"sent_flits\((\d+),:\)\s*=\s*\[([^\]]+)\]", m)
        if mm and sn:
            vec = [float(x) for x in mm.group(2).split()]
            print("first class SN vals:", [vec[i] for i in sn if i < len(vec)])