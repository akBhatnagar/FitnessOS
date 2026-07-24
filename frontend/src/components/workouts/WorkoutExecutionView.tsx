"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  ArrowLeft, CheckCircle2, Dumbbell, Edit3, Loader2,
} from "lucide-react";
import { apiClient } from "@/services/api";
import { toast } from "sonner";
import { PlanExercise, computeSummary, weightColumnLabel } from "@/lib/workoutPlan";

interface SessionInfo {
  id: string;
  session_name: string;
  muscle_groups: string[];
  status: string;
}

interface SetActual {
  exercise_id: string;
  set_number: number;
  planned_weight_kg: number;
  planned_reps: number;
  actual_weight_kg: string;
  actual_reps: string;
}

function buildSetRows(exercises: PlanExercise[]): SetActual[] {
  const rows: SetActual[] = [];
  for (const ex of exercises) {
    for (const s of ex.sets) {
      rows.push({
        exercise_id: ex.exercise_id,
        set_number: s.set_number,
        planned_weight_kg: s.weight_kg,
        planned_reps: s.reps,
        actual_weight_kg: String(s.actual_weight_kg ?? s.weight_kg),
        actual_reps: String(s.actual_reps ?? s.reps),
      });
    }
  }
  return rows;
}

export function WorkoutExecutionView({
  session,
  onComplete,
  onBack,
  onEditPlan,
}: {
  session: SessionInfo;
  onComplete: () => void;
  onBack: () => void;
  onEditPlan?: () => void;
}) {
  const [exercises, setExercises] = useState<PlanExercise[]>([]);
  const [setRows, setSetRows] = useState<SetActual[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadPlan = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/workouts/sessions/${session.id}/plan`);
      const exs: PlanExercise[] = res.data.exercises ?? [];
      setExercises(exs);
      setSetRows(buildSetRows(exs));
    } catch {
      toast.error("Failed to load workout.");
    } finally {
      setLoading(false);
    }
  }, [session.id]);

  useEffect(() => {
    loadPlan();
  }, [loadPlan]);

  const updateActual = (
    exerciseId: string,
    setNumber: number,
    field: "actual_weight_kg" | "actual_reps",
    value: string,
  ) => {
    setSetRows((prev) =>
      prev.map((r) =>
        r.exercise_id === exerciseId && r.set_number === setNumber
          ? { ...r, [field]: value }
          : r,
      ),
    );
  };

  const filledCount = setRows.filter((r) => {
    const ex = exercises.find((e) => e.exercise_id === r.exercise_id);
    const repsOk = !!r.actual_reps && parseInt(r.actual_reps, 10) > 0;
    if (!repsOk) return false;
    if (ex?.weight_irrelevant) return true;
    return !!r.actual_weight_kg && parseFloat(r.actual_weight_kg) >= 0;
  }).length;

  const handleSaveWorkout = async () => {
    const toSave = setRows
      .map((r) => {
        const ex = exercises.find((e) => e.exercise_id === r.exercise_id);
        const reps = parseInt(r.actual_reps, 10);
        if (!r.actual_reps || Number.isNaN(reps) || reps <= 0) return null;
        const weight = ex?.weight_irrelevant
          ? 0
          : parseFloat(r.actual_weight_kg || "0");
        if (!ex?.weight_irrelevant && (r.actual_weight_kg === "" || Number.isNaN(weight))) {
          return null;
        }
        return {
          exercise_id: r.exercise_id,
          set_number: r.set_number,
          actual_weight_kg: weight,
          actual_reps: reps,
        };
      })
      .filter(Boolean) as Array<{
        exercise_id: string;
        set_number: number;
        actual_weight_kg: number;
        actual_reps: number;
      }>;

    if (toSave.length === 0) {
      toast.error("Log at least one set before saving.");
      return;
    }

    setSaving(true);
    try {
      await apiClient.post(`/api/v1/workouts/sessions/${session.id}/save-workout`, {
        sets: toSave,
      });
      toast.success(`Workout saved — ${toSave.length} sets logged`);
      onComplete();
    } catch {
      toast.error("Failed to save workout.");
    } finally {
      setSaving(false);
    }
  };

  const summary = computeSummary(exercises);

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto space-y-4 pb-24">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="h-4 w-4 mr-1" /> Back
        </Button>
        <div className="flex-1">
          <h2 className="text-xl font-bold">{session.session_name}</h2>
          <p className="text-xs text-muted-foreground">
            {summary.exercises} exercises · {summary.sets} sets · edit what you actually did
          </p>
        </div>
        {onEditPlan && session.status !== "completed" && (
          <Button variant="outline" size="sm" onClick={onEditPlan}>
            <Edit3 className="h-3.5 w-3.5 mr-1" /> Edit plan
          </Button>
        )}
      </div>

      <p className="text-sm text-muted-foreground">
        Planned weights are pre-filled. Change anything you did differently in the gym, then save.
      </p>

      <div className="space-y-3">
        {exercises.map((ex) => {
          const rows = setRows.filter((r) => r.exercise_id === ex.exercise_id);
          return (
            <Card key={ex.exercise_id}>
              <CardHeader className="py-3 px-4">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <Dumbbell className="h-4 w-4 text-muted-foreground" />
                  {ex.name}
                  <Badge variant="outline" className="text-[9px] ml-auto">{rows.length} sets</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4 pt-0 space-y-2">
                {(ex.load_display === "per_hand" || ex.weight_irrelevant) && (
                  <p className="text-[11px] text-amber-500/90">
                    {ex.weight_irrelevant
                      ? "Bodyweight — enter reps only."
                      : "Enter the weight of each dumbbell (not combined)."}
                  </p>
                )}
                <div className="grid grid-cols-[2rem_1fr_1fr] gap-2 text-[10px] text-muted-foreground font-medium px-1">
                  <span>Set</span>
                  <span>{weightColumnLabel(ex)}</span>
                  <span>Reps</span>
                </div>
                {rows.map((r) => (
                  <div key={r.set_number} className="grid grid-cols-[2rem_1fr_1fr] gap-2 items-center">
                    <span className="text-sm font-mono text-muted-foreground">{r.set_number}</span>
                    {ex.weight_irrelevant ? (
                      <div className="h-9 flex items-center rounded-md border bg-muted/40 px-3 text-xs text-muted-foreground">
                        Bodyweight
                      </div>
                    ) : (
                      <Input
                        type="number"
                        step="2.5"
                        value={r.actual_weight_kg}
                        onChange={(e) => updateActual(ex.exercise_id, r.set_number, "actual_weight_kg", e.target.value)}
                        className="h-9 font-mono"
                        placeholder={String(r.planned_weight_kg)}
                      />
                    )}
                    <Input
                      type="number"
                      value={r.actual_reps}
                      onChange={(e) => updateActual(ex.exercise_id, r.set_number, "actual_reps", e.target.value)}
                      className="h-9 font-mono"
                      placeholder={String(r.planned_reps)}
                    />
                  </div>
                ))}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="fixed bottom-0 left-0 right-0 p-4 bg-background/95 backdrop-blur border-t">
        <div className="max-w-xl mx-auto">
          <Button
            className="w-full h-12 text-base font-bold"
            disabled={saving || filledCount === 0}
            onClick={handleSaveWorkout}
          >
            {saving ? (
              <Loader2 className="h-5 w-5 animate-spin mr-2" />
            ) : (
              <CheckCircle2 className="h-5 w-5 mr-2" />
            )}
            Save Workout ({filledCount} sets)
          </Button>
        </div>
      </div>
    </div>
  );
}
