"use client";

import { useState, useEffect } from "react";
import { format, isValid, parseISO } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Dumbbell, Play, CheckCircle2, Clock, ChevronRight,
  Search, Plus, Zap, TrendingUp, BarChart3, RotateCcw,
  Trophy, Target, AlertCircle, Loader2, Moon, Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/services/api";
import { toast } from "sonner";
import { DatePickerBar, todayStr } from "@/components/shared/DatePickerBar";
import { MuscleWorkoutView } from "@/components/workouts/MuscleWorkoutView";
import { WorkoutPlanEditor, PlanEditorConfig } from "@/components/workouts/WorkoutPlanEditor";
import { WorkoutExecutionView } from "@/components/workouts/WorkoutExecutionView";
import {
  LOG_MUSCLE_OPTIONS,
  MIXED_WORKOUT,
  COMBO_WORKOUT,
  buildComboLabel,
  buildComboMuscles,
  getLogMuscleOption,
  isMuscleStructuredSession,
  groupSetsByExercise,
  REST_DAY_SESSION_NAME,
  isRestDaySession,
} from "@/lib/workoutMuscles";

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

type View = "overview" | "plan_editor" | "workout_execution" | "active_session" | "exercise_library" | "muscle_workout";

interface MuscleWorkoutState {
  session: Session;
  dbMuscles: string[];
  defaultPrimaryMuscle: string;
}

interface WorkoutExecutionState {
  session: Session;
}

const QUICK_SESSIONS = [
  { name: "Push Day", muscles: ["chest", "triceps", "front_deltoid"] },
  { name: "Pull Day", muscles: ["lats", "mid_back", "biceps"] },
  { name: "Legs Day", muscles: ["quads", "hamstrings", "glutes"] },
];

const ALL_DB_MUSCLES = [...new Set(LOG_MUSCLE_OPTIONS.flatMap((m) => m.dbMuscles))];

const MUSCLE_COLORS: Record<string, string> = {
  chest: "bg-blue-500/20 text-blue-400",
  lats: "bg-purple-500/20 text-purple-400",
  mid_back: "bg-purple-500/20 text-purple-400",
  front_deltoid: "bg-yellow-500/20 text-yellow-400",
  side_deltoid: "bg-yellow-500/20 text-yellow-400",
  rear_deltoid: "bg-yellow-500/20 text-yellow-400",
  traps: "bg-violet-500/20 text-violet-400",
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

/** Format a YYYY-MM-DD (or ISO) session date for display — date only, no time. */
function formatSessionDay(dateStr: string): string {
  const raw = (dateStr || "").slice(0, 10);
  if (!raw) return "";
  const parsed = parseISO(raw);
  if (!isValid(parsed)) return raw;
  return format(parsed, "EEE, MMM d");
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
  const [plannedExercises, setPlannedExercises] = useState<Exercise[]>([]);
  const [completing, setCompleting] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    apiClient
      .get(`/api/v1/workouts/sessions/${session.id}/sets`)
      .then(async (res) => {
        const actualRows = res.data.filter(
          (r: { actual_weight_kg?: number | null; actual_reps?: number | null }) =>
            r.actual_weight_kg != null && r.actual_reps != null,
        );
        setLoggedSets(groupSetsByExercise(actualRows));

        const seen = new Set<string>();
        const planned: Exercise[] = [];
        for (const row of res.data) {
          if (seen.has(row.exercise_id)) continue;
          seen.add(row.exercise_id);
          try {
            const detail = await apiClient.get(`/api/v1/workouts/exercises/${row.exercise_id}`);
            planned.push(detail.data);
          } catch { /* ignore */ }
        }
        setPlannedExercises(planned);
        if (planned.length === 1) setSelectedExercise(planned[0]);
      })
      .catch(() => { /* ignore — fresh session */ });
  }, [session.id]);

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

      {plannedExercises.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Personalized for you
          </p>
          <div className="flex flex-wrap gap-2">
            {plannedExercises.map((ex) => (
              <Button
                key={ex.id}
                variant={selectedExercise?.id === ex.id ? "default" : "outline"}
                size="sm"
                onClick={() => selectExercise(ex)}
              >
                {ex.name}
              </Button>
            ))}
          </div>
        </div>
      )}

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
  const [selectedDate, setSelectedDate] = useState(todayStr);
  const [view, setView] = useState<View>("overview");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [recentHistory, setRecentHistory] = useState<Session[]>([]);
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [exerciseQuery, setExerciseQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [generatingPlan, setGeneratingPlan] = useState(false);
  const [creatingSession, setCreatingSession] = useState(false);
  const [muscleWorkout, setMuscleWorkout] = useState<MuscleWorkoutState | null>(null);
  const [comboOpen, setComboOpen] = useState(false);
  const [comboMuscle1, setComboMuscle1] = useState(LOG_MUSCLE_OPTIONS[0].key);
  const [comboMuscle2, setComboMuscle2] = useState(LOG_MUSCLE_OPTIONS[1].key);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [generateStep, setGenerateStep] = useState<"pick" | "muscle" | "ppl">("pick");
  const [planEditor, setPlanEditor] = useState<PlanEditorConfig | null>(null);
  const [workoutExecution, setWorkoutExecution] = useState<WorkoutExecutionState | null>(null);
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);
  const [customExerciseOpen, setCustomExerciseOpen] = useState(false);
  const [customExerciseName, setCustomExerciseName] = useState("");
  const [customExerciseMuscle, setCustomExerciseMuscle] = useState(ALL_DB_MUSCLES[0]);
  const [addingCustomExercise, setAddingCustomExercise] = useState(false);

  const isToday = selectedDate === todayStr();

  const removableSessions = sessions.filter((s) => !isRestDaySession(s.session_name));
  const showRemoveOption = removableSessions.length >= 1;

  const closeGenerate = () => {
    setGenerateOpen(false);
    setGenerateStep("pick");
  };

  useEffect(() => {
    loadData(selectedDate);
  }, [selectedDate]);

  const loadData = async (date = selectedDate) => {
    setLoading(true);
    let historyLoaded = false;
    try {
      // Clean unused AI plan fillers once per load (safe no-op if none)
      await apiClient.post("/api/v1/workouts/plans/cleanup-unused").catch(() => null);
      const historyRes = await apiClient.get("/api/v1/workouts/sessions/history?limit=20");
      setRecentHistory(historyRes.data);
      historyLoaded = true;
    } catch {
      /* history failure handled below */
    }
    try {
      const todayRes = await apiClient.get("/api/v1/workouts/sessions/today", { params: { date } });
      setSessions(todayRes.data ?? []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("future dates")) {
        setSessions([]);
      } else if (!historyLoaded) {
        toast.error("Failed to load workout data.");
      }
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

  const openPlanPreview = (
    sessionName: string,
    dbMuscles: string[],
    generationType: string,
  ) => {
    closeGenerate();
    setPlanEditor({
      sessionName,
      scheduledDate: selectedDate,
      muscleGroups: dbMuscles,
      preview: { generation_type: generationType, goal: "fat_loss" },
    });
    setView("plan_editor");
  };

  const openPlanEditorForSession = (session: Session) => {
    setPlanEditor({
      sessionId: session.id,
      sessionName: session.session_name,
      scheduledDate: session.scheduled_date,
      muscleGroups: session.muscle_groups,
    });
    setView("plan_editor");
  };

  const openWorkoutExecution = (session: Session) => {
    setWorkoutExecution({ session });
    setView("workout_execution");
  };

  const resumeSession = async (session: Session) => {
    if (isRestDaySession(session.session_name)) {
      toast.info("Rest day — no workout to resume.");
      return;
    }
    try {
      const planRes = await apiClient.get(`/api/v1/workouts/sessions/${session.id}/plan`);
      const hasPlan = (planRes.data.exercises?.length ?? 0) > 0;

      if (hasPlan) {
        if (session.status === "scheduled") {
          openPlanEditorForSession(session);
          return;
        }
        if (session.status === "in_progress") {
          openWorkoutExecution(session);
          return;
        }
      }

      if (session.status === "scheduled") {
        await apiClient.post(`/api/v1/workouts/sessions/${session.id}/start`);
      }

      const inProgress = { ...session, status: "in_progress" as const };

      if (isMuscleStructuredSession(session.session_name)) {
        const dbMuscles = session.muscle_groups.length > 0
          ? session.muscle_groups
          : MIXED_WORKOUT.dbMuscles;
        setMuscleWorkout({
          session: inProgress,
          dbMuscles,
          defaultPrimaryMuscle: dbMuscles[0] ?? "chest",
        });
        setView("muscle_workout");
        return;
      }

      setActiveSession(inProgress);
      setView("active_session");
    } catch {
      toast.error("Failed to resume session.");
    }
  };

  const inferGenerationType = (sessionName: string, dbMuscles: string[]): string => {
    const n = sessionName.toLowerCase();
    if (sessionName === MIXED_WORKOUT.label) return "mixed";
    if (n.includes("push")) return "push";
    if (n.includes("pull")) return "pull";
    if (n.includes("leg")) return "legs";
    return dbMuscles.length > 4 ? "mixed" : "muscle";
  };

  const generatePPLPlan = async () => {
    setGeneratingPlan(true);
    try {
      const res = await apiClient.post("/api/v1/workouts/plans/generate", {
        plan_type: "ppl",
        days_per_week: 5,
        goal: "fat_loss",
        start_date: selectedDate,
      });
      const weekSessions: {
        id?: string;
        name: string;
        date: string;
        muscle_groups?: string[];
        exercise_names?: string[];
      }[] = res.data.week_1_sessions ?? [];
      const forDate = weekSessions.find((s) => s.date === selectedDate);
      closeGenerate();
      await loadData(selectedDate);
      if (forDate?.id) {
        openPlanEditorForSession({
          id: forDate.id,
          session_name: forDate.name,
          scheduled_date: forDate.date,
          status: "scheduled",
          muscle_groups: forDate.muscle_groups ?? [],
          duration_minutes: null,
          sets_logged: 0,
          effort_rating: null,
        });
        toast.success(`${forDate.name} ready — review your plan below`);
      } else {
        toast.success(`Plan created: ${res.data.plan_name}`);
      }
    } catch {
      toast.error("Failed to generate plan.");
    } finally {
      setGeneratingPlan(false);
    }
  };

  const handleGeneratePPL = () => {
    if (isToday) {
      generatePPLPlan();
    } else {
      setGenerateStep("ppl");
    }
  };

  const handleGenerateMusclePick = (key: string) => {
    const option = getLogMuscleOption(key);
    if (!option) return;
    openPlanPreview(`${option.label} Workout`, option.dbMuscles, "muscle");
  };

  const handleGenerateMixed = () => {
    openPlanPreview(MIXED_WORKOUT.label, MIXED_WORKOUT.dbMuscles, "mixed");
  };

  const handleGeneratePPLDay = (name: string, muscles: string[]) => {
    openPlanPreview(name, muscles, inferGenerationType(name, muscles));
  };

  const createSessionForDate = (sessionName: string, muscleGroups: string[] = []) => {
    openPlanPreview(sessionName, muscleGroups, inferGenerationType(sessionName, muscleGroups));
  };

  const startMuscleWorkout = (
    sessionName: string,
    dbMuscles: string[],
  ) => {
    openPlanPreview(sessionName, dbMuscles, inferGenerationType(sessionName, dbMuscles));
  };

  const handleSingleMuscle = (key: string) => {
    const option = getLogMuscleOption(key);
    if (!option) return;
    startMuscleWorkout(`${option.label} Workout`, option.dbMuscles);
  };

  const handleMixedWorkout = () => {
    startMuscleWorkout(MIXED_WORKOUT.label, MIXED_WORKOUT.dbMuscles);
  };

  const handleComboWorkout = () => {
    const m1 = getLogMuscleOption(comboMuscle1);
    const m2 = getLogMuscleOption(comboMuscle2);
    if (!m1 || !m2) return;
    if (comboMuscle1 === comboMuscle2) {
      toast.error("Pick two different muscle groups.");
      return;
    }
    const dbMuscles = buildComboMuscles(m1, m2);
    startMuscleWorkout(buildComboLabel(m1, m2), dbMuscles);
    setComboOpen(false);
  };

  const handleAddCustomExercise = async () => {
    const name = customExerciseName.trim();
    if (!name) {
      toast.error("Enter an exercise name.");
      return;
    }
    setAddingCustomExercise(true);
    try {
      const res = await apiClient.post("/api/v1/workouts/exercises", {
        name,
        primary_muscle: customExerciseMuscle,
        is_compound: false,
      });
      const created = res.data;
      const muscleGroup = LOG_MUSCLE_OPTIONS.find((m) =>
        m.dbMuscles.includes(customExerciseMuscle),
      )?.dbMuscles ?? [customExerciseMuscle];
      setCustomExerciseOpen(false);
      setCustomExerciseName("");
      setPlanEditor({
        sessionName: `${created.name} Workout`,
        scheduledDate: selectedDate,
        muscleGroups: muscleGroup,
        preview: { generation_type: "muscle", goal: "fat_loss" },
        seedExercise: {
          exercise_id: created.id,
          name: created.name,
          primary_muscle: created.primary_muscle,
          is_compound: created.is_compound ?? false,
        },
      });
      setView("plan_editor");
      toast.success(`${created.name} added to your library`);
    } catch {
      toast.error("Failed to add custom exercise.");
    } finally {
      setAddingCustomExercise(false);
    }
  };

  const deleteSession = async (session: Session) => {
    const label = session.session_name;
    setDeletingSessionId(session.id);
    setConfirmRemoveId(null);
    try {
      await apiClient.delete(`/api/v1/workouts/sessions/${session.id}`);
      if (workoutExecution?.session.id === session.id) {
        setWorkoutExecution(null);
        setView("overview");
      }
      if (planEditor?.sessionId === session.id) {
        setPlanEditor(null);
        setView("overview");
      }
      toast.success(`Removed ${label}`);
      await loadData();
    } catch {
      toast.error("Failed to remove session.");
    } finally {
      setDeletingSessionId(null);
    }
  };

  const logRestDay = async () => {
    if (sessions.some((s) => isRestDaySession(s.session_name))) {
      toast.info("Rest day already logged for this date.");
      return;
    }
    setCreatingSession(true);
    try {
      const res = await apiClient.post("/api/v1/workouts/sessions", {
        session_name: REST_DAY_SESSION_NAME,
        scheduled_date: selectedDate,
        muscle_groups: [],
      });
      await apiClient.post(`/api/v1/workouts/sessions/${res.data.id}/complete`, {});
      toast.success("Rest day logged");
      await loadData();
    } catch {
      toast.error("Failed to log rest day.");
    } finally {
      setCreatingSession(false);
    }
  };

  if (view === "plan_editor" && planEditor) {
    return (
      <WorkoutPlanEditor
        config={planEditor}
        onBack={() => { setView("overview"); setPlanEditor(null); loadData(); }}
        onSaved={() => { setView("overview"); setPlanEditor(null); loadData(); }}
        onStartWorkout={(saved) => {
          setPlanEditor(null);
          openWorkoutExecution({
            id: saved.id,
            session_name: saved.session_name,
            scheduled_date: planEditor.scheduledDate,
            status: "in_progress",
            muscle_groups: saved.muscle_groups ?? planEditor.muscleGroups,
            duration_minutes: null,
            sets_logged: 0,
            effort_rating: null,
          });
        }}
      />
    );
  }

  if (view === "workout_execution" && workoutExecution) {
    return (
      <WorkoutExecutionView
        session={workoutExecution.session}
        onBack={() => { setView("overview"); setWorkoutExecution(null); loadData(); }}
        onEditPlan={() => {
          openPlanEditorForSession(workoutExecution.session);
          setWorkoutExecution(null);
        }}
        onComplete={() => { setView("overview"); setWorkoutExecution(null); loadData(); }}
      />
    );
  }

  if (view === "muscle_workout" && muscleWorkout) {
    return (
      <MuscleWorkoutView
        session={muscleWorkout.session}
        dbMuscles={muscleWorkout.dbMuscles}
        defaultPrimaryMuscle={muscleWorkout.defaultPrimaryMuscle}
        onBack={() => { setView("overview"); setMuscleWorkout(null); }}
        onComplete={() => { setView("overview"); setMuscleWorkout(null); loadData(); }}
      />
    );
  }

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
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold">Workouts</h1>
            {!isToday && (
              <Badge variant="secondary" className="text-xs">Past date</Badge>
            )}
          </div>
          <Button variant="outline" size="sm" onClick={() => setView("exercise_library")}>
            <Search className="h-4 w-4 mr-1" /> Library
          </Button>
        </div>
        <DatePickerBar value={selectedDate} onChange={setSelectedDate} />
      </div>

      {/* Generate workout */}
      <div>
        <Button
          className="w-full"
          onClick={() => {
            setGenerateOpen((v) => !v);
            setGenerateStep("pick");
          }}
          disabled={generatingPlan || creatingSession}
        >
          <Zap className="h-4 w-4 mr-2" />
          Generate
        </Button>

        {generateOpen && (
          <Card className="mt-2">
            <CardContent className="p-4 space-y-3">
              {generateStep === "pick" && (
                <>
                  <p className="text-sm font-medium">What would you like to generate?</p>
                  <div className="grid gap-2">
                    <Button
                      variant="outline"
                      className="justify-start h-auto py-3"
                      disabled={generatingPlan}
                      onClick={handleGeneratePPL}
                    >
                      {generatingPlan ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-2 shrink-0" />
                      ) : (
                        <Zap className="h-4 w-4 mr-2 shrink-0" />
                      )}
                      <div className="text-left">
                        <div className="font-semibold">Push / Pull / Legs</div>
                        <div className="text-xs text-muted-foreground font-normal">
                          {isToday
                            ? "Full week plan starting today — appears in Today's Sessions"
                            : "Log Push, Pull, or Legs for this date"}
                        </div>
                      </div>
                    </Button>
                    <Button
                      variant="outline"
                      className="justify-start h-auto py-3"
                      onClick={() => setGenerateStep("muscle")}
                    >
                      <Dumbbell className="h-4 w-4 mr-2 shrink-0" />
                      <div className="text-left">
                        <div className="font-semibold">Specific Muscle</div>
                        <div className="text-xs text-muted-foreground font-normal">
                          Back, chest, biceps, legs, etc.
                        </div>
                      </div>
                    </Button>
                    <Button
                      variant="outline"
                      className="justify-start h-auto py-3"
                      onClick={handleGenerateMixed}
                    >
                      <Plus className="h-4 w-4 mr-2 shrink-0" />
                      <div className="text-left">
                        <div className="font-semibold">Mixed Workout</div>
                        <div className="text-xs text-muted-foreground font-normal">
                          Pick exercises from any muscle group
                        </div>
                      </div>
                    </Button>
                  </div>
                </>
              )}

              {generateStep === "muscle" && (
                <>
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">Choose a muscle group</p>
                    <Button variant="ghost" size="sm" onClick={() => setGenerateStep("pick")}>Back</Button>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {LOG_MUSCLE_OPTIONS.map((m) => (
                      <Button
                        key={m.key}
                        variant="outline"
                        size="sm"
                        className="h-auto py-2.5 flex-col gap-0.5"
                        onClick={() => handleGenerateMusclePick(m.key)}
                      >
                        <Dumbbell className="h-4 w-4" />
                        <span className="text-xs">{m.label}</span>
                      </Button>
                    ))}
                  </div>
                </>
              )}

              {generateStep === "ppl" && (
                <>
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">Which day for {selectedDate}?</p>
                    <Button variant="ghost" size="sm" onClick={() => setGenerateStep("pick")}>Back</Button>
                  </div>
                  <div className="grid gap-2">
                    {QUICK_SESSIONS.map((s) => (
                      <Button
                        key={s.name}
                        variant="outline"
                        onClick={() => handleGeneratePPLDay(s.name, s.muscles)}
                      >
                        {s.name}
                      </Button>
                    ))}
                  </div>
                </>
              )}

              <Button variant="ghost" size="sm" className="w-full" onClick={closeGenerate}>
                Cancel
              </Button>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Log by muscle group */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
          Log by Muscle
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {LOG_MUSCLE_OPTIONS.map((m) => (
            <Button
              key={m.key}
              variant="outline"
              size="sm"
              disabled={creatingSession}
              className="h-auto py-2.5 flex-col gap-0.5"
              onClick={() => handleSingleMuscle(m.key)}
            >
              <Dumbbell className="h-4 w-4" />
              <span className="text-xs">{m.label}</span>
            </Button>
          ))}
        </div>

        <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
          <Button
            variant="outline"
            disabled={creatingSession}
            onClick={() => setComboOpen((v) => !v)}
          >
            <Plus className="h-4 w-4 mr-2" />
            {COMBO_WORKOUT.label}
          </Button>
          <Button
            variant="outline"
            disabled={creatingSession}
            onClick={handleMixedWorkout}
          >
            <Plus className="h-4 w-4 mr-2" />
            {MIXED_WORKOUT.label}
          </Button>
        </div>

        {comboOpen && (
          <Card className="mt-2">
            <CardContent className="p-4 space-y-3">
              <p className="text-sm font-medium">Pick two muscle groups</p>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted-foreground">Muscle 1</label>
                  <select
                    value={comboMuscle1}
                    onChange={(e) => setComboMuscle1(e.target.value)}
                    className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                  >
                    {LOG_MUSCLE_OPTIONS.map((m) => (
                      <option key={m.key} value={m.key}>{m.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">Muscle 2</label>
                  <select
                    value={comboMuscle2}
                    onChange={(e) => setComboMuscle2(e.target.value)}
                    className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                  >
                    {LOG_MUSCLE_OPTIONS.map((m) => (
                      <option key={m.key} value={m.key}>{m.label}</option>
                    ))}
                  </select>
                </div>
              </div>
              <Button onClick={handleComboWorkout} disabled={creatingSession} className="w-full">
                {creatingSession ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                Start {buildComboLabel(
                  getLogMuscleOption(comboMuscle1)!,
                  getLogMuscleOption(comboMuscle2)!,
                )} Workout
              </Button>
            </CardContent>
          </Card>
        )}
        <div className="mt-2">
          {!customExerciseOpen ? (
            <Button
              variant="outline"
              className="w-full"
              onClick={() => setCustomExerciseOpen(true)}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add custom exercise
            </Button>
          ) : (
            <Card>
              <CardContent className="p-4 space-y-3">
                <p className="text-sm font-medium">Custom exercise</p>
                <Input
                  value={customExerciseName}
                  onChange={(e) => setCustomExerciseName(e.target.value)}
                  placeholder="e.g. Machine chest press"
                />
                <div>
                  <label className="text-xs text-muted-foreground">Primary muscle</label>
                  <select
                    value={customExerciseMuscle}
                    onChange={(e) => setCustomExerciseMuscle(e.target.value)}
                    className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                  >
                    {ALL_DB_MUSCLES.map((m) => (
                      <option key={m} value={m}>{m.replace(/_/g, " ")}</option>
                    ))}
                  </select>
                </div>
                <div className="flex gap-2">
                  <Button variant="ghost" className="flex-1" onClick={() => setCustomExerciseOpen(false)}>
                    Cancel
                  </Button>
                  <Button className="flex-1" onClick={handleAddCustomExercise} disabled={addingCustomExercise}>
                    {addingCustomExercise ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      "Create & plan workout"
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
        <div className="mt-2">
          <Button
            variant="outline"
            disabled={creatingSession || sessions.some((s) => isRestDaySession(s.session_name))}
            className="w-full"
            onClick={logRestDay}
          >
            {creatingSession ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <Moon className="h-4 w-4 mr-2" />
            )}
            Log Rest Day
          </Button>
        </div>
      </div>

      {/* Sessions for selected date */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
          {isToday ? "Today's Sessions" : "Sessions"}
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
                <p className="font-semibold">
                  {isToday ? "No sessions scheduled today" : "No sessions logged for this date"}
                </p>
                <p className="text-muted-foreground text-sm">
                  {isToday
                    ? "Generate a plan or it might be a rest day"
                    : "Add a workout to log sets for this day"}
                </p>
              </div>
              {isToday ? (
                <div className="flex flex-col gap-2 w-full max-w-xs">
                  <p className="text-xs text-muted-foreground">
                    Use the <strong>Generate</strong> button above to create a plan, or log a rest day.
                  </p>
                  <Button variant="outline" onClick={logRestDay} disabled={creatingSession}>
                    {creatingSession ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Moon className="h-4 w-4 mr-2" />}
                    Log Rest Day
                  </Button>
                </div>
              ) : (
                <div className="flex flex-col gap-2 w-full max-w-xs">
                  <p className="text-xs text-muted-foreground">
                    Use <strong>Generate</strong> above, or quickly log a day:
                  </p>
                  {QUICK_SESSIONS.map((s) => (
                    <Button
                      key={s.name}
                      variant="outline"
                      disabled={creatingSession}
                      onClick={() => createSessionForDate(s.name, s.muscles)}
                    >
                      {creatingSession ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
                      Log {s.name}
                    </Button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {showRemoveOption && removableSessions.length > 1 && (
              <p className="text-sm text-muted-foreground px-1">
                You have {removableSessions.length} workouts for this date — use <strong>Remove</strong> on any you don&apos;t need.
              </p>
            )}
            {sessions.map((s) => {
              const isRest = isRestDaySession(s.session_name);
              const confirming = confirmRemoveId === s.id;
              return (
              <Card key={s.id} className={cn(
                "transition-all",
                (s.status === "completed" || isRest) && "opacity-60",
                isRest && "border-muted",
              )}>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        {isRest && <Moon className="h-5 w-5 text-muted-foreground" />}
                        <span className="font-bold text-lg">{s.session_name}</span>
                        <Badge variant={
                          isRest ? "secondary" :
                          s.status === "completed" ? "success" :
                          s.status === "in_progress" ? "default" : "secondary"
                        }>
                          {isRest ? "rest" : s.status.replace("_", " ")}
                        </Badge>
                      </div>
                      {!isRest && (
                        <div className="flex gap-1 flex-wrap">
                          {s.muscle_groups.slice(0, 4).map((m) => <MuscleTag key={m} muscle={m} />)}
                        </div>
                      )}
                      {isRest ? (
                        <p className="text-xs text-muted-foreground mt-1">Recovery day — no training logged</p>
                      ) : s.sets_logged > 0 ? (
                        <p className="text-xs text-muted-foreground mt-1">
                          {s.status === "scheduled" ? "Plan ready · " : ""}{s.sets_logged} sets{s.status === "scheduled" ? " planned" : " logged"}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex flex-col items-end gap-2 shrink-0">
                      {confirming ? (
                        <div className="flex flex-col gap-2 items-stretch min-w-[140px]">
                          <p className="text-xs text-muted-foreground text-right">Remove this workout?</p>
                          <Button
                            variant="destructive"
                            size="sm"
                            disabled={deletingSessionId === s.id}
                            onClick={() => deleteSession(s)}
                          >
                            {deletingSessionId === s.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              "Yes, remove"
                            )}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setConfirmRemoveId(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      ) : (
                        <>
                          {showRemoveOption && !isRest && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-destructive border-destructive/40 hover:bg-destructive/10"
                              disabled={deletingSessionId === s.id}
                              onClick={() => setConfirmRemoveId(s.id)}
                            >
                              <Trash2 className="h-4 w-4 mr-1" />
                              Remove
                            </Button>
                          )}
                          {s.status === "completed" || isRest ? (
                            <CheckCircle2 className="h-8 w-8 text-green-400" />
                          ) : (
                            <Button onClick={() => resumeSession(s)} size="sm">
                              <Play className="h-4 w-4 mr-1" />
                              {s.status === "in_progress"
                                ? "Resume"
                                : s.sets_logged > 0
                                  ? "Review Plan"
                                  : "Start"}
                            </Button>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );})}
            {!isToday && (
              <div className="flex flex-wrap gap-2 pt-1">
                {QUICK_SESSIONS.map((s) => (
                  <Button
                    key={s.name}
                    variant="outline"
                    size="sm"
                    disabled={creatingSession}
                    onClick={() => createSessionForDate(s.name, s.muscles)}
                  >
                    <Plus className="h-3 w-3 mr-1" /> {s.name}
                  </Button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Recent workouts — all dates, click to open that day */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
          Recent Workouts
        </h2>
        {recentHistory.length === 0 ? (
          <p className="text-sm text-muted-foreground px-1">No workouts logged yet.</p>
        ) : (
          <div className="space-y-2">
            {recentHistory.map((s) => {
              const sessionDate = s.date ?? s.scheduled_date ?? "";
              const isSelected = sessionDate === selectedDate;
              return (
              <button
                key={s.id}
                type="button"
                onClick={() => setSelectedDate(sessionDate.slice(0, 10))}
                className={cn(
                  "flex w-full items-center justify-between rounded-lg border px-4 py-3 text-left transition-colors hover:bg-muted/40",
                  isSelected && "border-primary/50 bg-primary/5",
                )}
              >
                <div>
                  <span className="font-medium text-sm">{s.session_name}</span>
                  <p className="text-xs text-muted-foreground">
                    {formatSessionDay(sessionDate)}
                    {s.sets_logged ? ` · ${s.sets_logged} sets` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={
                    s.status === "completed" ? "success" :
                    s.status === "in_progress" ? "default" : "secondary"
                  } className="text-[10px] capitalize">
                    {(s.status ?? "completed").replace("_", " ")}
                  </Badge>
                  <div className="hidden sm:flex gap-1">
                    {(s.muscle_groups ?? []).slice(0, 2).map((m) => <MuscleTag key={m} muscle={m} />)}
                  </div>
                </div>
              </button>
            );})}
          </div>
        )}
      </div>
    </div>
  );
}
