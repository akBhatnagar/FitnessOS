"use client";

import { useState } from "react";
import {
  Activity,
  Check,
  ChevronDown,
  Clock,
  Flame,
  MapPin,
  Heart,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { apiClient } from "@/services/api";
import { toast } from "sonner";

const CARDIO_TYPES = [
  { value: "running", label: "Running", icon: "🏃" },
  { value: "cycling", label: "Cycling", icon: "🚴" },
  { value: "walking", label: "Walking", icon: "🚶" },
  { value: "elliptical", label: "Elliptical", icon: "⚡" },
  { value: "swimming", label: "Swimming", icon: "🏊" },
  { value: "jump_rope", label: "Jump Rope", icon: "🪢" },
  { value: "rowing", label: "Rowing", icon: "🚣" },
  { value: "stair_climber", label: "Stair Climber", icon: "🪜" },
  { value: "hiit", label: "HIIT", icon: "🔥" },
  { value: "yoga", label: "Yoga", icon: "🧘" },
  { value: "other", label: "Other", icon: "🏋️" },
];

const INTENSITIES = [
  { value: "low", label: "Low", color: "text-green-400" },
  { value: "moderate", label: "Moderate", color: "text-yellow-400" },
  { value: "high", label: "High", color: "text-red-400" },
];

interface CardioModalProps {
  sessionId?: string;
  logDate?: string;   // ISO date string for standalone logs
  onClose: () => void;
  onSaved?: () => void;
}

export function CardioModal({ sessionId, logDate, onClose, onSaved }: CardioModalProps) {
  const [performed, setPerformed] = useState<boolean | null>(null);
  const [cardioType, setCardioType] = useState("running");
  const [duration, setDuration] = useState("");
  const [calories, setCalories] = useState("");
  const [distance, setDistance] = useState("");
  const [heartRate, setHeartRate] = useState("");
  const [intensity, setIntensity] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [skipped, setSkipped] = useState(false);

  const handleSkip = () => {
    setSkipped(true);
    onClose();
    onSaved?.();
  };

  const handleSave = async () => {
    if (performed === null) return;
    setSaving(true);
    try {
      await apiClient.post("/api/v1/cardio", {
        session_id: sessionId || null,
        log_date: logDate || null,
        cardio_type: cardioType,
        performed,
        duration_minutes: duration ? parseInt(duration) : null,
        calories_burned: calories ? parseInt(calories) : null,
        distance_km: distance ? parseFloat(distance) : null,
        avg_heart_rate: heartRate ? parseInt(heartRate) : null,
        intensity: intensity || null,
        notes: notes || null,
      });
      toast.success(
        performed
          ? `Cardio logged — ${duration ? duration + " min" : ""} ${cardioType}`
          : "Noted — no cardio today"
      );
      onSaved?.();
      onClose();
    } catch {
      toast.error("Failed to save cardio log");
    } finally {
      setSaving(false);
    }
  };

  const selectedType = CARDIO_TYPES.find((t) => t.value === cardioType);

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 px-4 pb-4 sm:pb-0">
      <div className="w-full max-w-md rounded-2xl bg-card border shadow-xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10">
              <Activity className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h2 className="font-semibold text-base">Post-Workout Cardio</h2>
              <p className="text-xs text-muted-foreground">Did you do cardio today?</p>
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-5 max-h-[70vh] overflow-y-auto">
          {/* Performed toggle */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => setPerformed(true)}
              className={cn(
                "flex flex-col items-center gap-2 rounded-xl border-2 py-4 transition-all",
                performed === true
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border hover:border-primary/40"
              )}
            >
              <Check className="h-6 w-6" />
              <span className="text-sm font-medium">Yes, I did it</span>
            </button>
            <button
              onClick={() => setPerformed(false)}
              className={cn(
                "flex flex-col items-center gap-2 rounded-xl border-2 py-4 transition-all",
                performed === false
                  ? "border-muted-foreground bg-muted/40 text-muted-foreground"
                  : "border-border hover:border-muted-foreground/40"
              )}
            >
              <X className="h-6 w-6" />
              <span className="text-sm font-medium">Skipped today</span>
            </button>
          </div>

          {/* Cardio details — only if performed */}
          {performed === true && (
            <>
              {/* Cardio type selector */}
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">Type</p>
                <div className="grid grid-cols-3 gap-2">
                  {CARDIO_TYPES.map((type) => (
                    <button
                      key={type.value}
                      onClick={() => setCardioType(type.value)}
                      className={cn(
                        "flex flex-col items-center gap-1 rounded-lg border py-2 px-1 text-xs transition-all",
                        cardioType === type.value
                          ? "border-primary bg-primary/10 text-primary font-medium"
                          : "border-border hover:border-primary/40 text-muted-foreground"
                      )}
                    >
                      <span className="text-lg">{type.icon}</span>
                      <span>{type.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Intensity */}
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">
                  Intensity <span className="normal-case">(optional)</span>
                </p>
                <div className="flex gap-2">
                  {INTENSITIES.map((i) => (
                    <button
                      key={i.value}
                      onClick={() => setIntensity(intensity === i.value ? null : i.value)}
                      className={cn(
                        "flex-1 rounded-lg border py-2 text-sm font-medium transition-all",
                        intensity === i.value
                          ? `border-primary bg-primary/10 ${i.color}`
                          : "border-border hover:border-primary/30 text-muted-foreground"
                      )}
                    >
                      {i.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Stats row */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="flex items-center gap-1 text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wide">
                    <Clock className="h-3 w-3" /> Duration (min)
                  </label>
                  <Input
                    type="number"
                    min={1}
                    max={600}
                    placeholder="e.g. 30"
                    value={duration}
                    onChange={(e) => setDuration(e.target.value)}
                    className="h-9 text-sm"
                  />
                </div>
                <div>
                  <label className="flex items-center gap-1 text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wide">
                    <Flame className="h-3 w-3" /> Calories burned
                  </label>
                  <Input
                    type="number"
                    min={0}
                    placeholder="Apple Watch / machine"
                    value={calories}
                    onChange={(e) => setCalories(e.target.value)}
                    className="h-9 text-sm"
                  />
                </div>
                <div>
                  <label className="flex items-center gap-1 text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wide">
                    <MapPin className="h-3 w-3" /> Distance (km)
                  </label>
                  <Input
                    type="number"
                    step="0.1"
                    min={0}
                    placeholder="optional"
                    value={distance}
                    onChange={(e) => setDistance(e.target.value)}
                    className="h-9 text-sm"
                  />
                </div>
                <div>
                  <label className="flex items-center gap-1 text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wide">
                    <Heart className="h-3 w-3" /> Avg heart rate
                  </label>
                  <Input
                    type="number"
                    min={30}
                    max={250}
                    placeholder="bpm (optional)"
                    value={heartRate}
                    onChange={(e) => setHeartRate(e.target.value)}
                    className="h-9 text-sm"
                  />
                </div>
              </div>

              {/* Notes */}
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1.5 block uppercase tracking-wide">
                  Notes <span className="normal-case">(optional)</span>
                </label>
                <Input
                  placeholder="How did it feel? Treadmill, park, etc."
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
            </>
          )}

          {/* Skipped — quick note */}
          {performed === false && (
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1.5 block uppercase tracking-wide">
                Reason <span className="normal-case">(optional)</span>
              </label>
              <Input
                placeholder="e.g. Too tired, time constraints…"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="h-9 text-sm"
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex gap-3 px-5 py-4 border-t">
          <Button variant="ghost" size="sm" className="flex-1" onClick={handleSkip}>
            Skip for now
          </Button>
          <Button
            size="sm"
            className="flex-1"
            disabled={performed === null || saving}
            onClick={handleSave}
          >
            {saving ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    </div>
  );
}
