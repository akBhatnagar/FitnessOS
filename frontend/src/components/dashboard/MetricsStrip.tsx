"use client";

import { TrendingDown, TrendingUp, Minus, Scale, Target, Activity, Flame } from "lucide-react";
import { cn } from "@/lib/utils";

interface Metrics {
  current_weight_kg?: number;
  target_weight_kg?: number;
  weight_to_lose_kg?: number;
  body_fat_pct?: number;
  waist_cm?: number;
}

interface WeeklyProgress {
  gym_sessions_completed: number;
  gym_sessions_scheduled: number;
  adherence_pct: number;
}

interface MetricsStripProps {
  metrics?: Metrics;
  weeklyProgress?: WeeklyProgress;
}

export function MetricsStrip({ metrics, weeklyProgress }: MetricsStripProps) {
  const cards = [
    {
      label: "Current Weight",
      value: metrics?.current_weight_kg ? `${metrics.current_weight_kg} kg` : "—",
      subtext: metrics?.target_weight_kg ? `Target: ${metrics.target_weight_kg} kg` : "Set your target",
      icon: Scale,
      trend: metrics?.weight_to_lose_kg ? "down" : "neutral",
      color: "text-blue-500",
      bg: "bg-blue-500/10",
    },
    {
      label: "To Lose",
      value: metrics?.weight_to_lose_kg ? `${metrics.weight_to_lose_kg.toFixed(1)} kg` : "—",
      subtext: "Until target weight",
      icon: Target,
      trend: "neutral",
      color: "text-orange-500",
      bg: "bg-orange-500/10",
    },
    {
      label: "Weekly Gym",
      value: weeklyProgress
        ? `${weeklyProgress.gym_sessions_completed}/${weeklyProgress.gym_sessions_scheduled}`
        : "—",
      subtext: weeklyProgress ? `${weeklyProgress.adherence_pct}% adherence` : "No data",
      icon: Activity,
      trend: (weeklyProgress?.adherence_pct ?? 0) >= 80 ? "up" : "down",
      color: "text-green-500",
      bg: "bg-green-500/10",
    },
    {
      label: "Body Fat",
      value: metrics?.body_fat_pct ? `${metrics.body_fat_pct}%` : "—",
      subtext: "Estimated",
      icon: Flame,
      trend: "neutral",
      color: "text-purple-500",
      bg: "bg-purple-500/10",
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="relative overflow-hidden rounded-xl border bg-card p-4 transition-all hover:shadow-sm"
        >
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs text-muted-foreground font-medium">{card.label}</p>
              <p className="text-2xl font-bold mt-1 tracking-tight">{card.value}</p>
              <p className="text-xs text-muted-foreground mt-1">{card.subtext}</p>
            </div>
            <div className={cn("p-2 rounded-lg", card.bg)}>
              <card.icon className={cn("h-4 w-4", card.color)} />
            </div>
          </div>

          {/* Trend indicator */}
          <div className="mt-3 flex items-center gap-1">
            {card.trend === "up" && <TrendingUp className="h-3 w-3 text-green-500" />}
            {card.trend === "down" && <TrendingDown className="h-3 w-3 text-orange-500" />}
            {card.trend === "neutral" && <Minus className="h-3 w-3 text-muted-foreground" />}
          </div>
        </div>
      ))}
    </div>
  );
}
