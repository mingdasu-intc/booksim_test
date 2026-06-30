import {
  Stack,
  Grid,
  H1,
  H2,
  Text,
  Stat,
  Table,
  LineChart,
  Callout,
} from "cursor/canvas";

type Point = {
  inj: number;
  accepted: number;
  latency: number;
};

// Data from utils/sweep.sh on mesh6x7config (uniform traffic, DOR/min routing,
// 8 VCs, packet_size=1). Only converged runs shown, sorted by offered load.
const POINTS: Point[] = [
  { inj: 0.0025, accepted: 0.00242, latency: 22.08 },
  { inj: 0.05, accepted: 0.05047, latency: 23.04 },
  { inj: 0.1, accepted: 0.09883, latency: 23.07 },
  { inj: 0.15, accepted: 0.14994, latency: 23.44 },
  { inj: 0.2, accepted: 0.19906, latency: 24.12 },
  { inj: 0.225, accepted: 0.22366, latency: 24.86 },
  { inj: 0.2281, accepted: 0.22692, latency: 26.47 },
  { inj: 0.2313, accepted: 0.23012, latency: 25.52 },
  { inj: 0.2344, accepted: 0.2326, latency: 43.65 },
  { inj: 0.2375, accepted: 0.23448, latency: 98.09 },
  { inj: 0.2438, accepted: 0.23497, latency: 291.55 },
  { inj: 0.2453, accepted: 0.23559, latency: 326.68 },
  { inj: 0.2469, accepted: 0.2350, latency: 491.79 },
];

const ZERO_LOAD_LAT = 22.08;
const SAT_THROUGHPUT = 0.235;
const SAT_INJ = 0.234;

export default function Mesh6x7ThroughputSweep() {
  const categories = POINTS.map((p) => p.inj.toFixed(3));

  return (
    <Stack gap={20} style={{ padding: 24, maxWidth: 920 }}>
      <Stack gap={4}>
        <H1>6×7 Mesh — Latency-Throughput Sweep</H1>
        <Text tone="secondary">
          BookSim2 · anynet topology (42 routers/nodes) · uniform traffic ·
          minimal routing · 8 VCs · 1-flit packets
        </Text>
      </Stack>

      <Grid columns={4} gap={16}>
        <Stat value={ZERO_LOAD_LAT.toFixed(1)} label="Zero-load latency (cycles)" />
        <Stat
          value={SAT_THROUGHPUT.toFixed(3)}
          label="Saturation throughput (flits/node/cycle)"
          tone="success"
        />
        <Stat
          value={SAT_INJ.toFixed(3)}
          label="Saturation offered load"
          tone="warning"
        />
        <Stat value="5.2" label="Avg hop count" />
      </Grid>

      <Callout tone="info" title="How to read this">
        Below saturation the network absorbs everything you offer (accepted ≈
        offered) and latency is nearly flat near the zero-load value. Past an
        offered load of ~0.234 flits/node/cycle the queues blow up — latency
        rises by 10–20× while accepted throughput plateaus at ~0.235. That knee
        is the network's saturation throughput.
      </Callout>

      <Stack gap={6}>
        <H2>Average packet latency vs. offered load</H2>
        <LineChart
          categories={categories}
          series={[
            {
              name: "Avg packet latency",
              data: POINTS.map((p) => p.latency),
              tone: "info",
            },
          ]}
          valueSuffix=" cyc"
          height={300}
          referenceLines={[
            { value: ZERO_LOAD_LAT, label: "zero-load", tone: "neutral" },
          ]}
        />
        <Text size="small" tone="tertiary">
          X: offered load (injection rate, flits/node/cycle) · Y: average packet
          latency (cycles) · Source: utils/sweep.sh
        </Text>
      </Stack>

      <Stack gap={6}>
        <H2>Accepted throughput vs. offered load</H2>
        <LineChart
          categories={categories}
          series={[
            {
              name: "Accepted flit rate",
              data: POINTS.map((p) => p.accepted),
              tone: "success",
            },
            {
              name: "Offered load (ideal)",
              data: POINTS.map((p) => p.inj),
              tone: "neutral",
            },
          ]}
          valueSuffix=" f/n/c"
          height={300}
          referenceLines={[
            { value: SAT_THROUGHPUT, label: "saturation", tone: "success" },
          ]}
        />
        <Text size="small" tone="tertiary">
          X: offered load · Y: rate (flits/node/cycle). Accepted tracks offered
          until ~0.234, then flattens at the saturation throughput · Source:
          utils/sweep.sh
        </Text>
      </Stack>

      <Stack gap={6}>
        <H2>Sweep data points</H2>
        <Table
          headers={[
            "Offered load",
            "Accepted (flits/node/cyc)",
            "Avg latency (cyc)",
            "Regime",
          ]}
          columnAlign={["right", "right", "right", "left"]}
          rows={POINTS.map((p) => {
            const saturated = p.latency > 2 * ZERO_LOAD_LAT;
            return [
              p.inj.toFixed(4),
              p.accepted.toFixed(4),
              p.latency.toFixed(2),
              saturated ? "saturated" : "stable",
            ];
          })}
          rowTone={POINTS.map((p) =>
            p.latency > 2 * ZERO_LOAD_LAT ? "danger" : "success"
          )}
          striped
        />
      </Stack>
    </Stack>
  );
}
