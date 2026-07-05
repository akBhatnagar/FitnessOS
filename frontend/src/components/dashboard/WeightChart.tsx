"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { format, parseISO } from "date-fns";

interface WeightDataPoint {
  date: string;
  weight_kg: number | null;
}

interface WeightChartProps {
  data: WeightDataPoint[];
  targetWeight: number;
}

export function WeightChart({ data, targetWeight }: WeightChartProps) {
  const chartData = data
    .filter((d) => d.weight_kg !== null)
    .map((d) => ({
      date: d.date,
      weight: d.weight_kg,
      label: format(parseISO(d.date), "MMM d"),
    }));

  const minWeight = Math.min(...chartData.map((d) => d.weight ?? 0), targetWeight) - 2;
  const maxWeight = Math.max(...chartData.map((d) => d.weight ?? 0)) + 2;

  return (
    <div className="rounded-xl border bg-card p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="font-semibold">Weight Progress</h3>
          <p className="text-sm text-muted-foreground">
            {chartData.length > 0
              ? `Last ${chartData.length} measurements`
              : "No measurements yet"}
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full bg-primary" />
            <span className="text-muted-foreground">Current</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full bg-green-500" />
            <span className="text-muted-foreground">Target ({targetWeight} kg)</span>
          </div>
        </div>
      </div>

      {chartData.length === 0 ? (
        <div className="h-48 flex items-center justify-center">
          <p className="text-muted-foreground text-sm">
            Log your first weight measurement to see the chart.
          </p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="weightGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="hsl(24 95% 53%)" stopOpacity={0.3} />
                <stop offset="95%" stopColor="hsl(24 95% 53%)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={[minWeight, maxWeight]}
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              formatter={(value: number) => [`${value} kg`, "Weight"]}
              labelStyle={{ color: "hsl(var(--muted-foreground))" }}
            />
            <ReferenceLine
              y={targetWeight}
              stroke="hsl(142 76% 36%)"
              strokeDasharray="4 4"
              strokeWidth={1.5}
            />
            <Area
              type="monotone"
              dataKey="weight"
              stroke="hsl(24 95% 53%)"
              strokeWidth={2}
              fill="url(#weightGradient)"
              dot={{ r: 3, fill: "hsl(24 95% 53%)", strokeWidth: 0 }}
              activeDot={{ r: 5 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
