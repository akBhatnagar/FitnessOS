"use client";

import { useState, useEffect } from "react";
import { format } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Camera, TrendingDown, Scale, Ruler, Loader2,
  User, Target, BarChart2, Award,
} from "lucide-react";
import { apiClient } from "@/services/api";
import { toast } from "sonner";
import { DatePickerBar, todayStr } from "@/components/shared/DatePickerBar";
import { Input } from "@/components/ui/input";

interface Measurement {
  id: string;
  measured_on: string;
  weight_kg: number;
  body_fat_pct?: number;
  waist_cm?: number;
  energy_level?: number;
  sleep_quality?: number;
}

interface AnalyticsOverview {
  weight_history: { date: string; weight_kg: number }[];
  weight_summary?: {
    current_kg: number;
    target_kg: number;
    total_lost_kg: number;
    to_go_kg: number;
    weeks_of_data: number;
  };
}

export default function ProfilePage() {
  const [selectedDate, setSelectedDate] = useState(todayStr);
  const [weightInput, setWeightInput] = useState("");
  const [loggingWeight, setLoggingWeight] = useState(false);
  const [measurements, setMeasurements] = useState<Measurement[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsOverview | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = async () => {
    try {
      const [historyRes, analyticsRes] = await Promise.all([
        apiClient.get("/api/v1/measurements/", { params: { limit: 30 } }),
        apiClient.get("/api/v1/analytics/overview"),
      ]);
      setMeasurements(historyRes.data ?? []);
      setAnalytics(analyticsRes.data);
    } catch {
      toast.error("Failed to load profile data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const logWeight = async () => {
    const weight = parseFloat(weightInput);
    if (!weight || weight <= 0) {
      toast.error("Enter a valid weight in kg.");
      return;
    }
    setLoggingWeight(true);
    try {
      await apiClient.post("/api/v1/measurements/", {
        measured_on: selectedDate,
        weight_kg: weight,
      });
      toast.success(`Weight logged for ${selectedDate}`);
      setWeightInput("");
      await loadData();
    } catch {
      toast.error("Failed to log weight.");
    } finally {
      setLoggingWeight(false);
    }
  };

  const latest = measurements[0];
  const weightHistory = analytics?.weight_history ?? [];
  const summary = analytics?.weight_summary;
  const targetKg = summary?.target_kg ?? 85;
  const isToday = selectedDate === todayStr();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Progress & Profile</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Track your transformation journey
        </p>
      </div>

      {/* Profile card */}
      <Card className="bg-gradient-to-br from-primary/10 to-transparent">
        <CardContent className="py-6">
          <div className="flex items-center gap-6">
            <div className="h-20 w-20 rounded-full bg-primary/20 flex items-center justify-center">
              <User className="h-10 w-10 text-primary" />
            </div>
            <div className="flex-1">
              <h2 className="text-xl font-bold">{latest ? "Your Profile" : "Profile"}</h2>
              <p className="text-muted-foreground text-sm">28 years · 6&apos;1&quot; · Vegetarian</p>
              <div className="flex gap-2 mt-2">
                <Badge variant="secondary">Fat Loss Phase</Badge>
                <Badge variant="outline" className="text-primary border-primary/30">Active</Badge>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Log weight */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Scale className="h-4 w-4" /> Log Weight
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <DatePickerBar value={selectedDate} onChange={setSelectedDate} />
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-xs text-muted-foreground">Weight (kg)</label>
              <Input
                type="number"
                step="0.1"
                value={weightInput}
                onChange={(e) => setWeightInput(e.target.value)}
                placeholder={latest?.weight_kg ? `Last: ${latest.weight_kg} kg` : "e.g. 98.5"}
                className="mt-1 font-mono text-lg font-bold"
              />
            </div>
            <div className="flex items-end">
              <Button onClick={logWeight} disabled={loggingWeight} className="h-10">
                {loggingWeight ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save"}
              </Button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            {isToday
              ? "Log today's weight — updates your current weight on the dashboard."
              : "Log weight for a past date. Re-saving the same date updates that entry."}
          </p>
        </CardContent>
      </Card>

      {/* Current stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={<Scale className="h-4 w-4 text-orange-400" />}
          label="Current Weight"
          value={latest?.weight_kg ? `${latest.weight_kg} kg` : "—"}
          sub={`Target: ${targetKg} kg`}
        />
        <StatCard
          icon={<Target className="h-4 w-4 text-green-400" />}
          label="To Lose"
          value={latest?.weight_kg ? `${Math.max(0, latest.weight_kg - targetKg).toFixed(1)} kg` : "—"}
          sub={`Goal weight: ${targetKg} kg`}
        />
        <StatCard
          icon={<Ruler className="h-4 w-4 text-blue-400" />}
          label="Waist"
          value={latest?.waist_cm ? `${latest.waist_cm} cm` : "—"}
          sub={latest?.measured_on ? format(new Date(latest.measured_on), "MMM d") : ""}
        />
        <StatCard
          icon={<TrendingDown className="h-4 w-4 text-red-400" />}
          label="Total Lost"
          value={summary?.total_lost_kg ? `${summary.total_lost_kg.toFixed(1)} kg` : "—"}
          sub={`${summary?.weeks_of_data ?? 0} weeks tracked`}
        />
      </div>

      {/* Weight history */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <BarChart2 className="h-4 w-4" /> Weight History
          </CardTitle>
        </CardHeader>
        <CardContent>
          {weightHistory.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No weight history recorded yet.
            </p>
          ) : (
            <div className="space-y-2">
              {weightHistory.slice(-10).reverse().map((entry, i) => {
                const prev = weightHistory.slice(-10).reverse()[i + 1];
                const diff = prev ? entry.weight_kg - prev.weight_kg : 0;
                return (
                  <div
                    key={entry.date}
                    className="flex items-center justify-between py-2 border-b border-border/30 last:border-0"
                  >
                    <p className="text-sm text-muted-foreground">
                      {format(new Date(entry.date), "MMM d, yyyy")}
                    </p>
                    <div className="flex items-center gap-3">
                      {diff !== 0 && (
                        <span className={`text-xs ${diff < 0 ? "text-green-400" : "text-red-400"}`}>
                          {diff < 0 ? "▼" : "▲"} {Math.abs(diff).toFixed(1)} kg
                        </span>
                      )}
                      <span className="font-bold text-sm">{entry.weight_kg} kg</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Progress Photos placeholder */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Camera className="h-4 w-4" /> Progress Photos
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-10 text-center border-2 border-dashed border-border rounded-lg">
            <Camera className="h-12 w-12 text-muted-foreground/30 mb-3" />
            <p className="text-sm font-medium">Progress Photo Tracking</p>
            <p className="text-xs text-muted-foreground mt-1 max-w-xs">
              Photo upload and AI analysis coming soon. Your AI coach will track visual progress and
              estimate body composition changes over time.
            </p>
            <Button variant="outline" size="sm" className="mt-4 gap-2" disabled>
              <Camera className="h-4 w-4" />
              Upload Photo (Coming Soon)
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Achievements */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Award className="h-4 w-4 text-yellow-400" /> Achievements
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {[
              { title: "First Measurement", desc: "Logged your starting point", done: true },
              { title: "1st Gym Session", desc: "Started your fitness journey", done: true },
              { title: "First Swim", desc: "Took the plunge!", done: true },
              { title: "5 kg Lost", desc: "Reached -5 kg milestone", done: false },
              { title: "100 Gym Sessions", desc: "Century of consistency", done: false },
              { title: "Wedding Ready", desc: "Reach target weight", done: false },
            ].map((a) => (
              <div
                key={a.title}
                className={`p-3 rounded-lg border text-center ${
                  a.done
                    ? "bg-primary/10 border-primary/20"
                    : "bg-muted/20 border-border/30 opacity-50"
                }`}
              >
                <Award className={`h-6 w-6 mx-auto mb-1 ${a.done ? "text-yellow-400" : "text-muted-foreground"}`} />
                <p className="text-xs font-medium">{a.title}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">{a.desc}</p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  icon, label, value, sub,
}: {
  icon: React.ReactNode; label: string; value: string; sub?: string;
}) {
  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex items-center gap-2 mb-2">
          <div className="h-7 w-7 rounded-md bg-muted flex items-center justify-center">{icon}</div>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
        <p className="text-xl font-bold">{value}</p>
        {sub && <p className="text-[10px] text-muted-foreground mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}
