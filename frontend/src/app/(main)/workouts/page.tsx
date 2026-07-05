"use client";

import { useState, useEffect } from "react";
import { format } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Dumbbell, Play, CheckCircle2, Clock, ChevronRight,
  Search, Plus, Zap, TrendingUp, BarChart3, RotateCcw,
  Trophy, Target, AlertCircle, Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/services/api";
import { toast } from "sonner";

// ─── Types ─────────────────────────────────────────────────────────────────

interface Session {
  id: string;
  session_name: string;
  scheduled_date: string;
  status: string;
  muscle_groups: string[];
  duration_minutes: number | null;
  sets_logged: number;
  effort_rating: number | null;
}

interface Exercise {
  id: string;
  name: string;
  slug: string;
  primary_muscle: string;
  is_compound: boolean;
  tags: string[];
  instructions?: string;
  tips?: string;
}

interface SetRow {
  exercise_id: string;
  exercise_name: string;
  set_number: number;
  planned_reps?: number;
  planned_weight_kg?: number;
  actual_reps?: number;
  actual_weight_kg?: number;
  rpe?: number;
  estimated_1rm?: number;
}

interface Suggestion {
  recommended_weight_kg: number;
  recommended_sets: number;
  recommended_reps_min: number;
  recommended_reps_max: number;
  estimated_1rm: number | null;
  rationale: string;
  change_from_last: number;
  notes: string[];
}

type View = "overview" | "active_session" | "exercise_library";

const MUSCLE_COLORS: Record<string, string> = {
  chest: "bg-blue-500/20 text-blue-400",
  lats: "bg-purple-500/20 text-purple-400",
  mid_back: "bg-purple-500/20 text-purple-400",
  front_deltoid: "bg-yellow-500/20 text-yellow-400",
  side_deltoid: "bg-yellow-500/20 text-yellow-400",
  rear_deltoid: "bg-yellow-500/20 text-yellow-400",
  biceps: "bg-red-500/20 text-red-400",
  triceps: "bg-orange-500/20 text-orange-400",
  quads: "bg-green-500/20 text-green-400",
  hamstrings: "bg-emerald-500/20 text-emerald-400",
  glutes: "bg-teal-500/20 text-teal-400",
  calves: "bg-cyan-500/20 text-cyan-400",
  core: "bg-pink-500/20 text-pink-400",
  abs: "bg-pink-500/20 text-pink-400",
};

function MuscleTag({ muscle }: { muscle: string }) {
  const colors = MUSCLE_COLORS[muscle] || "bg-muted text-muted-foreground";
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize", colors)}>
      {muscle.replace("_", " ")}
    </span>
  );
}

// ─── Set Logger ─────────────────────────────────────────────────────────────

function SetLogger({
  sessionId,
  exercise,
  existingSets,
  suggestion,
  onSetLogged,
}: {
  sessionId: string;
  exercise: Exercise;
  existingSets: SetRow[];
  suggestion: Suggestion | null;
  onSetLogged: (set: SetRow) => void;
}) {
  const [weight, setWeight] = useState(suggestion?.recommended_weight_kg.toString() ?? "");
  const [reps, setReps] = useState(suggestion?.recommended_reps_min.toString() ?? "");
  const [rpe, setRpe] = useState("");
  const [logging, setLogging] = useState(false);
  const nextSet = existingSets.length + 1;
  const targetSets = suggestion?.recommended_sets ?? 3;

  const handleLog = async () => {
    if (!weight || !reps) {
      toast.error("Enter weight and reps to log the set.");
      return;
    }
    setLogging(true);
    try {
      const res = await apiClient.post(`/api/v1/workouts/sessions/${sessionId}/sets`, {
        exercise_id: exercise.id,
        set_number: nextSet,
        actual_weight_kg: parseFloat(weight),
        actual_reps: parseInt(reps),
        rpe: rpe ? parseInt(rpe) : null,
        planned_reps: suggestion?.recommended_reps_min,
        planned_weight_kg: suggestion?.recommended_weight_kg,
      });
      onSetLogged({
        exercise_id: exercise.id,
        exercise_name: exercise.name,
        set_number: nextSet,
        actual_weight_kg: parseFloat(weight),
        actual_reps: parseInt(reps),
        rpe: rpe ? parseInt(rpe) : undefined,
        estimated_1rm: res.data.estimated_1rm,
      });
      setReps("");
      setRpe("");
      toast.success(`Set ${nextSet} logged — ${weight}kg × ${reps}`);
    } catch {
      toast.error("Failed to log set.");
    } finally {
      setLogging(false);
    }
  };

  const allSetsComplete = existingSets.length >= targetSets;

  return (
    <div className="space-y-4">
      {/* Suggestion banner */}
      {suggestion && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
          <div className="flex items-center gap-2 mb-1">
            <Zap className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-primary">AI Suggestion</span>
            {suggestion.change_from_last > 0 && (
              <Badge variant="success" className="text-[10px] py-0">
                +{suggestion.change_from_last}kg from last session
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground">{suggestion.rationale}</p>
          <div className="mt-2 flex gap-3 text-sm font-bold">
            <span>{suggestion.recommended_sets} sets</span>
            <span>×</span>
            <span>{suggestion.recommended_reps_min}-{suggestion.recommended_reps_max} reps</span>
            <span>@</span>
            <span className="text-primary">{suggestion.recommended_weight_kg}kg</span>
          </div>
          {suggestion.estimated_1rm && (
            <p className="text-[10px] text-muted-foreground mt-1">
              Estimated 1RM: {suggestion.estimated_1rm}kg
            </p>
          )}
        </div>
      )}

      {/* Logged sets */}
      {existingSets.length > 0 && (
        <div className="space-y-1.5">
          {existingSets.map((s) => (
            <div key={s.set_number} className="flex items-center justify-between rounded-lg bg-muted/30 px-3 py-2 text-sm">
              <span className="text-muted-foreground font-mono">Set {s.set_number}</span>
              <span className="font-bold">{s.actual_weight_kg}kg × {s.actual_reps}</span>
              {s.rpe && <span className="text-muted-foreground text-xs">RPE {s.rpe}</span>}
              {s.estimated_1rm && (
                <span className="text-[10px] text-primary font-medium">~{s.estimated_1rm}kg 1RM</span>
              )}
              <CheckCircle2 className="h-4 w-4 text-green-400" />
            </div>
          ))}
        </div>
      )}

      {/* Log next set */}
      {!allSetsComplete && (
        <div className="rounded-lg border-2 border-dashed border-primary/30 p-4">
          <p className="text-xs font-semibold text-muted-foreground mb-3">
            Set {nextSet} of {targetSets}
          </p>
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="text-[10px] text-muted-foreground">Weight (kg)</label>
              <Input
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                type="number"
                step="2.5"
                placeholder="kg"
                className="font-mono text-lg font-bold h-11"
              />
            </div>
            <div className="flex-1">
              <label className="text-[10px] text-muted-foreground">Reps</label>
              <Input
                value={reps}
                onChange={(e) => setReps(e.target.value)}
                type="number"
                placeholder="reps"
                className="font-mono text-lg font-bold h-11"
              />
            </div>
            <div className="w-20">
              <label className="text-[10px] text-muted-foreground">RPE (opt)</label>
              <Input
                value={rpe}
                onChange={(e) => setRpe(e.target.value)}
                type="number"
                min={1}
                max={10}
                placeholder="RPE"
                className="font-mono h-11"
              />
            </div>
          </div>
          <Button onClick={handleLog} disabled={logging} className="mt-3 w-full">
            {logging ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
            Log Set {nextSet}
          </Button>
        </div>
      )}

      {allSetsComplete && (
        <div className="flex items-center gap-2 rounded-lg bg-green-500/10 border border-green-500/20 px-3 py-2">
          <Trophy className="h-4 w-4 text-green-400" />
          <span className="text-sm text-green-400 font-semibold">All {targetSets} sets complete!</span>
        </div>
      )}
    </div>
  );
}

// ─── Active Session View ─────────────────────────────────────────────────────

function ActiveSessionView({
  session,
  onComplete,
}: {
  session: Session;
  onComplete: () => void;
}) {
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [selectedExercise, setSelectedExercise] = useState<Exercise | null>(null);
  const [suggestions, setSuggestions] = useState<Record<string, Suggestion>>({});
  const [loggedSets, setLoggedSets] = useState<Record<string, SetRow[]>>({});
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Exercise[]>([]);
  const [completing, setCompleting] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  // Timer
  useEffect(() => {
    const t = setInterval(() => setElapsed((e) => e + 1), 60000);
    return () => clearInterval(t);
  }, []);

  const searchExercises = async (q: string) => {
    if (!q.trim()) { setSearchResults([]); return; }
    try {
      const res = await apiClient.get(`/api/v1/workouts/exercises?query=${encodeURIComponent(q)}`);
      setSearchResults(res.data.slice(0, 8));
    } catch { /* ignore */ }
  };

  const selectExercise = async (ex: Exercise) => {
    setSelectedExercise(ex);
    setQuery("");
    setSearchResults([]);
    if (!suggestions[ex.id]) {
      try {
        const res = await apiClient.get(
          `/api/v1/workouts/sessions/${session.id}/suggest?exercise_id=${ex.id}`
        );
        setSuggestions((s) => ({ ...s, [ex.id]: res.data }));
      } catch { /* will show no suggestion */ }
    }
  };

  const handleSetLogged = (set: SetRow) => {
    setLoggedSets((prev) => ({
      ...prev,
      [set.exercise_id]: [...(prev[set.exercise_id] ?? []), set],
    }));
  };

  const totalSets = Object.values(loggedSets).flat().length;

  const handleComplete = async () => {
    setCompleting(true);
    try {
      await apiClient.post(`/api/v1/workouts/sessions/${session.id}/complete`, {
        effort_rating: null,
        notes: null,
      });
      toast.success("Session complete! 💪");
      onComplete();
    } catch {
      toast.error("Failed to complete session.");
    } finally {
      setCompleting(false);
    }
  };

  return (
    <div className="max-w-xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">{session.session_name}</h2>
          <div className="flex gap-1 mt-1 flex-wrap">
            {session.muscle_groups.slice(0, 4).map((m) => <MuscleTag key={m} muscle={m} />)}
          </div>
        </div>
        <div className="text-right">
          <div className="flex items-center gap-1 text-muted-foreground text-sm">
            <Clock className="h-4 w-4" />
            <span>{elapsed}m</span>
          </div>
          <div className="text-xs text-muted-foreground">{totalSets} sets logged</div>
        </div>
      </div>

      {/* Exercise search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => { setQuery(e.target.value); searchExercises(e.target.value); }}
          placeholder="Search exercise (e.g. bench press, lateral raise...)"
          className="pl-9"
        />
        {searchResults.length > 0 && (
          <div className="absolute top-full left-0 right-0 z-10 mt-1 rounded-lg border bg-card shadow-lg">
            {searchResults.map((ex) => (
              <button
                key={ex.id}
                onClick={() => selectExercise(ex)}
                className="flex w-full items-center justify-between px-4 py-2.5 text-sm hover:bg-muted/50 first:rounded-t-lg last:rounded-b-lg"
              >
                <div className="flex items-center gap-2">
                  <Dumbbell className="h-3.5 w-3.5 text-muted-foreground" />
                  <span>{ex.name}</span>
                  {ex.is_compound && <Badge variant="secondary" className="text-[9px]">Compound</Badge>}
                </div>
                <MuscleTag muscle={ex.primary_muscle} />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Selected exercise + set logger */}
      {selectedExercise && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">{selectedExercise.name}</CardTitle>
              <button
                onClick={() => setSelectedExercise(null)}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Change exercise
              </button>
            </div>
            {selectedExercise.tips && (
              <CardDescription className="text-xs">{selectedExercise.tips}</CardDescription>
            )}
          </CardHeader>
          <CardContent>
            <SetLogger
              sessionId={session.id}
              exercise={selectedExercise}
              existingSets={loggedSets[selectedExercise.id] ?? []}
              suggestion={suggestions[selectedExercise.id] ?? null}
              onSetLogged={handleSetLogged}
            />
          </CardContent>
        </Card>
      )}

      {/* Done exercises summary */}
      {Object.keys(loggedSets).length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Completed exercises</p>
          {Object.entries(loggedSets).map(([exId, sets]) => (
            <div key={exId} className="flex items-center justify-between rounded-lg bg-muted/20 px-3 py-2 text-sm">
              <span className="font-medium">{sets[0].exercise_name}</span>
              <span className="text-muted-foreground">{sets.length} sets</span>
              <CheckCircle2 className="h-4 w-4 text-green-400" />
            </div>
          ))}
        </div>
      )}

      {/* Finish button */}
      <Button
        onClick={handleComplete}
        disabled={completing || totalSets === 0}
        className="w-full h-12 text-base font-bold"
        variant={totalSets > 0 ? "default" : "secondary"}
      >
        {completing ? <Loader2 className="h-5 w-5 animate-spin mr-2" /> : <CheckCircle2 className="h-5 w-5 mr-2" />}
        Finish Session ({totalSets} sets)
      </Button>
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────────────────

export default function WorkoutsPage() {
  const [view, setView] = useState<View>("overview");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [recentHistory, setRecentHistory] = useState<Session[]>([]);
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [exerciseQuery, setExerciseQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [generatingPlan, setGeneratingPlan] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [todayRes, historyRes] = await Promise.all([
        apiClient.get("/api/v1/workouts/sessions/today"),
        apiClient.get("/api/v1/workouts/sessions/history?limit=5"),
      ]);
      setSessions(todayRes.data);
      setRecentHistory(historyRes.data);
    } catch {
      toast.error("Failed to load workout data.");
    } finally {
      setLoading(false);
    }
  };

  const searchExercises = async (q: string) => {
    setExerciseQuery(q);
    try {
      const res = await apiClient.get(`/api/v1/workouts/exercises?query=${encodeURIComponent(q)}`);
      setExercises(res.data);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    if (view === "exercise_library" && exercises.length === 0) {
      apiClient.get("/api/v1/workouts/exercises").then((r) => setExercises(r.data)).catch(() => {});
    }
  }, [view]);

  const startSession = async (session: Session) => {
    try {
      await apiClient.post(`/api/v1/workouts/sessions/${session.id}/start`);
      setActiveSession({ ...session, status: "in_progress" });
      setView("active_session");
    } catch {
      toast.error("Failed to start session.");
    }
  };

  const generatePlan = async () => {
    setGeneratingPlan(true);
    try {
      const res = await apiClient.post("/api/v1/workouts/plans/generate", {
        plan_type: "ppl",
        days_per_week: 5,
        goal: "fat_loss",
      });
      toast.success(`Plan generated: ${res.data.plan_name}`);
      loadData();
    } catch {
      toast.error("Failed to generate plan.");
    } finally {
      setGeneratingPlan(false);
    }
  };

  if (view === "active_session" && activeSession) {
    return (
      <ActiveSessionView
        session={activeSession}
        onComplete={() => { setView("overview"); loadData(); }}
      />
    );
  }

  if (view === "exercise_library") {
    return (
      <div className="max-w-2xl mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Exercise Library</h1>
            <p className="text-muted-foreground text-sm">{exercises.length} exercises</p>
          </div>
          <Button variant="ghost" onClick={() => setView("overview")}>← Back</Button>
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={exerciseQuery}
            onChange={(e) => searchExercises(e.target.value)}
            placeholder="Search exercises..."
            className="pl-9"
          />
        </div>

        <div className="grid gap-3">
          {exercises.map((ex) => (
            <Card key={ex.id} className="cursor-pointer hover:border-primary/50 transition-colors">
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold">{ex.name}</span>
                      {ex.is_compound && <Badge variant="secondary" className="text-[10px]">Compound</Badge>}
                    </div>
                    <div className="flex gap-1 flex-wrap">
                      <MuscleTag muscle={ex.primary_muscle} />
                      {ex.tags.filter(t => ["priority", "v_taper", "fat_loss"].includes(t)).map(t => (
                        <span key={t} className="rounded-full bg-primary/10 text-primary px-2 py-0.5 text-[10px] font-semibold">
                          {t.replace("_", " ")}
                        </span>
                      ))}
                    </div>
                    {ex.tips && (
                      <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{ex.tips}</p>
                    )}
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground mt-1" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Workouts</h1>
          <p className="text-muted-foreground text-sm">{format(new Date(), "EEEE, MMMM d")}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setView("exercise_library")}>
            <Search className="h-4 w-4 mr-1" /> Library
          </Button>
        </div>
      </div>

      {/* Today's Sessions */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
          Today's Sessions
        </h2>

        {loading ? (
          <div className="flex items-center justify-center h-24">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : sessions.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center justify-center py-10 text-center gap-3">
              <Dumbbell className="h-10 w-10 text-muted-foreground" />
              <div>
                <p className="font-semibold">No sessions scheduled today</p>
                <p className="text-muted-foreground text-sm">Generate a plan or it might be a rest day</p>
              </div>
              <Button onClick={generatePlan} disabled={generatingPlan}>
                {generatingPlan ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Zap className="h-4 w-4 mr-2" />}
                Generate Push/Pull/Legs Plan
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {sessions.map((s) => (
              <Card key={s.id} className={cn(
                "transition-all",
                s.status === "completed" && "opacity-60",
              )}>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-bold text-lg">{s.session_name}</span>
                        <Badge variant={
                          s.status === "completed" ? "success" :
                          s.status === "in_progress" ? "default" : "secondary"
                        }>
                          {s.status.replace("_", " ")}
                        </Badge>
                      </div>
                      <div className="flex gap-1 flex-wrap">
                        {s.muscle_groups.slice(0, 4).map((m) => <MuscleTag key={m} muscle={m} />)}
                      </div>
                      {s.sets_logged > 0 && (
                        <p className="text-xs text-muted-foreground mt-1">{s.sets_logged} sets logged</p>
                      )}
                    </div>
                    <div>
                      {s.status === "completed" ? (
                        <CheckCircle2 className="h-8 w-8 text-green-400" />
                      ) : (
                        <Button onClick={() => startSession(s)} size="sm">
                          <Play className="h-4 w-4 mr-1" />
                          {s.status === "in_progress" ? "Resume" : "Start"}
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Recent History */}
      {recentHistory.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
            Recent Sessions
          </h2>
          <div className="space-y-2">
            {recentHistory.map((s) => (
              <div key={s.id} className="flex items-center justify-between rounded-lg border px-4 py-3">
                <div>
                  <span className="font-medium text-sm">{s.session_name}</span>
                  <p className="text-xs text-muted-foreground">
                    {format(new Date(s.date ?? s.scheduled_date ?? ""), "EEE, MMM d")}
                    {s.duration_minutes && ` · ${s.duration_minutes}m`}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex gap-1">
                    {(s.muscle_groups ?? []).slice(0, 2).map((m) => <MuscleTag key={m} muscle={m} />)}
                  </div>
                  {s.effort_rating && (
                    <Badge variant="outline" className="text-[10px]">
                      Effort {s.effort_rating}/10
                    </Badge>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
