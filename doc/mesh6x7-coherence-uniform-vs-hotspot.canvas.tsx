import {
  Stack,
  Grid,
  Row,
  H1,
  H2,
  Text,
  Stat,
  Table,
  LineChart,
  BarChart,
  Callout,
} from "cursor/canvas";

type SweepPoint = { inj: number; throughput: number; latency: number };

// Injection-rate sweeps (utils/sweep.sh) on the 6x7 mesh with coherence-style
// request/reply traffic. "inj" = offered request rate (pkt/node/cycle);
// "throughput" = measured accepted flit rate (flits/node/cycle); latency in cyc.
const UNIFORM: SweepPoint[] = [
  { inj: 0.0025, throughput: 0.0154, latency: 30.36 },
  { inj: 0.05, throughput: 0.3035, latency: 33.84 },
  { inj: 0.0625, throughput: 0.3759, latency: 38.1 },
  { inj: 0.0656, throughput: 0.3953, latency: 39.34 },
  { inj: 0.0672, throughput: 0.403, latency: 39.69 },
];

const HOTSPOT: SweepPoint[] = [
  { inj: 0.0025, throughput: 0.0153, latency: 30.24 },
  { inj: 0.0125, throughput: 0.0764, latency: 32.06 },
  { inj: 0.0188, throughput: 0.1123, latency: 35.88 },
  { inj: 0.0219, throughput: 0.1302, latency: 59.07 },
  { inj: 0.0234, throughput: 0.1366, latency: 281.25 },
];

const U_SAT_INJ = 0.0672;
const H_SAT_INJ = 0.0234;
const U_PEAK_THR = 0.403;
const H_PEAK_THR = 0.137;

export default function CoherenceUniformVsHotspot() {
  return (
    <Stack gap={20} style={{ padding: 24, maxWidth: 960 }}>
      <Stack gap={4}>
        <H1>Coherence Traffic: Uniform vs. Hotspot</H1>
        <Text tone="secondary">
          6×7 mesh (42 nodes) · request/reply (use_read_write) · write_fraction
          0.3 · 1-flit control / 5-flit data · 2 subnets · 4 VCs · BookSim2
          injection-rate sweep
        </Text>
      </Stack>

      <Callout tone="warning" title="Centralized directories saturate ~3× earlier">
        Spreading directory/home nodes across all 42 nodes (uniform) lets the
        network sustain a peak accepted throughput of ~0.40 flits/node/cycle.
        Funneling every request into just 4 hotspot directory banks collapses
        that to ~0.14 — the hotspot nodes and the links feeding them become the
        bottleneck, and latency blows up at roughly one-third the offered load.
      </Callout>

      <Grid columns={4} gap={16}>
        <Stat value={U_PEAK_THR.toFixed(2)} label="Uniform peak throughput (f/n/c)" tone="success" />
        <Stat value={H_PEAK_THR.toFixed(2)} label="Hotspot peak throughput (f/n/c)" tone="warning" />
        <Stat value={U_SAT_INJ.toFixed(4)} label="Uniform saturation offered load (pkt/n/c)" />
        <Stat value={H_SAT_INJ.toFixed(4)} label="Hotspot saturation offered load (pkt/n/c)" />
      </Grid>

      <Stack gap={6}>
        <H2>Peak sustained throughput</H2>
        <BarChart
          categories={["Uniform (distributed)", "Hotspot (4 dirs)"]}
          series={[
            {
              name: "Peak accepted throughput",
              data: [U_PEAK_THR, H_PEAK_THR],
            },
          ]}
          valueSuffix=" f/n/c"
          showValues
          height={220}
        />
        <Text size="small" tone="tertiary">
          Y: peak accepted flit rate at saturation (flits/node/cycle) · higher is
          better · Source: utils/sweep.sh
        </Text>
      </Stack>

      <Grid columns={2} gap={20}>
        <Stack gap={6}>
          <H2>Uniform — latency vs. load</H2>
          <LineChart
            categories={UNIFORM.map((p) => p.inj.toFixed(4))}
            series={[
              { name: "Avg packet latency", data: UNIFORM.map((p) => p.latency), tone: "success" },
            ]}
            valueSuffix=" cyc"
            height={260}
          />
          <Text size="small" tone="tertiary">
            X: offered load (pkt/node/cycle) · Y: avg packet latency (cyc). Knee
            near 0.067.
          </Text>
        </Stack>

        <Stack gap={6}>
          <H2>Hotspot — latency vs. load</H2>
          <LineChart
            categories={HOTSPOT.map((p) => p.inj.toFixed(4))}
            series={[
              { name: "Avg packet latency", data: HOTSPOT.map((p) => p.latency), tone: "warning" },
            ]}
            valueSuffix=" cyc"
            height={260}
          />
          <Text size="small" tone="tertiary">
            X: offered load (pkt/node/cycle) · Y: avg packet latency (cyc). Knee
            near 0.023 — latency hits 281 cyc.
          </Text>
        </Stack>
      </Grid>

      <Stack gap={6}>
        <H2>Sweep data points</H2>
        <Row gap={24} align="stretch" wrap>
          <Stack gap={6} style={{ flex: 1, minWidth: 340 }}>
            <Text weight="semibold" tone="secondary">Uniform</Text>
            <Table
              headers={["Offered load", "Throughput (f/n/c)", "Latency (cyc)"]}
              columnAlign={["right", "right", "right"]}
              rows={UNIFORM.map((p) => [
                p.inj.toFixed(4),
                p.throughput.toFixed(4),
                p.latency.toFixed(2),
              ])}
              rowTone={UNIFORM.map((p) => (p.latency > 60 ? "danger" : "success"))}
              striped
            />
          </Stack>
          <Stack gap={6} style={{ flex: 1, minWidth: 340 }}>
            <Text weight="semibold" tone="secondary">Hotspot (4 dirs)</Text>
            <Table
              headers={["Offered load", "Throughput (f/n/c)", "Latency (cyc)"]}
              columnAlign={["right", "right", "right"]}
              rows={HOTSPOT.map((p) => [
                p.inj.toFixed(4),
                p.throughput.toFixed(4),
                p.latency.toFixed(2),
              ])}
              rowTone={HOTSPOT.map((p) => (p.latency > 60 ? "danger" : "success"))}
              striped
            />
          </Stack>
        </Row>
      </Stack>
    </Stack>
  );
}
