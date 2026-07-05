"use client";

import { differenceInDays, parseISO } from "date-fns";
import { Camera, Heart, TrendingDown } from "lucide-react";

interface Countdown {
  title: string;
  date: string;
  days_remaining: number;
}

interface Prediction {
  predicted_wedding_weight_kg?: number;
  confidence_pct?: number;
}

interface CountdownCardsProps {
  countdowns?: {
    pre_wedding?: Countdown;
    wedding?: Countdown;
  };
  prediction?: Prediction | null;
}

export function CountdownCards({ countdowns, prediction }: CountdownCardsProps) {
  const preWedding = countdowns?.pre_wedding;
  const wedding = countdowns?.wedding;

  return (
    <div className="space-y-4">
      {preWedding && (
        <CountdownCard
          title="Pre-Wedding Shoot"
          days={preWedding.days_remaining}
          subtitle="Oct 20, 2026 · Peak Definition"
          icon={Camera}
          colorClass="border-amber-500/30 bg-amber-500/5"
          textClass="text-amber-500"
          urgency={preWedding.days_remaining <= 60 ? "high" : "medium"}
        />
      )}

      {wedding && (
        <CountdownCard
          title="Wedding Day"
          days={wedding.days_remaining}
          subtitle="Jan 30, 2027 · Best Physique"
          icon={Heart}
          colorClass="border-red-500/30 bg-red-500/5"
          textClass="text-red-500"
          urgency={wedding.days_remaining <= 90 ? "high" : "medium"}
        />
      )}

      {prediction && (
        <div className="rounded-xl border bg-card p-4">
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-green-500/10">
              <TrendingDown className="h-4 w-4 text-green-500" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground font-medium">AI Prediction · Wedding</p>
              <p className="text-xl font-bold mt-0.5">
                {prediction.predicted_wedding_weight_kg ?? "—"} kg
              </p>
              {prediction.confidence_pct && (
                <p className="text-xs text-muted-foreground mt-1">
                  {prediction.confidence_pct}% confidence
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CountdownCard({
  title,
  days,
  subtitle,
  icon: Icon,
  colorClass,
  textClass,
  urgency,
}: {
  title: string;
  days: number;
  subtitle: string;
  icon: React.ComponentType<{ className?: string }>;
  colorClass: string;
  textClass: string;
  urgency: "high" | "medium" | "low";
}) {
  return (
    <div className={`rounded-xl border p-4 ${colorClass}`}>
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Icon className={`h-4 w-4 ${textClass}`} />
            <p className="text-sm font-semibold">{title}</p>
          </div>
          <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>
        </div>
        <div className="text-right">
          <p className={`text-3xl font-black tabular-nums ${textClass}`}>{days}</p>
          <p className="text-xs text-muted-foreground">days</p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="mt-3">
        <div className="h-1 bg-muted rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${textClass.replace("text-", "bg-")}`}
            style={{
              width: `${Math.max(5, Math.min(100, (1 - days / 400) * 100))}%`,
            }}
          />
        </div>
      </div>
    </div>
  );
}
