"use client";

import { useState, useEffect } from "react";
import { format, addDays, startOfWeek, isSameDay } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Calendar, Dumbbell, Waves, Utensils, Moon, Sun,
  Clock, ChevronLeft, ChevronRight, Loader2,
} from "lucide-react";
import { apiClient } from "@/services/api";
import { toast } from "sonner";

interface WorkoutSession {
  id: string;
  status: string;
  plan_name: string;
  scheduled_date: string;
  scheduled_time?: string;
}

interface DashboardSummary {
  weekly_progress: {
    gym_sessions_completed: number;
    gym_sessions_scheduled: number;
    adherence_pct: number;
  };
  countdowns?: { label: string; days: number }[];
}

const DAILY_SCHEDULE = [
  { time: "08:00", label: "Swimming", icon: Waves, color: "text-blue-400", type: "swimming" },
  { time: "10:30", label: "Office starts", icon: Sun, color: "text-yellow-400", type: "office" },
  { time: "13:00", label: "Lunch break", icon: Utensils, color: "text-green-400", type: "nutrition" },
  { time: "21:00", label: "Gym session", icon: Dumbbell, color: "text-orange-400", type: "gym" },
  { time: "20:00", label: "Office ends", icon: Moon, color: "text-purple-400", type: "office" },
  { time: "00:00", label: "Target sleep", icon: Moon, color: "text-indigo-400", type: "sleep" },
];

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function SchedulePage() {
  const [today] = useState(new Date());
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date(), { weekStartsOn: 1 }));
  const [sessions, setSessions] = useState<WorkoutSession[]>([]);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [histRes, sumRes] = await Promise.all([
          apiClient.get("/api/v1/workouts/sessions/history?limit=14"),
          apiClient.get("/api/v1/dashboard/summary"),
        ]);
        setSessions(Array.isArray(histRes.data) ? histRes.data : []);
        setSummary(sumRes.data);
      } catch {
        toast.error("Failed to load schedule.");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));

  const getSessionForDay = (day: Date) =>
    sessions.find((s) => {
      const d = new Date(s.scheduled_date ?? s.scheduled_date);
      return isSameDay(d, day);
    });

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
        <h1 className="text-2xl font-bold tracking-tight">Schedule</h1>
        <p className="text-muted-foreground text-sm mt-1">
          {format(today, "EEEE, MMMM d, yyyy")}
        </p>
      </div>

      {/* Weekly adherence */}
      {summary && (
        <div className="grid grid-cols-3 gap-4">
          <Card>
            <CardContent className="py-4 text-center">
              <p className="text-2xl font-bold text-primary">
                {summary.weekly_progress?.gym_sessions_completed ?? 0}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Gym sessions done</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-4 text-center">
              <p className="text-2xl font-bold">
                {summary.weekly_progress?.gym_sessions_scheduled ?? 0}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Scheduled this week</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="py-4 text-center">
              <p className={`text-2xl font-bold ${
                (summary.weekly_progress?.adherence_pct ?? 0) >= 70 ? "text-green-400" : "text-orange-400"
              }`}>
                {summary.weekly_progress?.adherence_pct ?? 0}%
              </p>
              <p className="text-xs text-muted-foreground mt-1">Adherence</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Week calendar */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Calendar className="h-4 w-4" /> Weekly View
            </CardTitle>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setWeekStart((w) => addDays(w, -7))}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-xs text-muted-foreground">
                {format(weekStart, "MMM d")} – {format(addDays(weekStart, 6), "MMM d")}
              </span>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setWeekStart((w) => addDays(w, 7))}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-7 gap-2">
            {weekDays.map((day, idx) => {
              const session = getSessionForDay(day);
              const isToday = isSameDay(day, today);
              return (
                <div
                  key={idx}
                  className={`rounded-lg p-2 text-center space-y-1 border transition-colors ${
                    isToday
                      ? "bg-primary/10 border-primary/30"
                      : "bg-muted/20 border-transparent"
                  }`}
                >
                  <p className="text-[10px] font-medium text-muted-foreground uppercase">
                    {DAY_LABELS[day.getDay()]}
                  </p>
                  <p className={`text-sm font-bold ${isToday ? "text-primary" : ""}`}>
                    {format(day, "d")}
                  </p>
                  <div className="space-y-0.5">
                    {/* Always show swimming on weekdays */}
                    {day.getDay() !== 0 && (
                      <div className="h-1 rounded-full bg-blue-400/60" title="Swimming" />
                    )}
                    {/* Show gym session if found */}
                    {session ? (
                      <div
                        className={`h-1 rounded-full ${
                          session.status === "COMPLETED"
                            ? "bg-green-400"
                            : session.status === "IN_PROGRESS"
                            ? "bg-yellow-400"
                            : "bg-orange-400/60"
                        }`}
                        title={session.plan_name}
                      />
                    ) : day.getDay() !== 0 ? (
                      <div className="h-1 rounded-full bg-orange-400/20" title="Gym planned" />
                    ) : null}
                  </div>
                  {session && (
                    <Badge
                      variant={session.status === "COMPLETED" ? "default" : "secondary"}
                      className="text-[9px] px-1 py-0 h-4"
                    >
                      {session.status === "COMPLETED" ? "✓" : "gym"}
                    </Badge>
                  )}
                </div>
              );
            })}
          </div>
          <div className="flex gap-4 mt-3 pt-3 border-t">
            <LegendItem color="bg-blue-400/60" label="Swimming" />
            <LegendItem color="bg-green-400" label="Gym done" />
            <LegendItem color="bg-orange-400/60" label="Gym planned" />
            <LegendItem color="bg-primary/30" label="Today" />
          </div>
        </CardContent>
      </Card>

      {/* Daily routine */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="h-4 w-4" /> Daily Routine
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="relative space-y-0">
              {[...DAILY_SCHEDULE].sort((a, b) => {
                // Convert HH:MM to sortable minutes; treat 00:xx (midnight) as 24:xx so it sorts last
                const toMin = (t: string) => {
                  const [h, m] = t.split(":").map(Number);
                  return (h === 0 ? 24 : h) * 60 + (m ?? 0);
                };
                return toMin(a.time) - toMin(b.time);
              }).map((item, i) => (
                <div key={i} className="flex items-center gap-3 py-3 border-b border-border/30 last:border-0">
                  <span className="text-xs text-muted-foreground font-mono w-12">{item.time}</span>
                  <div className={`h-8 w-8 rounded-lg bg-muted/50 flex items-center justify-center shrink-0`}>
                    <item.icon className={`h-4 w-4 ${item.color}`} />
                  </div>
                  <span className="text-sm">{item.label}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Upcoming events */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Key Events</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <EventItem
              label="Pre-Wedding Shoot"
              date="October 20, 2026"
              targetDate={new Date(2026, 9, 20)}
              color="text-amber-400"
            />
            <EventItem
              label="Wedding Day"
              date="January 30, 2027"
              targetDate={new Date(2027, 0, 30)}
              color="text-red-400"
            />
            <div className="pt-4 border-t">
              <p className="text-xs text-muted-foreground font-medium mb-3">Weekly Targets</p>
              <div className="space-y-2">
                {[
                  { label: "Gym sessions", target: "5x / week", icon: Dumbbell },
                  { label: "Swimming", target: "5x / week", icon: Waves },
                  { label: "Sleep goal", target: "12:00 AM", icon: Moon },
                ].map((t) => (
                  <div key={t.label} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <t.icon className="h-3 w-3 text-muted-foreground" />
                      <span className="text-muted-foreground">{t.label}</span>
                    </div>
                    <span className="font-medium">{t.target}</span>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <div className={`h-2 w-4 rounded-full ${color}`} />
      {label}
    </div>
  );
}

function EventItem({
  label, date, targetDate, color,
}: {
  label: string; date: string; targetDate: Date; color: string;
}) {
  const days = Math.ceil((targetDate.getTime() - Date.now()) / 86400000);
  return (
    <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30 border border-border/50">
      <div>
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">{date}</p>
      </div>
      <div className={`text-right ${color}`}>
        <p className="text-lg font-bold">{days > 0 ? days : 0}</p>
        <p className="text-[10px]">days left</p>
      </div>
    </div>
  );
}
