"use client";

import { useState, useEffect } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Area, AreaChart,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  TrendingDown, TrendingUp, Target, Calendar, Trophy,
  Dumbbell, Flame, Brain, CheckCircle2, AlertCircle, Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/services/api";
import { format, differenceInDays } from "date-fns";

// ─── Types ─────────────────────────────────────────────────────────────────

interface WeightPoint { date: string; weight_kg: number; }
interface GymWeek { week: string; completed: number; total: number; pct: number; }
interface MacroDay { date: string; calories: number; protein_g: number; }
interface EventCountdown {
  title: string;
  event_type: string;
  date: string;
  days_remaining: number;
  peak_priority: string;
  is_critical: boolean;
}
interface WeddingPrediction {
  event: string;
  event_date: string;
  days_remaining: number;
  current_weight: number;
  target_weight: number;
  predicted_weight: number;
  weekly_loss_rate: number;
  on_track: boolean;
  kg_to_lose: number;
  confidence: string;
}
interface ReviewScore { week: string; score: number; gym: number; swim: number; }

interface AnalyticsData {
  weight_history: WeightPoint[];
  weight_summary: {
    current_kg: number;
    target_kg: number;
    total_lost_kg: number;
    to_go_kg: number;
    weeks_of_data: number;
  };
  gym_adherence: GymWeek[];
  macro_trend: MacroDay[];
  event_countdowns: EventCountdown[];
  wedding_prediction: WeddingPrediction | null;
  weekly_review_scores: ReviewScore[];
  lifetime_stats: { total_gym_sessions: number };
}

// ─── Countdown Card ──────────────────────────────────────────────────────────

function CountdownCard({ event }: { event: EventCountdown }) {
  const urgency = event.days_remaining <= 30 ? "critical" :
                  event.days_remaining <= 90 ? "high" : "normal";

  return (
    <div className={cn(
      "rounded-xl border p-4 space-y-2",
      urgency === "critical" && "border-red-500/40 bg-red-500/5",
      urgency === "high" && "border-yellow-500/40 bg-yellow-500/5",
    )}>
      <div className="flex items-center justify-between">
        <span className="font-semibold text-sm">{event.title}</span>
        {event.is_critical && <Badge variant="destructive" className="text-[10px]">Critical</Badge>}
      </div>
      <div className="text-3xl font-black tracking-tight">
        {event.days_remaining}
        <span className="text-base font-normal text-muted-foreground ml-1">days</span>
      </div>
      <p className="text-xs text-muted-foreground">
        {format(new Date(event.date), "MMMM d, yyyy")}
      </p>
    </div>
  );
}

// ─── Custom Tooltip ──────────────────────────────────────────────────────────

function WeightTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-card px-3 py-2 text-sm shadow-lg">
      <p className="text-muted-foreground text-xs mb-1">{label}</p>
      <p className="font-bold">{payload[0].value} kg</p>
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────────────────

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient.get("/api/v1/analytics/overview")
      .then((r) => setData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!data) return <p className="text-muted-foreground">Failed to load analytics.</p>;

  const { weight_summary, weight_history, gym_adherence, macro_trend,
          event_countdowns, wedding_prediction, weekly_review_scores, lifetime_stats } = data;

  // Build chart data — add target line
  const weightChartData = weight_history.map((p) => ({
    date: format(new Date(p.date), "MMM d"),
    weight: p.weight_kg,
    target: 85,
  }));

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Analytics</h1>
        <p className="text-muted-foreground text-sm">Your 12-week progress overview</p>
      </div>

      {/* Top Stats Row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-3xl font-black">{weight_summary.current_kg}</div>
            <div className="text-xs text-muted-foreground">Current kg</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className={cn("text-3xl font-black", weight_summary.total_lost_kg > 0 ? "text-green-400" : "text-muted-foreground")}>
              {weight_summary.total_lost_kg > 0 ? "-" : "+"}{Math.abs(weight_summary.total_lost_kg)}
            </div>
            <div className="text-xs text-muted-foreground">kg lost (12w)</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-3xl font-black text-primary">{weight_summary.to_go_kg}</div>
            <div className="text-xs text-muted-foreground">kg to goal</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-3xl font-black">{lifetime_stats.total_gym_sessions}</div>
            <div className="text-xs text-muted-foreground">gym sessions</div>
          </CardContent>
        </Card>
      </div>

      {/* Weight Chart */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingDown className="h-5 w-5 text-green-400" />
            Weight Trend
          </CardTitle>
          <CardDescription>
            12-week history · Target: 85kg
            {weight_history.length < 2 && " · Add weekly weigh-ins for trend line"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {weight_history.length >= 2 ? (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={weightChartData} margin={{ top: 5, right: 5, bottom: 0, left: -20 }}>
                <defs>
                  <linearGradient id="weightGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                <Tooltip content={<WeightTooltip />} />
                <ReferenceLine y={85} stroke="#f97316" strokeDasharray="5 5" label={{ value: "Target 85kg", fill: "#f97316", fontSize: 11 }} />
                <Area type="monotone" dataKey="weight" stroke="#22c55e" fill="url(#weightGrad)" strokeWidth={2} dot={{ r: 3, fill: "#22c55e" }} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex flex-col items-center justify-center h-40 text-muted-foreground text-sm gap-2">
              <TrendingDown className="h-10 w-10" />
              <p>Log your weight in Weekly Review every Sunday to see the trend</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Wedding Prediction */}
      {wedding_prediction && (
        <Card className={cn(
          "border-2",
          wedding_prediction.on_track ? "border-green-500/30" : "border-yellow-500/30"
        )}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              {wedding_prediction.on_track
                ? <CheckCircle2 className="h-5 w-5 text-green-400" />
                : <AlertCircle className="h-5 w-5 text-yellow-400" />
              }
              Wedding Prediction
            </CardTitle>
            <CardDescription>{wedding_prediction.event} · {wedding_prediction.days_remaining} days away</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div className="rounded-lg bg-muted/30 p-3">
                <div className="text-2xl font-black">{wedding_prediction.current_weight}kg</div>
                <div className="text-xs text-muted-foreground">Today</div>
              </div>
              <div className="rounded-lg bg-primary/10 border border-primary/20 p-3">
                <div className={cn("text-2xl font-black", wedding_prediction.on_track ? "text-green-400" : "text-yellow-400")}>
                  {wedding_prediction.predicted_weight}kg
                </div>
                <div className="text-xs text-muted-foreground">Predicted</div>
              </div>
              <div className="rounded-lg bg-muted/30 p-3">
                <div className="text-2xl font-black">{wedding_prediction.target_weight}kg</div>
                <div className="text-xs text-muted-foreground">Target</div>
              </div>
            </div>

            <div className="mt-4 flex items-center gap-3 rounded-lg p-3 text-sm" style={{
              backgroundColor: wedding_prediction.on_track ? "rgb(34 197 94 / 0.05)" : "rgb(234 179 8 / 0.05)"
            }}>
              {wedding_prediction.on_track ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-green-400 shrink-0" />
                  <p className="text-muted-foreground">
                    On track at <strong>{wedding_prediction.weekly_loss_rate}kg/week</strong>. 
                    Keep your current consistency and you'll hit the target.
                  </p>
                </>
              ) : (
                <>
                  <AlertCircle className="h-4 w-4 text-yellow-400 shrink-0" />
                  <p className="text-muted-foreground">
                    Slightly behind. Increase deficit by 200 kcal or add one extra swim session per week.
                  </p>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Event Countdowns */}
      {event_countdowns.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
            Event Countdowns
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {event_countdowns.map((e) => <CountdownCard key={e.title} event={e} />)}
          </div>
        </div>
      )}

      {/* Gym Adherence */}
      {gym_adherence.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Dumbbell className="h-5 w-5 text-primary" />
              Gym Adherence (Last 4 Weeks)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={gym_adherence} margin={{ top: 5, right: 5, bottom: 0, left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="week" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" unit="%" />
                <Tooltip formatter={(v: number) => [`${v}%`, "Adherence"]} />
                <ReferenceLine y={80} stroke="#22c55e" strokeDasharray="4 4" />
                <Bar dataKey="pct" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <p className="text-xs text-muted-foreground mt-2">Green line = 80% adherence target</p>
          </CardContent>
        </Card>
      )}

      {/* Protein Trend */}
      {macro_trend.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Flame className="h-5 w-5 text-red-400" />
              Protein Intake (Last 2 Weeks)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={macro_trend} margin={{ top: 5, right: 5, bottom: 0, left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))"
                  tickFormatter={(v) => format(new Date(v), "MMM d")} />
                <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" unit="g" />
                <Tooltip formatter={(v: number) => [`${v}g`, "Protein"]} />
                <ReferenceLine y={160} stroke="#ef4444" strokeDasharray="4 4" label={{ value: "160g target", fill: "#ef4444", fontSize: 10 }} />
                <Bar dataKey="protein_g" fill="#ef4444" radius={[4, 4, 0, 0]} opacity={0.8} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Weekly Review Scores */}
      {weekly_review_scores.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Trophy className="h-5 w-5 text-yellow-400" />
              Weekly Review Scores
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {weekly_review_scores.map((r) => (
                <div key={r.week} className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground w-28 shrink-0">{r.week}</span>
                  <div className="flex-1 h-6 rounded-full bg-muted/30 overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        (r.score ?? 0) >= 80 ? "bg-green-500" : (r.score ?? 0) >= 60 ? "bg-yellow-500" : "bg-red-500"
                      )}
                      style={{ width: `${r.score ?? 0}%` }}
                    />
                  </div>
                  <span className="text-sm font-bold w-10 text-right">{r.score ?? 0}%</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
