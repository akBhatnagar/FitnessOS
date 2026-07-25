export interface PlanSet {
  set_number: number;
  weight_kg: number;
  reps: number;
  actual_weight_kg?: number;
  actual_reps?: number;
}

export interface PlanAlternative {
  id: string;
  name: string;
  primary_muscle: string;
  is_compound: boolean;
  tips?: string;
  equipment?: string[];
  tags?: string[];
  weight_irrelevant?: boolean;
  load_display?: "bodyweight" | "per_hand" | "total" | string;
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

export interface PlanExercise {
  exercise_id: string;
  name: string;
  primary_muscle: string;
  is_compound: boolean;
  tips?: string;
  notes?: string;
  sets: PlanSet[];
  /** Prefetched swaps from generation — shown only when Alt is opened. */
  alternatives?: PlanAlternative[];
  weight_irrelevant?: boolean;
  load_display?: "bodyweight" | "per_hand" | "total" | string;
  load_label?: string;
  equipment?: string[];
}

export interface PlanSummary {
  exercises: number;
  sets: number;
}

export interface WorkoutPlanData {
  session_id?: string;
  session_name: string;
  exercises: PlanExercise[];
  summary: PlanSummary;
  personalization?: string[];
  goal?: string;
}

export function computeSummary(exercises: PlanExercise[]): PlanSummary {
  return {
    exercises: exercises.length,
    sets: exercises.reduce((n, ex) => n + ex.sets.length, 0),
  };
}

export function defaultSets(count = 3, weight = 20, reps = 10): PlanSet[] {
  return Array.from({ length: count }, (_, i) => ({
    set_number: i + 1,
    weight_kg: weight,
    reps,
  }));
}

export function renumberSets(sets: PlanSet[]): PlanSet[] {
  return sets.map((s, i) => ({ ...s, set_number: i + 1 }));
}

export function weightColumnLabel(ex: Pick<PlanExercise, "weight_irrelevant" | "load_display" | "load_label">): string {
  if (ex.weight_irrelevant || ex.load_display === "bodyweight") return "Load";
  if (ex.load_label) return ex.load_label;
  if (ex.load_display === "per_hand") return "kg each";
  return "Weight (kg)";
}
