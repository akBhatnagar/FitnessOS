"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { User } from "lucide-react";
import { cn } from "@/lib/utils";
import { apiClient } from "@/services/api";
import {
  LayoutDashboard,
  MessageSquare,
  Dumbbell,
  UtensilsCrossed,
  Waves,
  BarChart3,
  Calendar,
  Camera,
  Settings,
  Target,
  Zap,
  ClipboardList,
} from "lucide-react";

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "AI Coach", href: "/chat", icon: MessageSquare },
  { name: "Workouts", href: "/workouts", icon: Dumbbell },
  { name: "Nutrition", href: "/nutrition", icon: UtensilsCrossed },
  { name: "Swimming", href: "/swimming", icon: Waves },
  { name: "Analytics", href: "/analytics", icon: BarChart3 },
  { name: "Weekly Review", href: "/review", icon: ClipboardList },
  { name: "Schedule", href: "/schedule", icon: Calendar },
  { name: "Progress Photos", href: "/profile", icon: Camera },
];

const bottomNavigation = [
  { name: "Settings", href: "/settings", icon: Settings },
];

export function AppSidebar() {
  const pathname = usePathname();
  const [displayName, setDisplayName] = useState("Account");
  const [weightLabel, setWeightLabel] = useState("");

  useEffect(() => {
    apiClient
      .get("/api/v1/users/me")
      .then((res) => {
        const name = res.data?.name ?? res.data?.full_name;
        if (name) setDisplayName(String(name).split(" ")[0]);
      })
      .catch(() => {});

    apiClient
      .get("/api/v1/dashboard/summary")
      .then((res) => {
        const current = res.data?.metrics?.current_weight_kg;
        const target = res.data?.metrics?.target_weight_kg;
        if (current && target) setWeightLabel(`${current}kg → ${target}kg`);
      })
      .catch(() => {});
  }, []);

  return (
    <aside className="flex h-full w-64 flex-col border-r bg-card">
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b px-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
          <Zap className="h-4 w-4 text-primary-foreground" />
        </div>
        <div>
          <span className="font-bold text-lg tracking-tight">FitnessOS</span>
          <span className="block text-[10px] text-muted-foreground leading-none">AI Personal Trainer</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-1">
        {navigation.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150",
                isActive
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Bottom section */}
      <div className="border-t px-3 py-4 space-y-1">
        {bottomNavigation.map((item) => (
          <Link
            key={item.name}
            href={item.href}
            className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground transition-all duration-150"
          >
            <item.icon className="h-4 w-4 shrink-0" />
            {item.name}
          </Link>
        ))}

        {/* User profile */}
        <div className="flex items-center gap-3 px-3 py-2">
          <div className="h-8 w-8 rounded-full bg-primary/20 flex items-center justify-center shrink-0">
            <User className="h-4 w-4 text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium truncate">{displayName}</p>
            {weightLabel && (
              <p className="text-[10px] text-muted-foreground truncate">{weightLabel}</p>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}
