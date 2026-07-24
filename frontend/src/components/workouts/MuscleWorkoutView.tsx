"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  CheckCircle2, ChevronDown, Loader2, Plus, Dumbbell, ArrowLeft, Search,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/services/api";
import { toast } from "sonner";
import { ALL_DB_MUSCLES } from "@/lib/workoutMuscles";

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
  plannedSets,
  onSetLogged,
}: {
  sessionId: string;
  exercise: Exercise;
  existingSets: SetRow[];
  plannedSets?: Array<{ set_number: number; planned_weight_kg?: number | null; planned_reps?: number | null }>;
  onSetLogged: (set: SetRow) => void;
}) {
  const nextPlanned = plannedSets?.find((p) => p.set_number === existingSets.length + 1);
  const [weight, setWeight] = useState(nextPlanned?.planned_weight_kg?.toString() ?? "");
  const [reps, setReps] = useState(nextPlanned?.planned_reps?.toString() ?? "");
  const [logging, setLogging] = useState(false);
  const nextSet = existingSets.length + 1;

  useEffect(() => {
    const planned = plannedSets?.find((p) => p.set_number === nextSet);
    if (planned?.planned_weight_kg != null) setWeight(String(planned.planned_weight_kg));
    if (planned?.planned_reps != null) setReps(String(planned.planned_reps));
  }, [nextSet, plannedSets]);

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
  const [plannedSets, setPlannedSets] = useState<Record<string, Array<{ set_number: number; planned_weight_kg?: number | null; planned_reps?: number | null }>>>({});
  const [generatedExerciseIds, setGeneratedExerciseIds] = useState<string[]>([]);
  const [completing, setCompleting] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customMuscle, setCustomMuscle] = useState(defaultPrimaryMuscle);
  const [addingCustom, setAddingCustom] = useState(false);

  const [browseOpen, setBrowseOpen] = useState(false);
  const [browseQuery, setBrowseQuery] = useState("");
  const [browseList, setBrowseList] = useState<Exercise[]>([]);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [addQuery, setAddQuery] = useState("");
  const [addResults, setAddResults] = useState<Exercise[]>([]);

  const muscleOptions = useMemo(
    () => [...new Set([...dbMuscles, ...ALL_DB_MUSCLES])],
    [dbMuscles],
  );

  const loadSessionSets = async (): Promise<{ ids: Set<string>; plannedOrder: string[] }> => {
    const ids = new Set<string>();
    const plannedOrder: string[] = [];
    try {
      const res = await apiClient.get(`/api/v1/workouts/sessions/${session.id}/sets`);
      const grouped: Record<string, SetRow[]> = {};
      const planned: typeof plannedSets = {};
      for (const row of res.data) {
        ids.add(row.exercise_id);
        if (!plannedOrder.includes(row.exercise_id)) plannedOrder.push(row.exercise_id);
        if (!grouped[row.exercise_id]) grouped[row.exercise_id] = [];
        if (!planned[row.exercise_id]) planned[row.exercise_id] = [];
        planned[row.exercise_id].push({
          set_number: row.set_number,
          planned_weight_kg: row.planned_weight_kg,
          planned_reps: row.planned_reps,
        });
        if (row.actual_weight_kg != null && row.actual_reps != null) {
          grouped[row.exercise_id].push({
            exercise_id: row.exercise_id,
            exercise_name: row.exercise_name,
            set_number: row.set_number,
            actual_weight_kg: row.actual_weight_kg ?? undefined,
            actual_reps: row.actual_reps ?? undefined,
          });
        }
      }
      for (const id of Object.keys(grouped)) {
        grouped[id].sort((a, b) => a.set_number - b.set_number);
      }
      for (const id of Object.keys(planned)) {
        planned[id].sort((a, b) => a.set_number - b.set_number);
      }
      setLoggedSets(grouped);
      setPlannedSets(planned);
      setGeneratedExerciseIds(plannedOrder);
      const firstWithSets = Object.keys(grouped).find((id) => grouped[id].length > 0);
      const firstPlanned = plannedOrder[0];
      if (firstWithSets) setExpandedId(firstWithSets);
      else if (firstPlanned) setExpandedId(firstPlanned);
    } catch {
      toast.error("Failed to load logged sets.");
    }
    return { ids, plannedOrder };
  };

  useEffect(() => {
    let cancelled = false;

    async function init() {
      setLoading(true);
      const { ids: loggedExerciseIds, plannedOrder } = await loadSessionSets();
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

        if (!cancelled) {
          const generated = list.filter((e) => plannedOrder.includes(e.id));
          const rest = list.filter((e) => !plannedOrder.includes(e.id));
          const ordered = [
            ...plannedOrder
              .map((id) => generated.find((e) => e.id === id))
              .filter(Boolean) as Exercise[],
            ...rest.sort((a, b) => a.name.localeCompare(b.name)),
          ];
          setExercises(ordered);
        }
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

  const addExerciseToList = (created: Exercise) => {
    setExercises((prev) => {
      if (prev.some((e) => e.id === created.id)) return prev;
      return [...prev, created];
    });
    setExpandedId(created.id);
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
      addExerciseToList(created);
      setCustomName("");
      setShowCustom(false);
      toast.success(`${created.name} added to your exercise list`);
    } catch {
      toast.error("Failed to add custom exercise.");
    } finally {
      setAddingCustom(false);
    }
  };

  const openBrowse = async () => {
    setBrowseOpen(true);
    setBrowseLoading(true);
    try {
      const res = await apiClient.get("/api/v1/workouts/exercises", {
        params: { modality: "gym", limit: 200 },
      });
      setBrowseList(res.data);
    } catch {
      toast.error("Failed to load exercise library.");
    } finally {
      setBrowseLoading(false);
    }
  };

  const searchToAdd = async (q: string) => {
    setAddQuery(q);
    if (!q.trim()) {
      setAddResults([]);
      return;
    }
    try {
      const res = await apiClient.get("/api/v1/workouts/exercises", {
        params: { query: q.trim(), modality: "gym", limit: 40 },
      });
      const existing = new Set(exercises.map((e) => e.id));
      setAddResults(
        (res.data as Exercise[])
          .filter((e) => !existing.has(e.id))
          .slice(0, 8),
      );
    } catch {
      setAddResults([]);
    }
  };

  const filteredBrowse = browseList.filter((e) => {
    if (exercises.some((x) => x.id === e.id)) return false;
    if (!browseQuery.trim()) return true;
    const q = browseQuery.toLowerCase();
    return (
      e.name.toLowerCase().includes(q)
      || e.primary_muscle.toLowerCase().includes(q)
    );
  });

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
        {generatedExerciseIds.length > 0
          ? "Your personalized exercises are listed first — weights are pre-filled from your history and goals."
          : "Select an exercise, log each set with weight and reps, then finish when done."}
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
                No exercises found for this muscle group. Browse the library or add a custom exercise below.
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
                        {plannedSets[ex.id]?.length > 0 && sets.length === 0 && (
                          <Badge variant="secondary" className="text-[9px]">Suggested</Badge>
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
                      plannedSets={plannedSets[ex.id]}
                      onSetLogged={handleSetLogged}
                    />
                  </CardContent>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {/* Search + browse library */}
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
                  onClick={() => {
                    addExerciseToList(lib);
                    setAddQuery("");
                    setAddResults([]);
                    toast.success(`${lib.name} added`);
                  }}
                >
                  <span className="truncate">{lib.name}</span>
                  <span className="text-[10px] text-muted-foreground capitalize shrink-0">
                    {lib.primary_muscle.replace(/_/g, " ")}
                  </span>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

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
                placeholder="e.g. Dumbbell shrugs"
              />
              <div>
                <label className="text-xs text-muted-foreground">Primary muscle</label>
                <select
                  value={muscleOptions.includes(customMuscle) ? customMuscle : muscleOptions[0]}
                  onChange={(e) => setCustomMuscle(e.target.value)}
                  className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                >
                  {muscleOptions.map((m) => (
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

      {browseOpen && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 p-0 sm:p-4">
          <div className="w-full sm:max-w-lg max-h-[85vh] bg-background border rounded-t-xl sm:rounded-xl shadow-xl flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <div>
                <p className="font-semibold">Exercise library</p>
                <p className="text-xs text-muted-foreground">Browse any muscle group</p>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setBrowseOpen(false)}>Close</Button>
            </div>
            <div className="p-3 border-b">
              <Input
                value={browseQuery}
                onChange={(e) => setBrowseQuery(e.target.value)}
                placeholder="Filter by name or muscle..."
                autoFocus
              />
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
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        addExerciseToList(lib);
                        setBrowseOpen(false);
                        toast.success(`${lib.name} added`);
                      }}
                    >
                      <Plus className="h-3.5 w-3.5 mr-1" /> Add
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

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
