"use client";

import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useState } from "react";

import { formatDayShort, formatDuration } from "@/lib/ponto/format";
import type { TrendDay } from "@/lib/ponto/queries";

const SURPLUS = "var(--accent-surplus)";
const SHORTFALL = "var(--accent-shortfall)";
const FADED = 0.55;

/**
 * Daily trend. Zero in the middle, surplus above, shortfall below — the two
 * directions are not two series on the same side, because a day with 200
 * minutes of each is not a quiet day.
 *
 * Shortfall is plotted negative so the axis carries the meaning; the labels put
 * the magnitude back, since nobody reads "−542 minutos faltantes" as a
 * quantity below zero.
 */
export function ChartDiverging({
  data,
  height = 220,
}: {
  data: TrendDay[];
  height?: number;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const plotted = data.map((day) => ({ ...day, below: -day.shortfall }));

  return (
    <div>
      <div className="mb-3 flex items-center gap-4">
        <Legend color={SURPLUS} label="Excedente" />
        <Legend color={SHORTFALL} label="Faltante" />
      </div>

      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={plotted}
            margin={{ top: 4, right: 4, bottom: 4, left: 4 }}
            stackOffset="sign"
            onMouseLeave={() => setHovered(null)}
          >
            <XAxis
              dataKey="day"
              tickFormatter={formatDayShort}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: "var(--text-faint)" }}
              interval="preserveStartEnd"
            />
            <YAxis hide />
            <ReferenceLine y={0} stroke="var(--border-default)" />
            <Tooltip cursor={false} content={<TrendTooltip />} />
            <Bar
              dataKey="surplus"
              stackId="minutes"
              radius={[3, 3, 0, 0]}
              onMouseEnter={(_, index) =>
                setHovered(plotted[index]?.day ?? null)
              }
            >
              {plotted.map((day) => (
                <Cell
                  key={day.day}
                  fill={SURPLUS}
                  fillOpacity={hovered && hovered !== day.day ? FADED : 1}
                />
              ))}
            </Bar>
            <Bar
              dataKey="below"
              stackId="minutes"
              radius={[0, 0, 3, 3]}
              onMouseEnter={(_, index) =>
                setHovered(plotted[index]?.day ?? null)
              }
            >
              {plotted.map((day) => (
                <Cell
                  key={day.day}
                  fill={SHORTFALL}
                  fillOpacity={hovered && hovered !== day.day ? FADED : 1}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="text-ink-muted flex items-center gap-1.5 text-xs font-semibold">
      <span
        aria-hidden
        className="size-2 rounded-full"
        style={{ background: color }}
      />
      {label}
    </span>
  );
}

type TooltipProps = {
  active?: boolean;
  label?: string | number;
  payload?: { payload?: TrendDay }[];
};

function TrendTooltip({ active, payload, label }: TooltipProps) {
  const day = payload?.[0]?.payload;

  if (!active || !day) {
    return null;
  }

  return (
    <div className="bg-card border-line rounded-[10px] border px-3 py-2 shadow-[var(--shadow-md)]">
      <p className="text-ink text-xs font-bold">
        {formatDayShort(String(label))}
      </p>
      <p className="text-surplus text-xs font-semibold tabular-nums">
        Excedente {formatDuration(day.surplus)}
      </p>
      <p className="text-shortfall text-xs font-semibold tabular-nums">
        Faltante {formatDuration(day.shortfall)}
      </p>
    </div>
  );
}
