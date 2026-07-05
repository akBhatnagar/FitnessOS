"use client";

import { useState, useEffect } from "react";
import { format, isValid, parseISO } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Waves, Timer, Ruler, Trophy, Plus, Loader2,
  TrendingUp, Activity, Target,
} from "lucide-react";
import { apiClient } from "@/services/api";
import { toast } from "sonner";

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground font-medium">{children}</p>;
}

/** Raw shape returned by the swimming sessions API */
interface SwimmingSessionApi {
  id: string;
  session_date: string;
  duration_minutes: number;
  laps_completed?: number;
  total_laps?: number;
  distance_meters?: number;
  total_meters?: number;
  stroke_type?: string;
  strokes_practiced?: string[] | string;
  perceived_effort?: number;
  notes?: string;
}

interface SwimmingSession {
  id: string;
  session_date: string;
  duration_minutes: number;
  total_laps: number;
  total_meters: number;
  strokes: string[];
  perceived_effort: number;
  notes?: string;
}

interface SkillLevel {
  level: string;
  label: string;
  emoji: string;
}

interface NextMilestone {
  title: string;
  description: string;
  target_m: number;
  gap_meters: number;
}

interface SwimmingStats {
  total_sessions: number;
  total_distance_km: number;
  total_duration_hours: number;
  best_session_m: number;
  avg_effort: number;
  sessions_this_week: number;
  skill_level: SkillLevel;
  next_milestone?: NextMilestone;
}

interface Milestone {
  id: number;
  title: string;
  description: string;
  target_m: number;
  target_sessions: number;
  achieved: boolean;
}

interface LogForm {
  duration_minutes: string;
  total_laps: string;
  total_meters: string;
  strokes_practiced: string;
  perceived_effort: string;
  notes: string;
}

const STROKE_OPTIONS = ["Freestyle", "Backstroke", "Breaststroke", "Butterfly", "Mixed"];
const EFFORT_LABELS: Record<number, string> = { 1: "Easy", 2: "Light", 3: "Moderate", 4: "Hard", 5: "Max" };

function normalizeSession(raw: SwimmingSessionApi): SwimmingSession {
  let strokes: string[] = [];
  if (Array.isArray(raw.strokes_practiced)) {
    strokes = raw.strokes_practiced;
  } else if (typeof raw.strokes_practiced === "string" && raw.strokes_practiced) {
    strokes = raw.strokes_practiced.split(",").map((s) => s.trim()).filter(Boolean);
  } else if (raw.stroke_type) {
    strokes = [raw.stroke_type.replace(/_/g, " ")];
  }

  return {
    id: raw.id,
    session_date: raw.session_date,
    duration_minutes: raw.duration_minutes ?? 0,
    total_laps: raw.laps_completed ?? raw.total_laps ?? 0,
    total_meters: raw.distance_meters ?? raw.total_meters ?? 0,
    strokes,
    perceived_effort: raw.perceived_effort ?? 3,
    notes: raw.notes,
  };
}

function formatSessionDate(dateStr: string): string {
  const parsed = parseISO(dateStr);
  return isValid(parsed) ? format(parsed, "MMM d, yyyy") : dateStr;
}

export default function SwimmingPage() {
  const [sessions, setSessions] = useState<SwimmingSession[]>([]);
  const [stats, setStats] = useState<SwimmingStats | null>(null);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [loading, setLoading] = useState(true);
  const [logging, setLogging] = useState(false);
  const [showLog, setShowLog] = useState(false);
  const [form, setForm] = useState<LogForm>({
    duration_minutes: "45",
    total_laps: "20",
    total_meters: "500",
    strokes_practiced: "Freestyle",
    perceived_effort: "3",
    notes: "",
  });

  const loadData = async () => {
    try {
      const [sessRes, statsRes, milRes] = await Promise.all([
        apiClient.get("/api/v1/swimming/sessions"),
        apiClient.get("/api/v1/swimming/stats"),
        apiClient.get("/api/v1/swimming/milestones"),
      ]);
      const rawSessions: SwimmingSessionApi[] = Array.isArray(sessRes.data) ? sessRes.data : [];
      setSessions(rawSessions.map(normalizeSession));
      setStats(statsRes.data ?? null);
      setMilestones(Array.isArray(milRes.data) ? milRes.data : []);
    } catch {
      toast.error("Failed to load swimming data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const logSession = async () => {
    setLogging(true);
    try {
      await apiClient.post("/api/v1/swimming/sessions", {
        session_date: format(new Date(), "yyyy-MM-dd"),
        duration_minutes: parseInt(form.duration_minutes) || 45,
        total_laps: parseInt(form.total_laps) || 0,
        total_meters: parseInt(form.total_meters) || 0,
        strokes_practiced: form.strokes_practiced.split(",").map((s) => s.trim()),
        perceived_effort: parseInt(form.perceived_effort) || 3,
        notes: form.notes,
      });
      toast.success("Swimming session logged!");
      setShowLog(false);
      await loadData();
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : "Failed to log session.");
    } finally {
      setLogging(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Swimming</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {format(new Date(), "EEEE, MMMM d, yyyy")}
          </p>
        </div>
        <Button onClick={() => setShowLog(!showLog)} className="gap-2">
          <Plus className="h-4 w-4" />
          Log Session
        </Button>
      </div>

      {showLog && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Log Today&apos;s Swim</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <FieldLabel>Duration (min)</FieldLabel>
                <Input
                  type="number"
                  value={form.duration_minutes}
                  onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <FieldLabel>Total Laps</FieldLabel>
                <Input
                  type="number"
                  value={form.total_laps}
                  onChange={(e) => setForm({ ...form, total_laps: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <FieldLabel>Distance (meters)</FieldLabel>
                <Input
                  type="number"
                  value={form.total_meters}
                  onChange={(e) => setForm({ ...form, total_meters: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <FieldLabel>Effort (1–5)</FieldLabel>
                <Input
                  type="number"
                  min="1"
                  max="5"
                  value={form.perceived_effort}
                  onChange={(e) => setForm({ ...form, perceived_effort: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-1">
              <FieldLabel>Strokes practiced</FieldLabel>
              <div className="flex flex-wrap gap-2">
                {STROKE_OPTIONS.map((stroke) => {
                  const selected = form.strokes_practiced.includes(stroke);
                  return (
                    <button
                      key={stroke}
                      type="button"
                      onClick={() => {
                        const strokes = form.strokes_practiced
                          ? form.strokes_practiced.split(",").map((s) => s.trim()).filter(Boolean)
                          : [];
                        if (selected) {
                          setForm({ ...form, strokes_practiced: strokes.filter((s) => s !== stroke).join(", ") });
                        } else {
                          setForm({ ...form, strokes_practiced: [...strokes, stroke].join(", ") });
                        }
                      }}
                      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                        selected
                          ? "bg-primary text-primary-foreground border-primary"
                          : "border-border text-muted-foreground hover:border-primary"
                      }`}
                    >
                      {stroke}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="space-y-1">
              <FieldLabel>Notes (optional)</FieldLabel>
              <Input
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                placeholder="How did it feel?"
              />
            </div>
            <div className="flex gap-2">
              <Button onClick={logSession} disabled={logging} className="gap-2">
                {logging ? <Loader2 className="h-4 w-4 animate-spin" /> : <Waves className="h-4 w-4" />}
                Save Session
              </Button>
              <Button variant="ghost" onClick={() => setShowLog(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            icon={<Activity className="h-4 w-4 text-blue-400" />}
            label="Total Sessions"
            value={String(stats.total_sessions ?? 0)}
          />
          <StatCard
            icon={<Ruler className="h-4 w-4 text-green-400" />}
            label="Total Distance"
            value={`${Number(stats.total_distance_km ?? 0).toFixed(2)} km`}
          />
          <StatCard
            icon={<Waves className="h-4 w-4 text-cyan-400" />}
            label="This Week"
            value={`${stats.sessions_this_week ?? 0} sessions`}
          />
          <StatCard
            icon={<Target className="h-4 w-4 text-orange-400" />}
            label="Best Session"
            value={`${stats.best_session_m ?? 0}m`}
          />
        </div>
      )}

      {stats && (
        <Card className="bg-gradient-to-r from-blue-500/10 to-cyan-500/10 border-blue-500/20">
          <CardContent className="py-4 flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-4">
              <span className="text-3xl">{stats.skill_level?.emoji ?? "🌊"}</span>
              <div>
                <p className="font-semibold text-sm">Current Level</p>
                <p className="text-lg font-bold text-blue-400">{stats.skill_level?.label ?? "Beginner"}</p>
                <p className="text-xs text-muted-foreground">
                  {stats.total_duration_hours
                    ? `${Number(stats.total_duration_hours).toFixed(1)} hours total swim time`
                    : ""}
                </p>
              </div>
            </div>
            {stats.next_milestone && (
              <div className="text-right">
                <p className="text-xs text-muted-foreground">Next milestone</p>
                <p className="text-sm font-bold text-orange-400">{stats.next_milestone.title}</p>
                <p className="text-xs text-muted-foreground">{stats.next_milestone.description}</p>
                <p className="text-xs text-muted-foreground mt-1">{stats.next_milestone.gap_meters}m to go</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Timer className="h-4 w-4" /> Recent Sessions
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {sessions.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center">
                  <Waves className="h-12 w-12 text-muted-foreground/30 mb-3" />
                  <p className="text-sm text-muted-foreground">No swimming sessions yet.</p>
                  <p className="text-xs text-muted-foreground">Log your first session to get started!</p>
                </div>
              ) : (
                sessions.slice(0, 8).map((session) => (
                  <div
                    key={session.id}
                    className="flex items-start justify-between p-3 rounded-lg bg-muted/30 border border-border/50"
                  >
                    <div className="space-y-1">
                      <p className="text-sm font-medium">{formatSessionDate(session.session_date)}</p>
                      <div className="flex flex-wrap gap-1">
                        {session.strokes.map((s) => (
                          <Badge key={`${session.id}-${s}`} variant="secondary" className="text-xs capitalize">
                            {s}
                          </Badge>
                        ))}
                      </div>
                      {session.notes && (
                        <p className="text-xs text-muted-foreground italic">{session.notes}</p>
                      )}
                    </div>
                    <div className="text-right space-y-1">
                      <p className="text-sm font-bold">{session.total_meters}m</p>
                      <p className="text-xs text-muted-foreground">{session.total_laps} laps</p>
                      <p className="text-xs text-muted-foreground">{session.duration_minutes} min</p>
                      <Badge variant="outline" className="text-xs">
                        {EFFORT_LABELS[session.perceived_effort] ?? `Effort ${session.perceived_effort}`}
                      </Badge>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </div>

        <div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Trophy className="h-4 w-4 text-yellow-400" /> Milestones
              </CardTitle>
            </CardHeader>
            <CardContent>
              {milestones.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  Log more sessions to unlock milestones!
                </p>
              ) : (
                <ul className="space-y-2">
                  {milestones.map((m) => (
                    <li
                      key={m.id}
                      className={`flex items-start gap-2 p-2 rounded-lg ${
                        m.achieved ? "bg-yellow-400/10" : "opacity-50"
                      }`}
                    >
                      <Trophy
                        className={`h-3.5 w-3.5 shrink-0 mt-0.5 ${
                          m.achieved ? "text-yellow-400" : "text-muted-foreground"
                        }`}
                      />
                      <div>
                        <p className="text-xs font-medium">{m.title}</p>
                        <p className="text-[11px] text-muted-foreground">{m.description}</p>
                        <p className="text-[10px] text-muted-foreground mt-0.5">
                          {m.target_m}m · {m.target_sessions} sessions
                        </p>
                      </div>
                      {m.achieved && (
                        <span className="ml-auto text-[10px] text-yellow-400 font-bold shrink-0">✓</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-4 pt-4 border-t">
                <p className="text-xs text-muted-foreground font-medium mb-2 flex items-center gap-1">
                  <TrendingUp className="h-3 w-3" /> Next Goals
                </p>
                <ul className="space-y-1.5 text-xs text-muted-foreground">
                  <li>• Swim 1 km in one session</li>
                  <li>• Complete 50 total laps</li>
                  <li>• Practice 3 different strokes</li>
                  <li>• Maintain 4× weekly routine</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <Card>
      <CardContent className="py-4 flex items-center gap-3">
        <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center shrink-0">
          {icon}
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-lg font-bold">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
