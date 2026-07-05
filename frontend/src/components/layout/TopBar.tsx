"use client";

import { useState, useRef, useEffect } from "react";
import { format, differenceInDays } from "date-fns";
import { Bell, Search, X, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useRouter } from "next/navigation";

const EVENTS = [
  { label: "Pre-Wedding Shoot", date: new Date(2026, 9, 20), color: "text-amber-400", bg: "bg-amber-500/10" },
  { label: "Wedding Day", date: new Date(2027, 0, 30), color: "text-red-400", bg: "bg-red-500/10" },
];

function getNotifications() {
  const today = new Date();
  const notifications = [];

  // Event countdowns
  for (const event of EVENTS) {
    const days = differenceInDays(event.date, today);
    if (days >= 0 && days <= 120) {
      notifications.push({
        id: `event-${event.label}`,
        type: "event",
        title: `${days} days until ${event.label}`,
        body: `Stay consistent — every workout counts toward ${event.label.toLowerCase()}.`,
        urgent: days <= 30,
        color: event.color,
      });
    }
  }

  // Daily reminders
  const hour = today.getHours();
  if (hour >= 7 && hour < 9) {
    notifications.push({
      id: "reminder-swim",
      type: "reminder",
      title: "Swimming session reminder",
      body: "Your 8:00 AM swim is coming up. Stay consistent!",
      urgent: false,
      color: "text-blue-400",
    });
  }
  if (hour >= 20 && hour < 22) {
    notifications.push({
      id: "reminder-gym",
      type: "reminder",
      title: "Gym session time",
      body: "Your 9:00 PM gym session is scheduled for tonight.",
      urgent: false,
      color: "text-orange-400",
    });
  }

  // Weekly review reminder (Sunday)
  if (today.getDay() === 0) {
    notifications.push({
      id: "reminder-review",
      type: "review",
      title: "Weekly review day",
      body: "It's Sunday — time for your weekly check-in with your AI coach.",
      urgent: true,
      color: "text-green-400",
    });
  }

  // Generic motivation
  notifications.push({
    id: "motivation",
    type: "tip",
    title: "Today's tip",
    body: "Progressive overload is the key to muscle growth. Add small weight increments each session.",
    urgent: false,
    color: "text-primary",
  });

  return notifications;
}

export function TopBar() {
  const router = useRouter();
  const [showNotifications, setShowNotifications] = useState(false);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [searchValue, setSearchValue] = useState("");
  const panelRef = useRef<HTMLDivElement>(null);

  const allNotifications = getNotifications();
  const visibleNotifications = allNotifications.filter((n) => !dismissed.has(n.id));
  const hasUnread = visibleNotifications.length > 0;

  // Close panel on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setShowNotifications(false);
      }
    }
    if (showNotifications) {
      document.addEventListener("mousedown", handleClick);
    }
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showNotifications]);

  const handleSearch = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && searchValue.trim()) {
      router.push(`/chat?q=${encodeURIComponent(searchValue.trim())}`);
      setSearchValue("");
    }
  };

  return (
    <header className="flex h-16 items-center justify-between border-b bg-card/50 px-6 backdrop-blur-sm sticky top-0 z-10">
      {/* Search */}
      <div className="flex items-center gap-3 w-72 relative">
        <Search className="h-4 w-4 text-muted-foreground absolute ml-3 pointer-events-none" />
        <Input
          value={searchValue}
          onChange={(e) => setSearchValue(e.target.value)}
          onKeyDown={handleSearch}
          placeholder="Ask your coach anything..."
          className="pl-9 bg-background h-9 text-sm"
        />
      </div>

      <div className="flex items-center gap-2" ref={panelRef}>
        {/* Countdown pills */}
        <div className="hidden md:flex items-center gap-2 mr-4">
          <CountdownPill
            label="Pre-Wedding"
            targetDate={new Date(2026, 9, 20)}
            className="bg-amber-500/10 text-amber-500 border-amber-500/20"
          />
          <CountdownPill
            label="Wedding"
            targetDate={new Date(2027, 0, 30)}
            className="bg-red-500/10 text-red-500 border-red-500/20"
          />
        </div>

        {/* Notification bell */}
        <div className="relative">
          <Button
            variant="ghost"
            size="icon"
            className="relative"
            onClick={() => setShowNotifications((v) => !v)}
          >
            <Bell className="h-4 w-4" />
            {hasUnread && (
              <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-primary animate-pulse" />
            )}
          </Button>

          {/* Notification panel */}
          {showNotifications && (
            <div className="absolute right-0 top-12 w-80 bg-card border border-border rounded-xl shadow-xl z-50 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b">
                <div className="flex items-center gap-2">
                  <Bell className="h-4 w-4 text-primary" />
                  <span className="text-sm font-semibold">Notifications</span>
                  {visibleNotifications.length > 0 && (
                    <Badge className="h-5 text-xs px-1.5">{visibleNotifications.length}</Badge>
                  )}
                </div>
                <button
                  onClick={() => setShowNotifications(false)}
                  className="text-muted-foreground hover:text-foreground transition-colors"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="max-h-80 overflow-y-auto divide-y divide-border/50">
                {visibleNotifications.length === 0 ? (
                  <div className="px-4 py-8 text-center">
                    <Bell className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">All caught up!</p>
                  </div>
                ) : (
                  visibleNotifications.map((n) => (
                    <div
                      key={n.id}
                      className={`px-4 py-3 flex items-start gap-3 hover:bg-muted/30 transition-colors ${
                        n.urgent ? "bg-primary/5" : ""
                      }`}
                    >
                      <div className={`h-2 w-2 rounded-full mt-1.5 shrink-0 ${n.color.replace("text-", "bg-")}`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium leading-snug">{n.title}</p>
                        <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">{n.body}</p>
                      </div>
                      <button
                        onClick={() => setDismissed((d) => new Set([...d, n.id]))}
                        className="text-muted-foreground/50 hover:text-muted-foreground shrink-0"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ))
                )}
              </div>

              {visibleNotifications.length > 0 && (
                <div className="px-4 py-2 border-t">
                  <button
                    onClick={() => {
                      setDismissed(new Set(allNotifications.map((n) => n.id)));
                      setShowNotifications(false);
                    }}
                    className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
                  >
                    Mark all as read <ChevronRight className="h-3 w-3" />
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

function CountdownPill({
  label,
  targetDate,
  className,
}: {
  label: string;
  targetDate: Date;
  className?: string;
}) {
  const today = new Date();
  const days = Math.ceil((targetDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));

  if (days < 0) return null;

  return (
    <div
      className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium cursor-default ${className}`}
    >
      <span>{label}:</span>
      <span className="font-bold">{days}d</span>
    </div>
  );
}
