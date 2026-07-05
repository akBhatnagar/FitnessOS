"use client";

import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { CheckCircle2, Circle, Clock, Dumbbell, Waves } from "lucide-react";
import { apiClient } from "@/services/api";
import { cn } from "@/lib/utils";

const DEFAULT_SCHEDULE = [
  { time: "8:00 AM", activity: "Morning Swim", icon: Waves, status: "pending", type: "swim" },
  { time: "10:30 AM", activity: "Office Work", icon: Clock, status: "pending", type: "work" },
  { time: "1:00 PM", activity: "Lunch Break", icon: Clock, status: "pending", type: "nutrition" },
  { time: "8:00 PM", activity: "Office Ends", icon: Clock, status: "pending", type: "work" },
  { time: "9:00 PM", activity: "Evening Gym", icon: Dumbbell, status: "pending", type: "gym" },
];

export function TodaySchedule() {
  const { data: sessions } = useQuery({
    queryKey: ["workouts", "today"],
    queryFn: () =>
      apiClient.get("/api/v1/workouts/sessions/today").then((r) => r.data),
  });

  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-sm">Today's Schedule</h3>
        <span className="text-xs text-muted-foreground">
          {format(new Date(), "EEE, MMM d")}
        </span>
      </div>

      <div className="space-y-2">
        {DEFAULT_SCHEDULE.map((item, i) => {
          const isCompleted = item.status === "completed";
          const isActive = item.status === "active";

          return (
            <div
              key={i}
              className={cn(
                "flex items-center gap-3 rounded-lg p-2.5 transition-colors",
                isCompleted && "opacity-50",
                isActive && "bg-primary/5 border border-primary/20"
              )}
            >
              <div className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
                item.type === "gym" && "bg-orange-500/10",
                item.type === "swim" && "bg-blue-500/10",
                item.type === "nutrition" && "bg-green-500/10",
                item.type === "work" && "bg-slate-500/10",
              )}>
                <item.icon className={cn(
                  "h-3.5 w-3.5",
                  item.type === "gym" && "text-orange-500",
                  item.type === "swim" && "text-blue-500",
                  item.type === "nutrition" && "text-green-500",
                  item.type === "work" && "text-slate-500",
                )} />
              </div>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{item.activity}</p>
                <p className="text-xs text-muted-foreground">{item.time}</p>
              </div>

              {isCompleted ? (
                <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
              ) : (
                <Circle className="h-4 w-4 text-muted-foreground/30 shrink-0" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
