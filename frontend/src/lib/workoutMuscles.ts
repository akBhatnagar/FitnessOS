export interface LogMuscleOption {
  key: string;
  label: string;
  dbMuscles: string[];
}

/** User-facing muscle groups mapped to DB primary_muscle values. */
export const LOG_MUSCLE_OPTIONS: LogMuscleOption[] = [
  { key: "back", label: "Back", dbMuscles: ["lats", "mid_back", "lower_back"] },
  { key: "chest", label: "Chest", dbMuscles: ["chest"] },
  { key: "shoulders", label: "Shoulders", dbMuscles: ["front_deltoid", "side_deltoid", "rear_deltoid"] },
  { key: "biceps", label: "Biceps", dbMuscles: ["biceps", "brachialis"] },
  { key: "triceps", label: "Triceps", dbMuscles: ["triceps"] },
  { key: "legs", label: "Legs", dbMuscles: ["quads", "hamstrings", "glutes", "calves"] },
  { key: "core", label: "Core", dbMuscles: ["abs", "core"] },
];

export function getLogMuscleOption(key: string): LogMuscleOption | undefined {
  return LOG_MUSCLE_OPTIONS.find((m) => m.key === key);
}

export function buildComboLabel(m1: LogMuscleOption, m2: LogMuscleOption): string {
  return `${m1.label} + ${m2.label}`;
}

export function buildComboMuscles(m1: LogMuscleOption, m2: LogMuscleOption): string[] {
  return [...new Set([...m1.dbMuscles, ...m2.dbMuscles])];
}

export const MIXED_WORKOUT = {
  key: "mixed",
  label: "Mixed Workout",
  dbMuscles: LOG_MUSCLE_OPTIONS.flatMap((m) => m.dbMuscles),
};

export const COMBO_WORKOUT = {
  key: "combo",
  label: "Two Muscles",
};

export const REST_DAY_SESSION_NAME = "Rest Day";

export function isRestDaySession(sessionName: string): boolean {
  return sessionName === REST_DAY_SESSION_NAME;
}

const PPL_SESSION_NAMES = new Set(["Push Day", "Pull Day", "Legs Day"]);

/** Sessions created via Log by Muscle (not PPL plan quick-add). */
export function isMuscleStructuredSession(sessionName: string): boolean {
  if (isRestDaySession(sessionName)) return false;
  if (PPL_SESSION_NAMES.has(sessionName)) return false;
  if (sessionName === MIXED_WORKOUT.label) return true;
  if (sessionName.endsWith(" Workout")) return true;
  if (sessionName.includes(" + ")) return true;
  return false;
}

export function groupSetsByExercise(
  rows: Array<{
    exercise_id: string;
    exercise_name: string;
    set_number: number;
    actual_weight_kg?: number | null;
    actual_reps?: number | null;
  }>,
): Record<string, { exercise_id: string; exercise_name: string; set_number: number; actual_weight_kg?: number; actual_reps?: number }[]> {
  const grouped: Record<string, { exercise_id: string; exercise_name: string; set_number: number; actual_weight_kg?: number; actual_reps?: number }[]> = {};
  for (const row of rows) {
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
  return grouped;
}
