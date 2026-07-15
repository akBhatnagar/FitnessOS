"use client";

import { useState, useEffect, useRef } from "react";
import { format } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  UtensilsCrossed, Plus, Search, X, ChevronDown,
  Flame, Beef, Wheat, Droplet, Loader2, CheckCircle2, Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/services/api";
import { toast } from "sonner";
import { DatePickerBar, todayStr } from "@/components/shared/DatePickerBar";

// ─── Types ─────────────────────────────────────────────────────────────────

interface Macros {
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
}

interface Targets extends Macros {
  fiber_g: number;
  water_ml: number;
}

interface MealItem {
  id: string;
  food_name: string;
  quantity_g: number;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
}

interface Meal {
  id: string;
  meal_type: string;
  name: string;
  meal_date: string;
  total_calories: number;
  total_protein_g: number;
  total_carbs_g: number;
  total_fat_g: number;
  items: MealItem[];
}

interface FoodResult {
  id: string;
  name: string;
  calories_per_100g: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  serving_size_g?: number;
  serving_description?: string;
  is_vegetarian: boolean;
  is_vegan: boolean;
  tags: string[];
}

interface DayData {
  totals: Macros;
  targets: Macros;
  remaining: Macros;
  scores: { protein_pct: number; calorie_pct: number };
  meals: Meal[];
  insight: string;
}

const MEAL_TYPES = [
  { key: "breakfast", label: "Breakfast", emoji: "🌅" },
  { key: "lunch", label: "Lunch", emoji: "☀️" },
  { key: "snack", label: "Snack", emoji: "🍎" },
  { key: "pre_workout", label: "Pre-Workout", emoji: "⚡" },
  { key: "dinner", label: "Dinner", emoji: "🌙" },
  { key: "post_workout", label: "Post-Workout", emoji: "💪" },
];

// ─── Macro Ring ─────────────────────────────────────────────────────────────

function MacroRing({
  value,
  target,
  label,
  color,
  unit = "g",
}: {
  value: number;
  target: number;
  label: string;
  color: string;
  unit?: string;
}) {
  const pct = Math.min(100, (value / target) * 100);
  const r = 28;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative h-16 w-16">
        <svg className="h-16 w-16 -rotate-90" viewBox="0 0 64 64">
          <circle cx="32" cy="32" r={r} fill="none" stroke="currentColor" strokeWidth="6" className="text-muted/20" />
          <circle
            cx="32" cy="32" r={r}
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeDasharray={`${dash} ${circ - dash}`}
            strokeLinecap="round"
            className="transition-all duration-700"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xs font-bold leading-none">{Math.round(value)}</span>
          <span className="text-[9px] text-muted-foreground">{unit}</span>
        </div>
      </div>
      <span className="text-[10px] text-muted-foreground font-medium">{label}</span>
      <span className="text-[10px] text-muted-foreground">{Math.round(target) - Math.round(value)}{unit} left</span>
    </div>
  );
}

// ─── Food Search ─────────────────────────────────────────────────────────────

function FoodSearchPanel({
  mealId,
  onAdded,
  onClose,
}: {
  mealId: string;
  onAdded: () => void;
  onClose: () => void;
}) {
  const [mode, setMode] = useState<"search" | "manual">("search");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FoodResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<FoodResult | null>(null);
  const [quantity, setQuantity] = useState("100");
  const [adding, setAdding] = useState(false);
  const [manual, setManual] = useState({
    name: "",
    quantity_g: "100",
    calories: "",
    protein_g: "",
    carbs_g: "",
    fat_g: "",
  });
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.focus(); }, [mode]);

  const search = async (q: string) => {
    setQuery(q);
    if (!q.trim()) {
      setResults([]);
      return;
    }
    setSearching(true);
    try {
      const res = await apiClient.get(`/api/v1/nutrition/foods?query=${encodeURIComponent(q)}&limit=8`);
      setResults(res.data);
    } catch {
      setResults([]);
    } finally {
      setSearching(false);
    }
  };

  const openManual = (name?: string) => {
    setMode("manual");
    setManual((prev) => ({
      ...prev,
      name: name ?? query.trim(),
    }));
    setSelected(null);
  };

  const addFood = async () => {
    if (!selected || !quantity) return;
    setAdding(true);
    try {
      const res = await apiClient.post(`/api/v1/nutrition/meals/${mealId}/items`, {
        food_id: selected.id,
        food_name: selected.name,
        quantity_g: parseFloat(quantity),
      });
      toast.success(`Added ${selected.name} — ${res.data.protein_g}g protein`);
      onAdded();
      setSelected(null);
      setQuery("");
      setResults([]);
      setQuantity("100");
    } catch {
      toast.error("Failed to add food.");
    } finally {
      setAdding(false);
    }
  };

  const addManualFood = async () => {
    const name = manual.name.trim();
    const qty = parseFloat(manual.quantity_g);
    const calories = parseFloat(manual.calories);
    const protein = parseFloat(manual.protein_g);
    const carbs = parseFloat(manual.carbs_g || "0");
    const fat = parseFloat(manual.fat_g || "0");

    if (!name || !qty || qty <= 0) {
      toast.error("Enter a food name and quantity.");
      return;
    }
    if (Number.isNaN(calories) || Number.isNaN(protein)) {
      toast.error("Calories and protein are required for custom foods.");
      return;
    }

    setAdding(true);
    try {
      const res = await apiClient.post(`/api/v1/nutrition/meals/${mealId}/items`, {
        food_name: name,
        quantity_g: qty,
        calories_override: calories,
        protein_override: protein,
        carbs_override: carbs,
        fat_override: fat,
      });
      toast.success(`Added ${name} — ${res.data.protein_g}g protein`);
      onAdded();
      setMode("search");
      setManual({ name: "", quantity_g: "100", calories: "", protein_g: "", carbs_g: "", fat_g: "" });
      setQuery("");
      setResults([]);
    } catch {
      toast.error("Failed to add custom food.");
    } finally {
      setAdding(false);
    }
  };

  const qtyNum = parseFloat(quantity) || 100;
  const preview = selected ? {
    calories: Math.round(selected.calories_per_100g * qtyNum / 100),
    protein: Math.round(selected.protein_g * qtyNum / 100 * 10) / 10,
    carbs: Math.round(selected.carbs_g * qtyNum / 100 * 10) / 10,
    fat: Math.round(selected.fat_g * qtyNum / 100 * 10) / 10,
  } : null;

  return (
    <div className="rounded-xl border bg-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">
          {mode === "manual" ? "Add Custom Food" : "Add Food"}
        </span>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      {mode === "manual" ? (
        <div className="space-y-3">
          <div>
            <label className="text-xs text-muted-foreground">Food name</label>
            <Input
              value={manual.name}
              onChange={(e) => setManual({ ...manual, name: e.target.value })}
              placeholder="e.g. restaurant biryani, homemade paratha"
              className="mt-1"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Quantity (grams)</label>
            <Input
              type="number"
              value={manual.quantity_g}
              onChange={(e) => setManual({ ...manual, quantity_g: e.target.value })}
              className="mt-1"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-muted-foreground">Calories *</label>
              <Input
                type="number"
                value={manual.calories}
                onChange={(e) => setManual({ ...manual, calories: e.target.value })}
                placeholder="kcal"
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Protein (g) *</label>
              <Input
                type="number"
                value={manual.protein_g}
                onChange={(e) => setManual({ ...manual, protein_g: e.target.value })}
                placeholder="g"
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Carbs (g)</label>
              <Input
                type="number"
                value={manual.carbs_g}
                onChange={(e) => setManual({ ...manual, carbs_g: e.target.value })}
                placeholder="optional"
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground">Fat (g)</label>
              <Input
                type="number"
                value={manual.fat_g}
                onChange={(e) => setManual({ ...manual, fat_g: e.target.value })}
                placeholder="optional"
                className="mt-1"
              />
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Use the label, MyFitnessPal, or a rough estimate. Calories and protein are required.
          </p>
          <div className="flex gap-2">
            <Button onClick={addManualFood} disabled={adding} className="flex-1">
              {adding ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
              Add to Meal
            </Button>
            <Button variant="outline" onClick={() => setMode("search")}>
              Back
            </Button>
          </div>
        </div>
      ) : !selected ? (
        <>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              ref={inputRef}
              value={query}
              onChange={(e) => search(e.target.value)}
              placeholder="Search food (paneer, dal, oats...)"
              className="pl-9"
            />
          </div>
          {searching && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Searching...
            </div>
          )}
          {!searching && results.length > 0 && (
            <div className="space-y-1 max-h-60 overflow-y-auto">
              {results.map((f) => (
                <button
                  key={f.id}
                  onClick={() => {
                    setSelected(f);
                    if (f.serving_size_g) setQuantity(f.serving_size_g.toString());
                  }}
                  className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm hover:bg-muted/50 text-left"
                >
                  <div>
                    <span className="font-medium">{f.name}</span>
                    <div className="flex gap-2 text-[10px] text-muted-foreground mt-0.5">
                      {f.tags.slice(0, 2).map((t) => <span key={t}>{t}</span>)}
                    </div>
                  </div>
                  <div className="text-right text-[11px] text-muted-foreground">
                    <div className="font-bold text-foreground">{f.protein_g}g protein</div>
                    <div>{Math.round(f.calories_per_100g)} kcal / 100g</div>
                  </div>
                </button>
              ))}
            </div>
          )}
          {!searching && query.trim().length >= 2 && results.length === 0 && (
            <div className="rounded-lg border border-dashed px-3 py-3 text-center space-y-2">
              <p className="text-sm text-muted-foreground">
                No matches for &ldquo;{query.trim()}&rdquo;
              </p>
              <Button variant="outline" size="sm" onClick={() => openManual(query.trim())}>
                Add &ldquo;{query.trim()}&rdquo; manually
              </Button>
            </div>
          )}
          <button
            type="button"
            onClick={() => openManual()}
            className="w-full text-xs text-muted-foreground hover:text-foreground underline-offset-2 hover:underline"
          >
            Food not in the list? Add custom entry
          </button>
        </>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-sm">{selected.name}</span>
            <button onClick={() => setSelected(null)} className="text-xs text-muted-foreground hover:text-foreground">
              Change
            </button>
          </div>

          <div>
            <label className="text-xs text-muted-foreground">Quantity (grams)</label>
            <div className="flex gap-2 mt-1">
              <Input
                type="number"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                className="font-mono text-lg font-bold"
              />
              {selected.serving_size_g && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setQuantity(selected.serving_size_g!.toString())}
                  className="whitespace-nowrap text-xs"
                >
                  1 serving ({selected.serving_size_g}g)
                </Button>
              )}
            </div>
          </div>

          {preview && (
            <div className="grid grid-cols-4 gap-2 rounded-lg bg-muted/30 p-3">
              <div className="text-center">
                <div className="text-sm font-bold">{preview.calories}</div>
                <div className="text-[9px] text-muted-foreground">kcal</div>
              </div>
              <div className="text-center">
                <div className="text-sm font-bold text-red-400">{preview.protein}g</div>
                <div className="text-[9px] text-muted-foreground">protein</div>
              </div>
              <div className="text-center">
                <div className="text-sm font-bold text-yellow-400">{preview.carbs}g</div>
                <div className="text-[9px] text-muted-foreground">carbs</div>
              </div>
              <div className="text-center">
                <div className="text-sm font-bold text-blue-400">{preview.fat}g</div>
                <div className="text-[9px] text-muted-foreground">fat</div>
              </div>
            </div>
          )}

          <Button onClick={addFood} disabled={adding} className="w-full">
            {adding ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
            Add to Meal
          </Button>
        </div>
      )}
    </div>
  );
}

// ─── Meal Card ────────────────────────────────────────────────────────────────

function MealCard({
  meal,
  onUpdate,
  autoOpenSearch = false,
  onSearchClose,
}: {
  meal: Meal;
  onUpdate: () => void;
  autoOpenSearch?: boolean;
  onSearchClose?: () => void;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (autoOpenSearch) {
      setExpanded(true);
      setShowSearch(true);
      cardRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [autoOpenSearch, meal.id]);

  const closeSearch = () => {
    setShowSearch(false);
    onSearchClose?.();
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await apiClient.delete(`/api/v1/nutrition/meals/${meal.id}`);
      toast.success("Meal deleted");
      onUpdate();
    } catch {
      toast.error("Failed to delete meal.");
    } finally {
      setDeleting(false);
    }
  };

  const mealMeta = MEAL_TYPES.find((m) => m.key === meal.meal_type);

  return (
    <Card ref={cardRef}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-3 flex-1 text-left"
          >
            <span className="text-xl">{mealMeta?.emoji ?? "🍽"}</span>
            <div>
              <div className="font-semibold">{meal.name || mealMeta?.label}</div>
              <div className="text-xs text-muted-foreground">
                {meal.items.length} items · {Math.round(meal.total_calories)} kcal
              </div>
            </div>
            <div className="ml-auto flex items-center gap-3">
              <Badge variant="secondary" className="font-mono text-xs">
                {Math.round(meal.total_protein_g)}g P
              </Badge>
              <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", expanded && "rotate-180")} />
            </div>
          </button>
        </div>

        {expanded && (
          <div className="mt-3 space-y-2">
            {meal.items.map((item) => (
              <div key={item.id} className="flex items-center justify-between text-sm rounded-lg bg-muted/20 px-3 py-2">
                <span>{item.food_name}</span>
                <div className="flex items-center gap-3 text-muted-foreground text-xs">
                  <span>{item.quantity_g}g</span>
                  <span className="font-medium text-red-400">{item.protein_g}g P</span>
                  <span>{Math.round(item.calories)} kcal</span>
                </div>
              </div>
            ))}

            {showSearch ? (
              <FoodSearchPanel
                mealId={meal.id}
                onAdded={() => { onUpdate(); closeSearch(); }}
                onClose={closeSearch}
              />
            ) : (
              <div className="flex gap-2 pt-1">
                <Button variant="outline" size="sm" className="flex-1" onClick={() => setShowSearch(true)}>
                  <Plus className="h-3.5 w-3.5 mr-1" /> Add Food
                </Button>
                <Button variant="ghost" size="sm" onClick={handleDelete} disabled={deleting} className="text-destructive hover:text-destructive">
                  {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                </Button>
              </div>
            )}

            <div className="grid grid-cols-4 gap-1 pt-2 border-t">
              <div className="text-center text-xs">
                <div className="font-bold">{Math.round(meal.total_calories)}</div>
                <div className="text-muted-foreground">kcal</div>
              </div>
              <div className="text-center text-xs">
                <div className="font-bold text-red-400">{Math.round(meal.total_protein_g)}g</div>
                <div className="text-muted-foreground">protein</div>
              </div>
              <div className="text-center text-xs">
                <div className="font-bold text-yellow-400">{Math.round(meal.total_carbs_g)}g</div>
                <div className="text-muted-foreground">carbs</div>
              </div>
              <div className="text-center text-xs">
                <div className="font-bold text-blue-400">{Math.round(meal.total_fat_g)}g</div>
                <div className="text-muted-foreground">fat</div>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Main Page ──────────────────────────────────────────────────────────────

export default function NutritionPage() {
  const [selectedDate, setSelectedDate] = useState(todayStr);
  const [data, setData] = useState<DayData | null>(null);
  const [loading, setLoading] = useState(true);
  const [addingMeal, setAddingMeal] = useState<string | null>(null);
  const [creatingMeal, setCreatingMeal] = useState(false);
  const [searchMealId, setSearchMealId] = useState<string | null>(null);

  const isToday = selectedDate === todayStr();

  const loadData = async (date = selectedDate) => {
    try {
      const res = await apiClient.get("/api/v1/nutrition/today", { params: { date } });
      setData(res.data);
    } catch {
      toast.error("Failed to load nutrition data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    setSearchMealId(null);
    loadData(selectedDate);
  }, [selectedDate]);

  const createMeal = async (mealType: string) => {
    const existing = data?.meals.find((m) => m.meal_type === mealType);
    if (existing) {
      setSearchMealId(existing.id);
      return;
    }

    setCreatingMeal(true);
    setAddingMeal(mealType);
    try {
      const res = await apiClient.post("/api/v1/nutrition/meals", {
        meal_type: mealType,
        meal_date: selectedDate,
      });
      await loadData();
      setSearchMealId(res.data.id);
    } catch {
      toast.error("Failed to create meal.");
    } finally {
      setCreatingMeal(false);
      setAddingMeal(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const { totals, targets, remaining, scores, meals, insight } = data ?? {
    totals: { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 },
    targets: { calories: 2200, protein_g: 160, carbs_g: 220, fat_g: 70 },
    remaining: { calories: 2200, protein_g: 160, carbs_g: 220, fat_g: 70 },
    scores: { protein_pct: 0, calorie_pct: 0 },
    meals: [],
    insight: "",
  };


  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <h1 className="text-2xl font-bold">Nutrition</h1>
          {!isToday && (
            <Badge variant="secondary" className="text-xs">Past date</Badge>
          )}
        </div>
        <DatePickerBar value={selectedDate} onChange={setSelectedDate} />
      </div>

      {/* Macro Rings */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-center justify-around">
            <MacroRing value={totals.calories} target={targets.calories} label="Calories" color="#f97316" unit="kcal" />
            <MacroRing value={totals.protein_g} target={targets.protein_g} label="Protein" color="#ef4444" />
            <MacroRing value={totals.carbs_g} target={targets.carbs_g} label="Carbs" color="#eab308" />
            <MacroRing value={totals.fat_g} target={targets.fat_g} label="Fat" color="#3b82f6" />
          </div>

          {/* Insight */}
          {insight && (
            <div className="mt-4 rounded-lg bg-primary/5 border border-primary/20 px-3 py-2 text-sm text-muted-foreground">
              💡 {insight}
            </div>
          )}

          {/* Summary row */}
          <div className="grid grid-cols-4 gap-2 mt-4 pt-4 border-t text-center text-xs">
            <div>
              <div className="font-bold text-orange-400">{Math.round(remaining.calories)}</div>
              <div className="text-muted-foreground">kcal left</div>
            </div>
            <div>
              <div className="font-bold text-red-400">{Math.round(remaining.protein_g)}g</div>
              <div className="text-muted-foreground">protein left</div>
            </div>
            <div>
              <div className="font-bold text-yellow-400">{Math.round(remaining.carbs_g)}g</div>
              <div className="text-muted-foreground">carbs left</div>
            </div>
            <div>
              <div className="font-bold text-blue-400">{Math.round(remaining.fat_g)}g</div>
              <div className="text-muted-foreground">fat left</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Logged Meals */}
      {meals.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
            {isToday ? "Today's Meals" : "Meals"}
          </h2>
          {meals.map((meal) => (
            <MealCard
              key={meal.id}
              meal={meal}
              onUpdate={loadData}
              autoOpenSearch={searchMealId === meal.id}
              onSearchClose={() => setSearchMealId(null)}
            />
          ))}
        </div>
      )}

      {/* Add Meal Buttons */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
          {meals.length > 0 ? "Add another meal" : "Log a meal"}
        </h2>
        <div className="grid grid-cols-3 gap-2">
          {MEAL_TYPES.map((mt) => {
            const existingMeal = meals.find((m) => m.meal_type === mt.key);
            const alreadyLogged = Boolean(existingMeal);
            return (
              <button
                key={mt.key}
                onClick={() => createMeal(mt.key)}
                disabled={creatingMeal && addingMeal === mt.key}
                className={cn(
                  "flex flex-col items-center gap-1 rounded-xl border px-3 py-3 text-sm font-medium transition-all",
                  alreadyLogged
                    ? "border-green-500/30 bg-green-500/5 text-green-400 hover:border-primary/50"
                    : "border-border hover:border-primary/50 hover:bg-muted/30"
                )}
              >
                {creatingMeal && addingMeal === mt.key ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : alreadyLogged ? (
                  <CheckCircle2 className="h-4 w-4 text-green-400" />
                ) : (
                  <span className="text-base">{mt.emoji}</span>
                )}
                <span className="text-xs">{mt.label}</span>
                {alreadyLogged && (
                  <span className="text-[10px] text-muted-foreground">+ add food</span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
