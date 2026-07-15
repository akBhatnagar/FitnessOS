"use client";

import { format, addDays, parseISO, isValid } from "date-fns";
import { ChevronLeft, ChevronRight, CalendarDays } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function todayStr() {
  return format(new Date(), "yyyy-MM-dd");
}

interface DatePickerBarProps {
  value: string;
  onChange: (date: string) => void;
  className?: string;
}

export function DatePickerBar({ value, onChange, className }: DatePickerBarProps) {
  const today = todayStr();
  const isToday = value === today;
  const parsed = parseISO(value);
  const label = isValid(parsed) ? format(parsed, "EEEE, MMMM d, yyyy") : value;

  const shift = (days: number) => {
    const base = isValid(parsed) ? parsed : new Date();
    const next = addDays(base, days);
    const nextStr = format(next, "yyyy-MM-dd");
    if (nextStr > today) return;
    onChange(nextStr);
  };

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <div className="flex items-center gap-1">
        <Button type="button" variant="outline" size="icon" className="h-8 w-8" onClick={() => shift(-1)}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button type="button" variant="outline" size="icon" className="h-8 w-8" onClick={() => shift(1)} disabled={isToday}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
      <label className="relative flex items-center gap-2 rounded-lg border bg-background px-3 py-1.5 text-sm cursor-pointer hover:bg-muted/30">
        <CalendarDays className="h-4 w-4 text-muted-foreground shrink-0" />
        <input
          type="date"
          value={value}
          max={today}
          onChange={(e) => {
            if (e.target.value && e.target.value <= today) onChange(e.target.value);
          }}
          className="bg-transparent border-0 p-0 text-sm focus:outline-none focus:ring-0 cursor-pointer"
        />
      </label>
      {!isToday && (
        <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" onClick={() => onChange(today)}>
          Today
        </Button>
      )}
      <p className="w-full text-xs text-muted-foreground sm:w-auto sm:ml-1">{label}</p>
    </div>
  );
}

export { todayStr };
