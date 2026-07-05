"use client";

import { Trophy } from "lucide-react";

interface Achievement {
  title: string;
  type: string;
  achieved_on: string;
  icon?: string;
}

export function RecentAchievements({ achievements }: { achievements: Achievement[] }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="flex items-center gap-2 mb-4">
        <Trophy className="h-4 w-4 text-amber-500" />
        <h3 className="font-semibold text-sm">Recent Achievements</h3>
      </div>
      <div className="flex gap-3 flex-wrap">
        {achievements.map((a, i) => (
          <div
            key={i}
            className="flex items-center gap-2 rounded-full border bg-amber-500/5 border-amber-500/20 px-3 py-1.5"
          >
            <span className="text-sm">{a.icon ?? "🏆"}</span>
            <span className="text-xs font-medium">{a.title}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
