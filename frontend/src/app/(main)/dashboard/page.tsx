"use client";

import { useQuery } from "@tanstack/react-query";
import { differenceInDays, format, parseISO } from "date-fns";
import { MetricsStrip } from "@/components/dashboard/MetricsStrip";
import { WeightChart } from "@/components/dashboard/WeightChart";
import { CountdownCards } from "@/components/dashboard/CountdownCards";
import { TodaySchedule } from "@/components/dashboard/TodaySchedule";
import { QuickChat } from "@/components/dashboard/QuickChat";
import { RecentAchievements } from "@/components/dashboard/RecentAchievements";
import { apiClient } from "@/services/api";

export default function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => apiClient.get("/api/v1/dashboard/summary").then((r) => r.data),
    refetchInterval: 60_000, // refresh every minute
  });

  if (isLoading) {
    return <DashboardSkeleton />;
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-muted-foreground">Failed to load dashboard data.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Welcome back{data.user?.name ? `, ${data.user.name.split(" ")[0]}` : ""}
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          {format(new Date(), "EEEE, MMMM d, yyyy")} · Your AI coach is ready.
        </p>
      </div>

      {/* Metrics strip */}
      <MetricsStrip metrics={data.metrics} weeklyProgress={data.weekly_progress} />

      {/* Main grid */}
      <div className="grid grid-cols-12 gap-6">
        {/* Weight chart — wide */}
        <div className="col-span-12 lg:col-span-8">
          <WeightChart
            data={data.weight_history}
            targetWeight={data.metrics?.target_weight_kg ?? 85}
          />
        </div>

        {/* Countdown cards — narrow */}
        <div className="col-span-12 lg:col-span-4">
          <CountdownCards countdowns={data.countdowns} prediction={data.prediction} />
        </div>

        {/* Today's schedule */}
        <div className="col-span-12 lg:col-span-5">
          <TodaySchedule />
        </div>

        {/* Quick chat */}
        <div className="col-span-12 lg:col-span-7">
          <QuickChat />
        </div>

        {/* Recent achievements */}
        {data.recent_achievements?.length > 0 && (
          <div className="col-span-12">
            <RecentAchievements achievements={data.recent_achievements} />
          </div>
        )}
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      <div className="h-8 w-64 bg-muted rounded" />
      <div className="grid grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-24 bg-muted rounded-xl" />
        ))}
      </div>
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-8 h-72 bg-muted rounded-xl" />
        <div className="col-span-4 h-72 bg-muted rounded-xl" />
      </div>
    </div>
  );
}
