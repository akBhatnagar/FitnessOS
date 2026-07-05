"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import {
  CheckCircle2,
  Dumbbell,
  Waves,
  UtensilsCrossed,
  Moon,
  Scale,
  Heart,
  Brain,
  Camera,
  ChevronRight,
  ChevronLeft,
  Zap,
  TrendingUp,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/services/api";
import { toast } from "sonner";

// ─── Types ─────────────────────────────────────────────────────────────────

interface ReviewData {
  // Body
  weight_kg: number | null;
  waist_cm: number | null;
  // Adherence (0-7 days)
  gym_days: number;
  swim_days: number;
  diet_days: number;
  sleep_quality: 1 | 2 | 3 | 4 | 5;
  // Subjective
  energy_level: 1 | 2 | 3 | 4 | 5;
  stress_level: 1 | 2 | 3 | 4 | 5;
  pain_areas: string[];
  // Freeform
  wins: string;
  struggles: string;
  notes: string;
  // Photo
  photo_taken: boolean;
}

const INITIAL_DATA: ReviewData = {
  weight_kg: null,
  waist_cm: null,
  gym_days: 0,
  swim_days: 0,
  diet_days: 0,
  sleep_quality: 3,
  energy_level: 3,
  stress_level: 3,
  pain_areas: [],
  wins: "",
  struggles: "",
  notes: "",
  photo_taken: false,
};

const TOTAL_STEPS = 5;

// ─── Slider Component ───────────────────────────────────────────────────────

function ScaleButtons({
  value,
  onChange,
  labels,
}: {
  value: number;
  onChange: (v: number) => void;
  labels: [string, string, string, string, string];
}) {
  return (
    <div className="flex gap-2">
      {[1, 2, 3, 4, 5].map((v) => (
        <button
          key={v}
          onClick={() => onChange(v as 1 | 2 | 3 | 4 | 5)}
          className={cn(
            "flex-1 rounded-lg border-2 py-3 text-sm font-semibold transition-all",
            value === v
              ? "border-primary bg-primary text-primary-foreground"
              : "border-border bg-card text-muted-foreground hover:border-primary/50"
          )}
        >
          {v}
        </button>
      ))}
    </div>
  );
}

function DayButtons({
  value,
  onChange,
  max = 7,
}: {
  value: number;
  onChange: (v: number) => void;
  max?: number;
}) {
  return (
    <div className="flex gap-1.5 flex-wrap">
      {Array.from({ length: max + 1 }, (_, i) => i).map((d) => (
        <button
          key={d}
          onClick={() => onChange(d)}
          className={cn(
            "h-10 w-10 rounded-lg border-2 text-sm font-bold transition-all",
            value === d
              ? "border-primary bg-primary text-primary-foreground"
              : value > d
              ? "border-primary/30 bg-primary/10 text-primary"
              : "border-border bg-card text-muted-foreground hover:border-primary/50"
          )}
        >
          {d}
        </button>
      ))}
    </div>
  );
}

// ─── Steps ─────────────────────────────────────────────────────────────────

function Step1Body({
  data,
  onChange,
}: {
  data: ReviewData;
  onChange: (key: keyof ReviewData, value: any) => void;
}) {
  return (
    <div className="space-y-6">
      <div>
        <label className="text-sm font-medium text-muted-foreground">Weight this week (kg)</label>
        <div className="mt-2 flex items-center gap-3">
          <Scale className="h-5 w-5 text-primary" />
          <input
            type="number"
            step="0.1"
            value={data.weight_kg ?? ""}
            onChange={(e) => onChange("weight_kg", e.target.value ? parseFloat(e.target.value) : null)}
            placeholder="e.g. 99.2"
            className="flex h-12 w-full rounded-lg border border-input bg-background px-4 text-lg font-semibold focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <span className="text-muted-foreground">kg</span>
        </div>
        {data.weight_kg && (
          <p className="mt-1 text-xs text-muted-foreground">
            {data.weight_kg < 100 ? `🎉 Under 100kg!` : `${(data.weight_kg - 85).toFixed(1)}kg to go`}
          </p>
        )}
      </div>

      <div>
        <label className="text-sm font-medium text-muted-foreground">Waist measurement (optional)</label>
        <div className="mt-2 flex items-center gap-3">
          <input
            type="number"
            step="0.5"
            value={data.waist_cm ?? ""}
            onChange={(e) => onChange("waist_cm", e.target.value ? parseFloat(e.target.value) : null)}
            placeholder="e.g. 87"
            className="flex h-12 w-full rounded-lg border border-input bg-background px-4 text-lg font-semibold focus:outline-none focus:ring-2 focus:ring-primary"
          />
          <span className="text-muted-foreground">cm</span>
        </div>
      </div>

      <div className="rounded-lg border bg-primary/5 p-4">
        <div className="flex items-center gap-2 mb-2">
          <Camera className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">Progress Photo</span>
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          Weekly photos are the best way to see changes the scale doesn't show.
          Front + side + back in good lighting.
        </p>
        <button
          onClick={() => onChange("photo_taken", !data.photo_taken)}
          className={cn(
            "w-full rounded-lg border-2 py-2 text-sm font-medium transition-all",
            data.photo_taken
              ? "border-green-500 bg-green-500/10 text-green-400"
              : "border-dashed border-border text-muted-foreground hover:border-primary/50"
          )}
        >
          {data.photo_taken ? "✓ Photos taken this week" : "Mark as done (photos taken)"}
        </button>
      </div>
    </div>
  );
}

function Step2Adherence({
  data,
  onChange,
}: {
  data: ReviewData;
  onChange: (key: keyof ReviewData, value: any) => void;
}) {
  return (
    <div className="space-y-8">
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Dumbbell className="h-4 w-4 text-primary" />
          <label className="font-medium">Gym sessions completed this week</label>
          <Badge variant={data.gym_days >= 4 ? "success" : data.gym_days >= 2 ? "warning" : "destructive"}>
            {data.gym_days}/7 days
          </Badge>
        </div>
        <DayButtons value={data.gym_days} onChange={(v) => onChange("gym_days", v)} />
        <p className="mt-2 text-xs text-muted-foreground">
          Target: 5 days/week (Mon-Fri evenings at 9 PM)
        </p>
      </div>

      <div>
        <div className="flex items-center gap-2 mb-3">
          <Waves className="h-4 w-4 text-blue-400" />
          <label className="font-medium">Swimming sessions this week</label>
          <Badge variant={data.swim_days >= 3 ? "success" : data.swim_days >= 1 ? "warning" : "outline"}>
            {data.swim_days}/7 days
          </Badge>
        </div>
        <DayButtons value={data.swim_days} onChange={(v) => onChange("swim_days", v)} />
        <p className="mt-2 text-xs text-muted-foreground">
          Target: 3-4 days/week (morning sessions at 8 AM)
        </p>
      </div>

      <div>
        <div className="flex items-center gap-2 mb-3">
          <UtensilsCrossed className="h-4 w-4 text-green-400" />
          <label className="font-medium">Diet on-plan days</label>
          <Badge variant={data.diet_days >= 5 ? "success" : data.diet_days >= 3 ? "warning" : "destructive"}>
            {data.diet_days}/7 days
          </Badge>
        </div>
        <DayButtons value={data.diet_days} onChange={(v) => onChange("diet_days", v)} />
        <p className="mt-2 text-xs text-muted-foreground">
          On-plan = hit protein target (160g+) and stayed in caloric deficit
        </p>
      </div>
    </div>
  );
}

function Step3Wellbeing({
  data,
  onChange,
}: {
  data: ReviewData;
  onChange: (key: keyof ReviewData, value: any) => void;
}) {
  const PAIN_OPTIONS = [
    "Lower back", "Knees", "Shoulders", "Elbows", "Wrists",
    "Hips", "Ankles", "Neck", "None this week",
  ];

  return (
    <div className="space-y-8">
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Moon className="h-4 w-4 text-purple-400" />
          <label className="font-medium">Sleep quality this week</label>
        </div>
        <ScaleButtons
          value={data.sleep_quality}
          onChange={(v) => onChange("sleep_quality", v)}
          labels={["Terrible", "Poor", "Average", "Good", "Excellent"]}
        />
        <div className="flex justify-between mt-1 text-[10px] text-muted-foreground px-1">
          <span>Terrible</span><span>Poor</span><span>Average</span><span>Good</span><span>Excellent</span>
        </div>
      </div>

      <div>
        <div className="flex items-center gap-2 mb-3">
          <Zap className="h-4 w-4 text-yellow-400" />
          <label className="font-medium">Energy levels this week</label>
        </div>
        <ScaleButtons
          value={data.energy_level}
          onChange={(v) => onChange("energy_level", v)}
          labels={["Drained", "Low", "Moderate", "High", "Peak"]}
        />
        <div className="flex justify-between mt-1 text-[10px] text-muted-foreground px-1">
          <span>Drained</span><span>Low</span><span>Moderate</span><span>High</span><span>Peak</span>
        </div>
      </div>

      <div>
        <div className="flex items-center gap-2 mb-3">
          <Brain className="h-4 w-4 text-red-400" />
          <label className="font-medium">Stress level this week</label>
        </div>
        <ScaleButtons
          value={data.stress_level}
          onChange={(v) => onChange("stress_level", v)}
          labels={["None", "Mild", "Moderate", "High", "Overwhelmed"]}
        />
        <div className="flex justify-between mt-1 text-[10px] text-muted-foreground px-1">
          <span>None</span><span>Mild</span><span>Moderate</span><span>High</span><span>Max</span>
        </div>
      </div>

      <div>
        <div className="flex items-center gap-2 mb-3">
          <Heart className="h-4 w-4 text-red-400" />
          <label className="font-medium">Any pain or discomfort?</label>
        </div>
        <div className="flex flex-wrap gap-2">
          {PAIN_OPTIONS.map((area) => (
            <button
              key={area}
              onClick={() => {
                const current = data.pain_areas;
                if (area === "None this week") {
                  onChange("pain_areas", []);
                } else {
                  onChange(
                    "pain_areas",
                    current.includes(area)
                      ? current.filter((a) => a !== area)
                      : [...current.filter((a) => a !== "None this week"), area]
                  );
                }
              }}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium transition-all",
                data.pain_areas.includes(area) || (area === "None this week" && data.pain_areas.length === 0)
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/50"
              )}
            >
              {area}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function Step4Reflection({
  data,
  onChange,
}: {
  data: ReviewData;
  onChange: (key: keyof ReviewData, value: any) => void;
}) {
  return (
    <div className="space-y-6">
      <div>
        <label className="font-medium text-green-400 flex items-center gap-2 mb-2">
          <TrendingUp className="h-4 w-4" /> Wins this week
        </label>
        <Textarea
          value={data.wins}
          onChange={(e) => onChange("wins", e.target.value)}
          placeholder="What went well? Any PRs, habits kept, good meals? Even small wins count..."
          className="min-h-[100px] resize-none"
        />
      </div>

      <div>
        <label className="font-medium text-red-400 flex items-center gap-2 mb-2">
          <AlertCircle className="h-4 w-4" /> Struggles or missed targets
        </label>
        <Textarea
          value={data.struggles}
          onChange={(e) => onChange("struggles", e.target.value)}
          placeholder="What was hard? Missed sessions, bad meals, poor sleep? No judgment — just data for the AI to improve your plan..."
          className="min-h-[100px] resize-none"
        />
      </div>

      <div>
        <label className="font-medium text-muted-foreground flex items-center gap-2 mb-2">
          📝 Anything else for your AI coach?
        </label>
        <Textarea
          value={data.notes}
          onChange={(e) => onChange("notes", e.target.value)}
          placeholder="Schedule changes next week? Travel? Events? New injuries? Anything you want the AI to factor into next week's plan..."
          className="min-h-[80px] resize-none"
        />
      </div>
    </div>
  );
}

function Step5Summary({ data }: { data: ReviewData }) {
  const adherenceScore = Math.round(
    ((data.gym_days / 5 + data.swim_days / 4 + data.diet_days / 7) / 3) * 100
  );

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">
        Review everything before your AI coach generates next week's plan.
      </p>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border p-3">
          <p className="text-xs text-muted-foreground">Weight</p>
          <p className="text-2xl font-bold">{data.weight_kg ?? "—"} kg</p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-xs text-muted-foreground">Adherence Score</p>
          <p className={cn("text-2xl font-bold", adherenceScore >= 70 ? "text-green-400" : "text-yellow-400")}>
            {adherenceScore}%
          </p>
        </div>
      </div>

      <div className="rounded-lg border p-4 space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">🏋️ Gym</span>
          <span className="font-medium">{data.gym_days}/7 days</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">🏊 Swimming</span>
          <span className="font-medium">{data.swim_days}/7 days</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">🥗 Diet</span>
          <span className="font-medium">{data.diet_days}/7 days</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">😴 Sleep</span>
          <span className="font-medium">{data.sleep_quality}/5</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">⚡ Energy</span>
          <span className="font-medium">{data.energy_level}/5</span>
        </div>
        {data.pain_areas.length > 0 && (
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">💊 Pain</span>
            <span className="font-medium text-yellow-400">{data.pain_areas.join(", ")}</span>
          </div>
        )}
      </div>

      {data.wins && (
        <div className="rounded-lg border border-green-500/20 bg-green-500/5 p-3">
          <p className="text-xs text-green-400 font-medium mb-1">Your wins</p>
          <p className="text-sm text-muted-foreground">{data.wins}</p>
        </div>
      )}

      <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 text-sm text-muted-foreground">
        <p className="font-medium text-primary mb-1">What happens next</p>
        <p>Your AI coach will analyze this data, generate insights, and rebuild your plan for next week. The new plan will appear in your dashboard within 30 seconds.</p>
      </div>
    </div>
  );
}

// ─── Main Page ──────────────────────────────────────────────────────────────

const STEP_LABELS = ["Body", "Training", "Wellbeing", "Reflection", "Submit"];
const STEP_DESCRIPTIONS = [
  "Weight & measurements",
  "Gym, swim & diet adherence",
  "Sleep, energy & pain",
  "Wins & struggles",
  "Review & generate plan",
];

export default function WeeklyReviewPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [data, setData] = useState<ReviewData>(INITIAL_DATA);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleChange = (key: keyof ReviewData, value: any) => {
    setData((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await apiClient.post("/api/v1/reviews/weekly", {
        ...data,
        week_of: format(new Date(), "yyyy-MM-dd"),
      });
      setSubmitted(true);
      toast.success("Weekly review submitted! Generating your new plan...");
      setTimeout(() => router.push("/dashboard"), 3000);
    } catch (err) {
      toast.error("Failed to submit review. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center space-y-4">
        <div className="h-16 w-16 rounded-full bg-green-500/20 flex items-center justify-center">
          <CheckCircle2 className="h-8 w-8 text-green-400" />
        </div>
        <h2 className="text-2xl font-bold">Review submitted!</h2>
        <p className="text-muted-foreground max-w-sm">
          Your AI coach is analyzing your week and rebuilding your plan. Redirecting to dashboard...
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-1">
          <Badge variant="secondary">Weekly Review</Badge>
          <span className="text-xs text-muted-foreground">{format(new Date(), "EEEE, MMMM d")}</span>
        </div>
        <h1 className="text-2xl font-bold">Sunday Check-in</h1>
        <p className="text-muted-foreground text-sm mt-1">
          5 minutes every Sunday → better plan every Monday.
        </p>
      </div>

      {/* Progress */}
      <div className="flex items-center gap-1 mb-8">
        {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
          <div
            key={i}
            className={cn(
              "h-1.5 flex-1 rounded-full transition-all",
              i + 1 < step ? "bg-primary" : i + 1 === step ? "bg-primary/60" : "bg-border"
            )}
          />
        ))}
      </div>

      {/* Step card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg">{STEP_LABELS[step - 1]}</CardTitle>
              <CardDescription>{STEP_DESCRIPTIONS[step - 1]}</CardDescription>
            </div>
            <span className="text-xs text-muted-foreground font-medium">
              {step} / {TOTAL_STEPS}
            </span>
          </div>
        </CardHeader>
        <CardContent>
          {step === 1 && <Step1Body data={data} onChange={handleChange} />}
          {step === 2 && <Step2Adherence data={data} onChange={handleChange} />}
          {step === 3 && <Step3Wellbeing data={data} onChange={handleChange} />}
          {step === 4 && <Step4Reflection data={data} onChange={handleChange} />}
          {step === 5 && <Step5Summary data={data} />}
        </CardContent>
      </Card>

      {/* Navigation */}
      <div className="flex items-center justify-between mt-6">
        <Button
          variant="ghost"
          onClick={() => setStep((s) => Math.max(1, s - 1))}
          disabled={step === 1}
        >
          <ChevronLeft className="h-4 w-4 mr-1" /> Back
        </Button>

        {step < TOTAL_STEPS ? (
          <Button onClick={() => setStep((s) => s + 1)}>
            Continue <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        ) : (
          <Button onClick={handleSubmit} disabled={submitting} className="min-w-[160px]">
            {submitting ? (
              <>
                <span className="animate-spin mr-2">⟳</span>
                Generating plan...
              </>
            ) : (
              <>
                <Zap className="h-4 w-4 mr-2" />
                Submit & Generate Plan
              </>
            )}
          </Button>
        )}
      </div>
    </div>
  );
}
