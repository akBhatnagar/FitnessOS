"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  ArrowLeft, Dumbbell, Loader2, Plus, RefreshCw, Search, Trash2, Zap,
} from "lucide-react";
import { apiClient } from "@/services/api";
import { toast } from "sonner";
import {
  PlanExercise,
  PlanAlternative,
  WorkoutPlanData,
  computeSummary,
  defaultSets,
  renumberSets,
  weightColumnLabel,
} from "@/lib/workoutPlan";
import { ALL_DB_MUSCLES } from "@/lib/workoutMuscles";

interface LibraryExercise {
  id: string;
  name: string;
  primary_muscle: string;
  is_compound: boolean;
  tips?: string;
  type?: string;
  tags?: string[];
  equipment?: string[];
  weight_irrelevant?: boolean;
  load_display?: string;
  load_label?: string;
  prescription?: {
    sets: number;
    reps_min: number;
    reps_max: number;
    weight_kg: number;
    notes?: string;
    set_plan: Array<{ set_number: number; weight_kg: number; reps: number }>;
  };
}

export interface PlanEditorConfig {
  sessionName: string;
  scheduledDate: string;
  muscleGroups: string[];
  sessionId?: string;
  preview?: {
    generation_type: string;
    goal?: string;
  };
  seedExercise?: {
    exercise_id: string;
    name: string;
    primary_muscle: string;
    is_compound: boolean;
  };
}

interface SessionResult {
  id: string;
  session_name: string;
  status: string;
  muscle_groups?: string[];
}

export function WorkoutPlanEditor({
  config,
  onBack,
  onSaved,
  onStartWorkout,
}: {
  config: PlanEditorConfig;
  onBack: () => void;
  onSaved: (session: SessionResult) => void;
  onStartWorkout: (session: SessionResult) => void;
}) {
  const [plan, setPlan] = useState<WorkoutPlanData | null>(null);
  const [exercises, setExercises] = useState<PlanExercise[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [addQuery, setAddQuery] = useState("");
  const [addResults, setAddResults] = useState<LibraryExercise[]>([]);
  const [browseOpen, setBrowseOpen] = useState(false);
  const [browseQuery, setBrowseQuery] = useState("");
  const [browseList, setBrowseList] = useState<LibraryExercise[]>([]);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customMuscle, setCustomMuscle] = useState(
    config.muscleGroups[0] ?? "chest",
  );
  const [addingCustom, setAddingCustom] = useState(false);
  const [altFor, setAltFor] = useState<string | null>(null);
  const [alternatives, setAlternatives] = useState<Array<LibraryExercise | PlanAlternative>>([]);
  const [loadingAlts, setLoadingAlts] = useState(false);

  const withSeedExercise = useCallback((list: PlanExercise[]): PlanExercise[] => {
    const seed = config.seedExercise;
    if (!seed || list.some((e) => e.exercise_id === seed.exercise_id)) {
      return list;
    }
    return [
      {
        exercise_id: seed.exercise_id,
        name: seed.name,
        primary_muscle: seed.primary_muscle,
        is_compound: seed.is_compound,
        sets: defaultSets(3),
      },
      ...list,
    ];
  }, [config.seedExercise]);

  const loadPlan = useCallback(async () => {
    setLoading(true);
    try {
      if (config.sessionId) {
        const res = await apiClient.get(`/api/v1/workouts/sessions/${config.sessionId}/plan`, {
          timeout: 90_000,
        });
        setPlan(res.data);
        setExercises(withSeedExercise(res.data.exercises ?? []));
      } else if (config.preview) {
        const res = await apiClient.post(
          "/api/v1/workouts/sessions/preview",
          {
            session_name: config.sessionName,
            muscle_groups: config.muscleGroups,
            generation_type: config.preview.generation_type,
            goal: config.preview.goal ?? "fat_loss",
          },
          { timeout: 120_000 },
        );
        setPlan(res.data);
        setExercises(withSeedExercise(res.data.exercises ?? []));
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load workout plan.";
      toast.error(msg.includes("timeout") ? "Plan generation timed out — try again." : msg);
    } finally {
      setLoading(false);
    }
  }, [config, withSeedExercise]);

  useEffect(() => {
    loadPlan();
  }, [loadPlan]);

  const summary = computeSummary(exercises);

  const persist = async (startWorkout: boolean) => {
    if (exercises.length === 0) {
      toast.error("Add at least one exercise to your plan.");
      return;
    }
    setSaving(true);
    try {
      const res = await apiClient.post("/api/v1/workouts/sessions/save-plan", {
        session_id: config.sessionId ?? plan?.session_id ?? null,
        session_name: config.sessionName,
        scheduled_date: config.scheduledDate,
        muscle_groups: config.muscleGroups,
        start_workout: startWorkout,
        exercises: exercises.map((ex) => ({
          exercise_id: ex.exercise_id,
          sets: ex.sets.map((s) => ({
            set_number: s.set_number,
            weight_kg: s.weight_kg,
            reps: s.reps,
          })),
        })),
      });
      const session: SessionResult = {
        id: res.data.id,
        session_name: res.data.session_name,
        status: res.data.status,
        muscle_groups: res.data.muscle_groups,
      };
      if (startWorkout) {
        toast.success("Plan confirmed — let's go!");
        onStartWorkout(session);
      } else {
        toast.success("Workout plan saved");
        onSaved(session);
      }
    } catch {
      toast.error("Failed to save plan.");
    } finally {
      setSaving(false);
    }
  };

  const updateSet = (exId: string, setIdx: number, field: "weight_kg" | "reps", value: number) => {
    setExercises((prev) =>
      prev.map((ex) =>
        ex.exercise_id !== exId
          ? ex
          : {
              ...ex,
              sets: ex.sets.map((s, i) =>
                i === setIdx ? { ...s, [field]: value } : s,
              ),
            },
      ),
    );
  };

  const addSet = (exId: string) => {
    setExercises((prev) =>
      prev.map((ex) => {
        if (ex.exercise_id !== exId) return ex;
        const last = ex.sets[ex.sets.length - 1];
        return {
          ...ex,
          sets: [
            ...ex.sets,
            {
              set_number: ex.sets.length + 1,
              weight_kg: last?.weight_kg ?? 20,
              reps: last?.reps ?? 10,
            },
          ],
        };
      }),
    );
  };

  const removeSet = (exId: string, setIdx: number) => {
    setExercises((prev) =>
      prev.map((ex) =>
        ex.exercise_id !== exId
          ? ex
          : { ...ex, sets: renumberSets(ex.sets.filter((_, i) => i !== setIdx)) },
      ),
    );
  };

  const removeExercise = (exId: string) => {
    setExercises((prev) => prev.filter((ex) => ex.exercise_id !== exId));
  };

  const searchToAdd = async (q: string) => {
    setAddQuery(q);
    if (!q.trim()) {
      setAddResults([]);
      return;
    }
    try {
      const res = await apiClient.get("/api/v1/workouts/exercises", {
        params: { query: q, limit: "8", modality: "gym" },
      });
      setAddResults(
        res.data.filter(
          (e: LibraryExercise) => !exercises.some((x) => x.exercise_id === e.id),
        ),
      );
    } catch {
      setAddResults([]);
    }
  };

  const openBrowse = async () => {
    setBrowseOpen(true);
    setBrowseLoading(true);
    try {
      const res = await apiClient.get("/api/v1/workouts/exercises", {
        params: { limit: "120", modality: "gym" },
      });
      setBrowseList(res.data);
    } catch {
      toast.error("Failed to load exercises.");
    } finally {
      setBrowseLoading(false);
    }
  };

  const filteredBrowse = browseList.filter((e) => {
    if (exercises.some((x) => x.exercise_id === e.id)) return false;
    if (!browseQuery.trim()) return true;
    const q = browseQuery.toLowerCase();
    return (
      e.name.toLowerCase().includes(q)
      || e.primary_muscle.toLowerCase().includes(q)
    );
  });

  const addExercise = (lib: LibraryExercise) => {
    setExercises((prev) => [
      ...prev,
      {
        exercise_id: lib.id,
        name: lib.name,
        primary_muscle: lib.primary_muscle,
        is_compound: lib.is_compound,
        tips: lib.tips,
        sets: defaultSets(3),
      },
    ]);
    setAddQuery("");
    setAddResults([]);
    setBrowseOpen(false);
    toast.success(`${lib.name} added`);
  };

  const createCustomExercise = async () => {
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
      addExercise(res.data);
      setCustomName("");
      setCustomOpen(false);
      // Refresh browse list if open
      if (browseOpen) {
        const list = await apiClient.get("/api/v1/workouts/exercises", {
          params: { limit: "120", modality: "gym" },
        });
        setBrowseList(list.data);
      }
    } catch {
      toast.error("Failed to add custom exercise.");
    } finally {
      setAddingCustom(false);
    }
  };

  const loadAlternatives = async (ex: PlanExercise) => {
    setAltFor(ex.exercise_id);
    // Prefer alternatives baked into the AI/plan response — no extra API call
    if (ex.alternatives && ex.alternatives.length > 0) {
      const inPlan = new Set(exercises.map((e) => e.exercise_id));
      const filtered = ex.alternatives.filter((a) => !inPlan.has(a.id));
      setAlternatives(filtered);
      setLoadingAlts(false);
      if (filtered.length === 0) toast.info("No unused alternatives for this exercise.");
      return;
    }
    setLoadingAlts(true);
    try {
      const exclude = exercises.map((e) => e.exercise_id).join(",");
      const res = await apiClient.get(
        `/api/v1/workouts/exercises/${ex.exercise_id}/alternatives?exclude_ids=${exclude}&limit=5`,
      );
      setAlternatives(res.data);
      if (res.data.length === 0) toast.info("No alternatives found for this exercise.");
    } catch {
      toast.error("Failed to load alternatives.");
    } finally {
      setLoadingAlts(false);
    }
  };

  const swapExercise = (fromId: string, alt: LibraryExercise | PlanAlternative) => {
    const planSets = alt.prescription?.set_plan;
    const newSets = planSets && planSets.length > 0
      ? planSets.map((s) => ({
          set_number: s.set_number,
          weight_kg: alt.weight_irrelevant ? 0 : s.weight_kg,
          reps: s.reps,
        }))
      : defaultSets(
          alt.prescription?.sets ?? 3,
          alt.weight_irrelevant ? 0 : (alt.prescription?.weight_kg ?? 20),
          alt.prescription?.reps_min ?? 10,
        );

    setExercises((prev) =>
      prev.map((ex) =>
        ex.exercise_id !== fromId
          ? ex
          : {
              exercise_id: alt.id,
              name: alt.name,
              primary_muscle: alt.primary_muscle,
              is_compound: alt.is_compound,
              tips: alt.tips,
              notes: alt.prescription?.notes,
              sets: newSets,
              weight_irrelevant: alt.weight_irrelevant,
              load_display: alt.load_display,
              load_label: alt.load_label,
              equipment: alt.equipment,
              alternatives: undefined,
            },
      ),
    );
    setAltFor(null);
    setAlternatives([]);
    const w = newSets[0]?.weight_kg;
    const r = newSets[0]?.reps;
    toast.success(
      alt.weight_irrelevant
        ? `Swapped to ${alt.name} — ${newSets.length} sets × ${r} reps (bodyweight)`
        : w != null && w > 0
          ? `Swapped to ${alt.name} — ${newSets.length}×${r} @ ${w}kg`
          : `Swapped to ${alt.name} — ${newSets.length} sets × ${r} reps`,
    );
  };

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto space-y-4 pb-8">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="h-4 w-4 mr-1" /> Back
        </Button>
        <div className="flex-1">
          <h2 className="text-xl font-bold">{config.sessionName}</h2>
          <p className="text-xs text-muted-foreground">Review & edit your plan before working out</p>
        </div>
      </div>

      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="p-4 flex items-center justify-between gap-4">
          <div className="flex gap-6 text-sm">
            <div>
              <p className="text-muted-foreground text-xs">Exercises</p>
              <p className="text-2xl font-bold">{summary.exercises}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">Total sets</p>
              <p className="text-2xl font-bold">{summary.sets}</p>
            </div>
          </div>
          <Zap className="h-8 w-8 text-primary opacity-60" />
        </CardContent>
      </Card>

      {plan?.personalization && plan.personalization.length > 0 && (
        <p className="text-xs text-muted-foreground px-1">{plan.personalization[0]}</p>
      )}

      <div className="space-y-3">
        {exercises.map((ex) => (
          <Card key={ex.exercise_id}>
            <CardHeader className="py-3 px-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <Dumbbell className="h-4 w-4 shrink-0 text-muted-foreground" />
                    {ex.name}
                  </CardTitle>
                  <div className="flex gap-1 mt-1 flex-wrap">
                    <Badge variant="outline" className="text-[9px] capitalize">
                      {ex.primary_muscle.replace(/_/g, " ")}
                    </Badge>
                    {ex.is_compound && (
                      <Badge variant="secondary" className="text-[9px]">Compound</Badge>
                    )}
                    <Badge variant="secondary" className="text-[9px]">{ex.sets.length} sets</Badge>
                  </div>
                </div>
                <div className="flex gap-1 shrink-0">
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-xs h-8"
                    onClick={() => loadAlternatives(ex)}
                  >
                    <RefreshCw className="h-3 w-3 mr-1" />
                    Alt
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 text-destructive hover:text-destructive"
                    onClick={() => removeExercise(ex.exercise_id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-4 pt-0 space-y-2">
              {ex.notes && (
                <p className="text-[11px] text-muted-foreground">{ex.notes}</p>
              )}
              {(ex.load_display === "per_hand" || ex.weight_irrelevant) && (
                <p className="text-[11px] text-amber-500/90">
                  {ex.weight_irrelevant
                    ? "Bodyweight — weight is not used for this movement."
                    : "Log the weight of each dumbbell (not both combined)."}
                </p>
              )}
              {altFor === ex.exercise_id && (
                <div className="rounded-lg border bg-muted/30 p-2 space-y-1">
                  <p className="text-xs font-medium text-muted-foreground">Alternatives</p>
                  {loadingAlts ? (
                    <Loader2 className="h-4 w-4 animate-spin mx-auto my-2" />
                  ) : alternatives.length === 0 ? (
                    <p className="text-xs text-muted-foreground px-2 py-1">No alternatives available</p>
                  ) : (
                    alternatives.map((alt) => (
                      <button
                        key={alt.id}
                        type="button"
                        className="w-full text-left text-sm px-2 py-1.5 rounded hover:bg-muted"
                        onClick={() => swapExercise(ex.exercise_id, alt)}
                      >
                        <div className="font-medium">{alt.name}</div>
                        {alt.prescription && (
                          <div className="text-[11px] text-muted-foreground">
                            {alt.prescription.sets} sets × {alt.prescription.reps_min}
                            {alt.prescription.reps_max !== alt.prescription.reps_min
                              ? `-${alt.prescription.reps_max}`
                              : ""}{" "}
                            reps
                            {alt.weight_irrelevant
                              ? " · bodyweight"
                              : alt.prescription.weight_kg > 0
                                ? ` @ ${alt.prescription.weight_kg}kg${alt.load_display === "per_hand" ? " each" : ""}`
                                : ""}
                          </div>
                        )}
                      </button>
                    ))
                  )}
                  <Button variant="ghost" size="sm" className="w-full h-7 text-xs" onClick={() => setAltFor(null)}>
                    Cancel
                  </Button>
                </div>
              )}
              <div className="grid grid-cols-[2rem_1fr_1fr_2rem] gap-2 text-[10px] text-muted-foreground font-medium px-1">
                <span>Set</span>
                <span>{weightColumnLabel(ex)}</span>
                <span>Reps</span>
                <span />
              </div>
              {ex.sets.map((s, idx) => (
                <div key={s.set_number} className="grid grid-cols-[2rem_1fr_1fr_2rem] gap-2 items-center">
                  <span className="text-sm font-mono text-muted-foreground">{s.set_number}</span>
                  {ex.weight_irrelevant ? (
                    <div className="h-9 flex items-center rounded-md border bg-muted/40 px-3 text-xs text-muted-foreground">
                      Bodyweight
                    </div>
                  ) : (
                    <Input
                      type="number"
                      step="2.5"
                      value={s.weight_kg}
                      onChange={(e) => updateSet(ex.exercise_id, idx, "weight_kg", parseFloat(e.target.value) || 0)}
                      className="h-9 font-mono"
                    />
                  )}
                  <Input
                    type="number"
                    value={s.reps}
                    onChange={(e) => updateSet(ex.exercise_id, idx, "reps", parseInt(e.target.value, 10) || 0)}
                    className="h-9 font-mono"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-9 w-9 p-0"
                    disabled={ex.sets.length <= 1}
                    onClick={() => removeSet(ex.exercise_id, idx)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
              <Button variant="outline" size="sm" className="w-full h-8 text-xs" onClick={() => addSet(ex.exercise_id)}>
                <Plus className="h-3 w-3 mr-1" /> Add set
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardContent className="p-4 space-y-3">
          <p className="text-sm font-medium">Add exercise</p>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                value={addQuery}
                onChange={(e) => searchToAdd(e.target.value)}
                placeholder="Search exercises..."
                className="pl-9"
              />
            </div>
            <Button variant="outline" onClick={openBrowse} className="shrink-0">
              <Dumbbell className="h-4 w-4 mr-1" />
              Browse all
            </Button>
          </div>
          {addResults.length > 0 && (
            <div className="rounded-lg border divide-y max-h-40 overflow-y-auto">
              {addResults.map((lib) => (
                <button
                  key={lib.id}
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm hover:bg-muted/50 flex items-center justify-between gap-2"
                  onClick={() => addExercise(lib)}
                >
                  <span>{lib.name}</span>
                  <Plus className="h-3.5 w-3.5 shrink-0 text-primary" />
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {browseOpen && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 p-0 sm:p-4">
          <div className="w-full sm:max-w-lg max-h-[85vh] bg-background border rounded-t-xl sm:rounded-xl shadow-xl flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <div>
                <p className="font-semibold">Exercise library</p>
                <p className="text-xs text-muted-foreground">Gym exercises only — swimming is separate</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setBrowseOpen(false)}>Close</Button>
            </div>
            <div className="p-3 border-b space-y-2">
              <Input
                value={browseQuery}
                onChange={(e) => setBrowseQuery(e.target.value)}
                placeholder="Filter exercises..."
              />
              {!customOpen ? (
                <Button variant="outline" size="sm" className="w-full" onClick={() => setCustomOpen(true)}>
                  <Plus className="h-3.5 w-3.5 mr-1" /> Add new custom exercise
                </Button>
              ) : (
                <div className="rounded-lg border p-3 space-y-2">
                  <Input
                    value={customName}
                    onChange={(e) => setCustomName(e.target.value)}
                    placeholder="Custom exercise name"
                  />
                  <select
                    value={customMuscle}
                    onChange={(e) => setCustomMuscle(e.target.value)}
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                  >
                    {[...new Set([...config.muscleGroups, ...ALL_DB_MUSCLES])].map((m) => (
                      <option key={m} value={m}>{m.replace(/_/g, " ")}</option>
                    ))}
                  </select>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" className="flex-1" onClick={() => setCustomOpen(false)}>Cancel</Button>
                    <Button size="sm" className="flex-1" onClick={createCustomExercise} disabled={addingCustom}>
                      {addingCustom ? <Loader2 className="h-4 w-4 animate-spin" /> : "Create & add"}
                    </Button>
                  </div>
                </div>
              )}
            </div>
            <div className="flex-1 overflow-y-auto divide-y">
              {browseLoading ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : filteredBrowse.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">No exercises found</p>
              ) : (
                filteredBrowse.map((lib) => (
                  <div key={lib.id} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{lib.name}</p>
                      <p className="text-[11px] text-muted-foreground capitalize">
                        {lib.primary_muscle.replace(/_/g, " ")}
                        {lib.is_compound ? " · Compound" : ""}
                      </p>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => addExercise(lib)}>
                      <Plus className="h-3.5 w-3.5 mr-1" /> Add
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      <div className="sticky bottom-0 bg-background/95 backdrop-blur border-t pt-3 space-y-2 -mx-1 px-1">
        <Button
          className="w-full h-12 font-bold"
          disabled={saving || exercises.length === 0}
          onClick={() => persist(true)}
        >
          {saving ? <Loader2 className="h-5 w-5 animate-spin mr-2" /> : <Zap className="h-5 w-5 mr-2" />}
          Confirm Plan & Start Workout
        </Button>
        <Button
          variant="outline"
          className="w-full"
          disabled={saving || exercises.length === 0}
          onClick={() => persist(false)}
        >
          Save Plan for Later
        </Button>
      </div>
    </div>
  );
}
