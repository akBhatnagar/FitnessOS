"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  CheckCircle2, ChevronDown, Loader2, Plus, Dumbbell, ArrowLeft,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/services/api";
import { toast } from "sonner";

export interface Exercise {
  id: string;
  name: string;
  slug: string;
  primary_muscle: string;
  is_compound: boolean;
  tags: string[];
  tips?: string;
}

export interface SetRow {
  exercise_id: string;
  exercise_name: string;
  set_number: number;
  actual_reps?: number;
  actual_weight_kg?: number;
}

interface SessionInfo {
  id: string;
  session_name: string;
  muscle_groups: string[];
}

function MuscleTag({ muscle }: { muscle: string }) {
  return (
    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold capitalize">
      {muscle.replace(/_/g, " ")}
    </span>
  );
}

function ExerciseSetLogger({
  sessionId,
  exercise,
  existingSets,
  onSetLogged,
}: {
  sessionId: string;
  exercise: Exercise;
  existingSets: SetRow[];
  onSetLogged: (set: SetRow) => void;
}) {
  const [weight, setWeight] = useState("");
  const [reps, setReps] = useState("");
  const [logging, setLogging] = useState(false);
  const nextSet = existingSets.length + 1;

  const handleLog = async () => {
    if (!weight || !reps) {
      toast.error("Enter weight and reps for this set.");
      return;
    }
    setLogging(true);
    try {
      await apiClient.post(`/api/v1/workouts/sessions/${sessionId}/sets`, {
        exercise_id: exercise.id,
        set_number: nextSet,
        actual_weight_kg: parseFloat(weight),
        actual_reps: parseInt(reps, 10),
      });
      onSetLogged({
        exercise_id: exercise.id,
        exercise_name: exercise.name,
        set_number: nextSet,
        actual_weight_kg: parseFloat(weight),
        actual_reps: parseInt(reps, 10),
      });
      setReps("");
      toast.success(`Set ${nextSet} logged`);
    } catch {
      toast.error("Failed to log set.");
    } finally {
      setLogging(false);
    }
  };

  return (
    <div className="space-y-3">
      {existingSets.length > 0 && (
        <div className="space-y-1.5">
          {existingSets.map((s) => (
            <div key={s.set_number} className="flex items-center justify-between rounded-lg bg-muted/30 px-3 py-2 text-sm">
              <span className="text-muted-foreground font-mono">Set {s.set_number}</span>
              <span className="font-bold">{s.actual_weight_kg}kg × {s.actual_reps}</span>
              <CheckCircle2 className="h-4 w-4 text-green-400" />
            </div>
          ))}
        </div>
      )}
      <div className="rounded-lg border border-dashed p-3 space-y-2">
        <p className="text-xs font-semibold text-muted-foreground">Set {nextSet}</p>
        <div className="flex gap-2">
          <div className="flex-1">
            <label className="text-[10px] text-muted-foreground">Weight (kg)</label>
            <Input
              value={weight}
              onChange={(e) => setWeight(e.target.value)}
              type="number"
              step="2.5"
              placeholder="kg"
              className="font-mono h-10"
            />
          </div>
          <div className="flex-1">
            <label className="text-[10px] text-muted-foreground">Reps</label>
            <Input
              value={reps}
              onChange={(e) => setReps(e.target.value)}
              type="number"
              placeholder="reps"
              className="font-mono h-10"
            />
          </div>
        </div>
        <Button onClick={handleLog} disabled={logging} size="sm" className="w-full">
          {logging ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
          Log Set {nextSet}
        </Button>
      </div>
    </div>
  );
}

export function MuscleWorkoutView({
  session,
  dbMuscles,
  defaultPrimaryMuscle,
  onComplete,
  onBack,
}: {
  session: SessionInfo;
  dbMuscles: string[];
  defaultPrimaryMuscle: string;
  onComplete: () => void;
  onBack: () => void;
}) {
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loggedSets, setLoggedSets] = useState<Record<string, SetRow[]>>({});
  const [completing, setCompleting] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customMuscle, setCustomMuscle] = useState(defaultPrimaryMuscle);
  const [addingCustom, setAddingCustom] = useState(false);

  const loadSessionSets = async (): Promise<Set<string>> => {
    const ids = new Set<string>();
    try {
      const res = await apiClient.get(`/api/v1/workouts/sessions/${session.id}/sets`);
      const grouped: Record<string, SetRow[]> = {};
      for (const row of res.data) {
        ids.add(row.exercise_id);
        if (!grouped[row.exercise_id]) grouped[row.exercise_id] = [];
        grouped[row.exercise_id].push({
          exercise_id: row.exercise_id,
          exercise_name: row.exercise_name,
          set_number: row.set_number,
          actual_weight_kg: row.actual_weight_kg ?? undefined,
          actual_reps: row.actual_reps ?? undefined,
        });
      }
      for (const id of Object.keys(grouped)) {
        grouped[id].sort((a, b) => a.set_number - b.set_number);
      }
      setLoggedSets(grouped);
      const firstWithSets = Object.keys(grouped).find((id) => grouped[id].length > 0);
      if (firstWithSets) setExpandedId(firstWithSets);
    } catch {
      toast.error("Failed to load logged sets.");
    }
    return ids;
  };

  useEffect(() => {
    let cancelled = false;

    async function init() {
      setLoading(true);
      const loggedExerciseIds = await loadSessionSets();
      if (cancelled) return;

      try {
        const params: Record<string, string> = {};
        if (dbMuscles.length > 0) {
          params.muscle_groups = dbMuscles.join(",");
        }
        const res = await apiClient.get("/api/v1/workouts/exercises", { params });
        let list: Exercise[] = res.data;

        for (const id of loggedExerciseIds) {
          if (list.some((e) => e.id === id)) continue;
          try {
            const detail = await apiClient.get(`/api/v1/workouts/exercises/${id}`);
            list = [
              ...list,
              {
                id: detail.data.id,
                name: detail.data.name,
                slug: detail.data.slug,
                primary_muscle: detail.data.primary_muscle,
                is_compound: detail.data.is_compound,
                tags: detail.data.tags ?? [],
                tips: detail.data.tips,
              },
            ];
          } catch {
            /* exercise may have been removed */
          }
        }

        if (!cancelled) setExercises(list);
      } catch {
        if (!cancelled) toast.error("Failed to load exercises.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    init();
    return () => { cancelled = true; };
  }, [session.id, dbMuscles.join(",")]);

  const handleSetLogged = (set: SetRow) => {
    setLoggedSets((prev) => ({
      ...prev,
      [set.exercise_id]: [...(prev[set.exercise_id] ?? []), set],
    }));
  };

  const addCustomExercise = async () => {
    const name = customName.trim();
    if (!name) {
      toast.error("Enter an exercise name.");
      return;
    }
    setAddingCustom(true);
    try {
      const res = await apiClient.post("/api/v1/workouts/exercises", {
        name,
        primary_muscle: customMuscle,
        is_compound: false,
      });
      const created: Exercise = res.data;
      setExercises((prev) => {
        if (prev.some((e) => e.id === created.id)) return prev;
        return [...prev, created].sort((a, b) => a.name.localeCompare(b.name));
      });
      setExpandedId(created.id);
      setCustomName("");
      setShowCustom(false);
      toast.success(`${created.name} added to your exercise list`);
    } catch {
      toast.error("Failed to add custom exercise.");
    } finally {
      setAddingCustom(false);
    }
  };

  const totalSets = Object.values(loggedSets).flat().length;

  const handleComplete = async () => {
    setCompleting(true);
    try {
      await apiClient.post(`/api/v1/workouts/sessions/${session.id}/complete`, {});
      toast.success("Workout logged!");
      onComplete();
    } catch {
      toast.error("Failed to save workout.");
    } finally {
      setCompleting(false);
    }
  };

  return (
    <div className="max-w-xl mx-auto space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="h-4 w-4 mr-1" /> Back
        </Button>
        <div className="flex-1">
          <h2 className="text-xl font-bold">{session.session_name}</h2>
          <p className="text-xs text-muted-foreground">{totalSets} sets logged</p>
        </div>
      </div>

      <p className="text-sm text-muted-foreground">
        Select an exercise, log each set with weight and reps, then finish when done.
      </p>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="space-y-2">
          {exercises.length === 0 && (
            <Card className="border-dashed">
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                No exercises found for this muscle group. Add a custom exercise below.
              </CardContent>
            </Card>
          )}
          {exercises.map((ex) => {
            const sets = loggedSets[ex.id] ?? [];
            const expanded = expandedId === ex.id;
            return (
              <Card key={ex.id} className={cn(expanded && "border-primary/40")}>
                <button
                  type="button"
                  className="w-full text-left"
                  onClick={() => setExpandedId(expanded ? null : ex.id)}
                >
                  <CardHeader className="py-3 px-4">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <Dumbbell className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <CardTitle className="text-sm font-semibold truncate">{ex.name}</CardTitle>
                        {ex.tags.includes("custom") && (
                          <Badge variant="secondary" className="text-[9px]">Custom</Badge>
                        )}
                        {sets.length > 0 && (
                          <Badge variant="success" className="text-[9px]">{sets.length} sets</Badge>
                        )}
                      </div>
                      <ChevronDown className={cn("h-4 w-4 shrink-0 transition-transform", expanded && "rotate-180")} />
                    </div>
                    <div className="flex gap-1 mt-1">
                      <MuscleTag muscle={ex.primary_muscle} />
                      {ex.is_compound && (
                        <Badge variant="outline" className="text-[9px]">Compound</Badge>
                      )}
                    </div>
                  </CardHeader>
                </button>
                {expanded && (
                  <CardContent className="pt-0 px-4 pb-4">
                    {ex.tips && (
                      <p className="text-xs text-muted-foreground mb-3">{ex.tips}</p>
                    )}
                    <ExerciseSetLogger
                      sessionId={session.id}
                      exercise={ex}
                      existingSets={sets}
                      onSetLogged={handleSetLogged}
                    />
                  </CardContent>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {/* Custom exercise */}
      <Card>
        <CardContent className="p-4 space-y-3">
          {!showCustom ? (
            <Button variant="outline" className="w-full" onClick={() => setShowCustom(true)}>
              <Plus className="h-4 w-4 mr-2" /> Exercise not listed? Add custom
            </Button>
          ) : (
            <div className="space-y-3">
              <p className="text-sm font-semibold">Add custom exercise</p>
              <Input
                value={customName}
                onChange={(e) => setCustomName(e.target.value)}
                placeholder="e.g. Machine chest press"
              />
              <div>
                <label className="text-xs text-muted-foreground">Primary muscle</label>
                <select
                  value={customMuscle}
                  onChange={(e) => setCustomMuscle(e.target.value)}
                  className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                >
                  {dbMuscles.map((m) => (
                    <option key={m} value={m}>{m.replace(/_/g, " ")}</option>
                  ))}
                </select>
              </div>
              <div className="flex gap-2">
                <Button variant="ghost" className="flex-1" onClick={() => setShowCustom(false)}>Cancel</Button>
                <Button className="flex-1" onClick={addCustomExercise} disabled={addingCustom}>
                  {addingCustom ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add & log sets"}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Button
        onClick={handleComplete}
        disabled={completing || totalSets === 0}
        className="w-full h-12 text-base font-bold"
      >
        {completing ? <Loader2 className="h-5 w-5 animate-spin mr-2" /> : <CheckCircle2 className="h-5 w-5 mr-2" />}
        Finish Workout ({totalSets} sets)
      </Button>
    </div>
  );
}
