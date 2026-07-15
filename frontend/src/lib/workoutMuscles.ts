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
