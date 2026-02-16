import React from "react";
import { usePolling } from "./hooks/usePolling";
import { useApi } from "./hooks/useApi";
import { sleep } from "./api/endpoints";
import { formatMinutes } from "./utils/formatters";
import type { SleepStatsResponse, WeeklyDay, WakeWindow as WakeWindowType } from "./api/types";

function urgencyColor(urgency: string): string {
  if (urgency === "red") return "#ff4444";
  if (urgency === "yellow") return "#ffbb33";
  return "#00C851";
}

function WakeWindowBar({ ww }: { ww: WakeWindowType }) {
  const pct = Math.min(100, (ww.awake_minutes / ww.window_max_minutes) * 100);
  const color = urgencyColor(ww.urgency);

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, marginBottom: 4 }}>
        <span>Awake: {formatMinutes(ww.awake_minutes)}</span>
        <span style={{ color }}>
          {ww.remaining_minutes > 0
            ? `${formatMinutes(ww.remaining_minutes)} left`
            : "Past window!"}
        </span>
      </div>
      <div style={{ background: "#333", borderRadius: 8, height: 20, overflow: "hidden" }}>
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: color,
            borderRadius: 8,
            transition: "width 0.5s ease, background 0.3s ease",
          }}
        />
      </div>
      <div style={{ fontSize: 12, color: "#888", marginTop: 2 }}>
        Window: {formatMinutes(ww.window_min_minutes)}–{formatMinutes(ww.window_max_minutes)} (age: {ww.baby_age_months}mo)
      </div>
    </div>
  );
}

function WeeklyChart({ data }: { data: WeeklyDay[] }) {
  const maxMins = Math.max(...data.map((d) => d.total_nap_minutes), 1);
  const barWidth = 32;
  const chartHeight = 100;
  const svgWidth = data.length * (barWidth + 8) + 8;

  return (
    <svg width={svgWidth} height={chartHeight + 24} style={{ display: "block", margin: "0 auto" }}>
      {data.map((d, i) => {
        const barH = (d.total_nap_minutes / maxMins) * chartHeight;
        const x = 8 + i * (barWidth + 8);
        const y = chartHeight - barH;
        return (
          <g key={d.date}>
            <rect x={x} y={y} width={barWidth} height={barH} rx={4} fill="#4fc3f7" />
            {d.total_nap_minutes > 0 && (
              <text x={x + barWidth / 2} y={y - 4} textAnchor="middle" fontSize={10} fill="#ccc">
                {formatMinutes(d.total_nap_minutes)}
              </text>
            )}
            <text x={x + barWidth / 2} y={chartHeight + 16} textAnchor="middle" fontSize={11} fill="#999">
              {d.day_label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ textAlign: "center", padding: "4px 8px" }}>
      <div style={{ fontSize: 20, fontWeight: "bold" }}>{value}</div>
      <div style={{ fontSize: 12, color: "#999" }}>{label}</div>
    </div>
  );
}

export default function SleepDashboard() {
  const { data: stats } = usePolling<SleepStatsResponse>(sleep.getStats, 30000);
  const { data: weekly } = useApi<WeeklyDay[]>(sleep.getWeekly);

  if (!stats) return <div style={{ textAlign: "center", color: "#888" }}>Loading sleep data...</div>;

  return (
    <div>
      <h3 style={{ margin: "0 0 12px", color: "orange" }}>Sleep Dashboard</h3>

      <WakeWindowBar ww={stats.wake_window} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, margin: "12px 0" }}>
        <StatItem label="Total Nap" value={formatMinutes(stats.total_nap_minutes)} />
        <StatItem label="Naps" value={String(stats.nap_count)} />
        <StatItem label="Longest Nap" value={formatMinutes(stats.longest_nap_minutes)} />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: 8,
          margin: "8px 0 16px",
          padding: "8px",
          background: "#1a1a2e",
          borderRadius: 8,
        }}
      >
        <StatItem label="Night Sleep" value={formatMinutes(stats.night_sleep.total_minutes)} />
        <StatItem label="Night Wakes" value={String(stats.night_sleep.wake_count)} />
        <StatItem label="Longest Stretch" value={formatMinutes(stats.night_sleep.longest_stretch_minutes)} />
      </div>

      {weekly && weekly.length > 0 && (
        <div>
          <h4 style={{ margin: "0 0 8px", color: "#ccc" }}>Weekly Trends</h4>
          <WeeklyChart data={weekly} />
        </div>
      )}
    </div>
  );
}
