"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { format, parseISO, differenceInWeeks, differenceInMonths } from "date-fns";
import { Bell, Search, X, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useRouter } from "next/navigation";
import { apiClient } from "@/services/api";

interface AppEvent {
  id: string;
  title: string;
  description?: string | null;
  event_type: string;
  event_date: string;
  location?: string | null;
  peak_priority: string;
  days_remaining: number;
  is_critical: boolean;
  is_upcoming: boolean;
}

interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  urgent: boolean;
  color: string;
}

// ─── LocalStorage Read State ────────────────────────────────────────────────

const READ_STATE_KEY = "fitnessos:notifications:read";

function getReadState(): Set<string> {
  try {
    const raw = localStorage.getItem(READ_STATE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return new Set(parsed as string[]);
    return new Set();
  } catch {
    return new Set();
  }
}

function persistReadState(readIds: Set<string>) {
  try {
    localStorage.setItem(READ_STATE_KEY, JSON.stringify([...readIds]));
  } catch {
    // localStorage full or unavailable — fail silently
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function shortLabel(title: string, eventType: string): string {
  const t = title.toLowerCase();
  const type = eventType.toLowerCase();
  if (t.includes("pre-wedding") || t.includes("pre wedding") || type.includes("photo")) {
    return "Pre-Wedding";
  }
  if (t.includes("wedding") || type === "wedding") return "Wedding";
  return title.length > 14 ? `${title.slice(0, 12)}…` : title;
}

function pillClasses(eventType: string): string {
  const t = eventType.toLowerCase();
  if (t.includes("wedding") && !t.includes("pre")) {
    return "bg-red-500/10 text-red-500 border-red-500/20";
  }
  if (t.includes("photo") || t.includes("pre")) {
    return "bg-amber-500/10 text-amber-500 border-amber-500/20";
  }
  return "bg-primary/10 text-primary border-primary/20";
}

function formatCountdownDetail(days: number): string {
  if (days < 0) return `${Math.abs(days)} days ago`;
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  const weeks = Math.floor(days / 7);
  const months = Math.floor(days / 30);
  if (months >= 2) return `${days} days · ~${months} months`;
  if (weeks >= 2) return `${days} days · ~${weeks} weeks`;
  return `${days} days`;
}

function buildEventNotifications(events: AppEvent[]): Notification[] {
  const notifications: Notification[] = [];
  for (const event of events) {
    const days = event.days_remaining;
    if (days >= 0 && days <= 120) {
      notifications.push({
        id: `event-${event.id}`,
        type: "event",
        title: `${days} days until ${event.title}`,
        body: `Stay consistent — every workout counts toward ${event.title.toLowerCase()}.`,
        urgent: days <= 30,
        color: event.event_type.toLowerCase().includes("wedding") && !event.event_type.toLowerCase().includes("pre")
          ? "text-red-400"
          : "text-amber-400",
      });
    }
  }
  return notifications;
}

// ─── TopBar Component ─────────────────────────────────────────────────────────

export function TopBar() {
  const router = useRouter();
  const [showNotifications, setShowNotifications] = useState(false);
  const [readIds, setReadIds] = useState<Set<string>>(new Set());
  const [searchValue, setSearchValue] = useState("");
  const [events, setEvents] = useState<AppEvent[]>([]);
  const [dailyTip, setDailyTip] = useState<string | null>(null);
  const [tipLoading, setTipLoading] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // Load read state from localStorage on mount
  useEffect(() => {
    setReadIds(getReadState());
  }, []);

  // Load events
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await apiClient.get("/api/v1/events/");
        if (!cancelled) setEvents(res.data ?? []);
      } catch {
        // Keep empty — pills simply hide until events load
      }
    };
    load();
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  // Load daily tip once (only when notification panel is opened for the first time)
  const loadDailyTip = useCallback(async () => {
    if (dailyTip !== null || tipLoading) return;
    setTipLoading(true);
    try {
      const res = await apiClient.get("/api/v1/notifications/daily-tip");
      setDailyTip(res.data.tip);
    } catch {
      setDailyTip("Focus on consistency over perfection today.");
    } finally {
      setTipLoading(false);
    }
  }, [dailyTip, tipLoading]);

  // Build notifications list
  const allNotifications: Notification[] = [
    ...buildEventNotifications(events),
    ...(dailyTip
      ? [{
          id: "daily-tip",
          type: "tip",
          title: "Today's tip",
          body: dailyTip,
          urgent: false,
          color: "text-primary",
        }]
      : []),
  ];

  const unreadNotifications = allNotifications.filter((n) => !readIds.has(n.id));
  const hasUnread = unreadNotifications.length > 0 || dailyTip === null;

  // Mark a single notification as read
  const markRead = (id: string) => {
    setReadIds((prev) => {
      const next = new Set(prev);
      next.add(id);
      persistReadState(next);
      return next;
    });
  };

  // Mark all as read
  const markAllRead = () => {
    setReadIds((prev) => {
      const next = new Set(prev);
      allNotifications.forEach((n) => next.add(n.id));
      persistReadState(next);
      return next;
    });
    setShowNotifications(false);
  };

  // When panel opens, fetch tip if needed + mark visible notifications as read
  useEffect(() => {
    if (showNotifications) {
      loadDailyTip();
      // Auto-mark event notifications as read when panel is opened
      const timer = setTimeout(() => {
        setReadIds((prev) => {
          const next = new Set(prev);
          let changed = false;
          allNotifications.forEach((n) => {
            if (!next.has(n.id)) {
              next.add(n.id);
              changed = true;
            }
          });
          if (changed) persistReadState(next);
          return next;
        });
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [showNotifications, dailyTip]);

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

  const upcomingEvents = events.filter((e) => e.days_remaining >= 0);

  return (
    <header className="flex h-16 items-center justify-between border-b bg-card/50 px-6 backdrop-blur-sm sticky top-0 z-10">
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
        <div className="hidden md:flex items-center gap-2 mr-4">
          {upcomingEvents.map((event) => (
            <CountdownPill
              key={event.id}
              label={shortLabel(event.title, event.event_type)}
              event={event}
              className={pillClasses(event.event_type)}
            />
          ))}
        </div>

        <div className="relative">
          <Button
            variant="ghost"
            size="icon"
            className="relative"
            onClick={() => setShowNotifications((v) => !v)}
          >
            <Bell className="h-4 w-4" />
            {hasUnread && unreadNotifications.length > 0 && (
              <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-primary animate-pulse" />
            )}
          </Button>

          {showNotifications && (
            <div className="absolute right-0 top-12 w-80 bg-card border border-border rounded-xl shadow-xl z-50 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b">
                <div className="flex items-center gap-2">
                  <Bell className="h-4 w-4 text-primary" />
                  <span className="text-sm font-semibold">Notifications</span>
                  {unreadNotifications.length > 0 && (
                    <Badge className="h-5 text-xs px-1.5">{unreadNotifications.length}</Badge>
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
                {allNotifications.length === 0 && !tipLoading ? (
                  <div className="px-4 py-8 text-center">
                    <Bell className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                    <p className="text-sm text-muted-foreground">All caught up!</p>
                  </div>
                ) : (
                  <>
                    {tipLoading && dailyTip === null && (
                      <div className="px-4 py-3 text-xs text-muted-foreground animate-pulse">
                        Generating your personalized tip...
                      </div>
                    )}
                    {allNotifications.map((n) => {
                      const isRead = readIds.has(n.id);
                      return (
                        <div
                          key={n.id}
                          onClick={() => markRead(n.id)}
                          className={`px-4 py-3 flex items-start gap-3 hover:bg-muted/30 transition-colors cursor-pointer ${
                            n.urgent && !isRead ? "bg-primary/5" : ""
                          }`}
                        >
                          <div className={`h-2 w-2 rounded-full mt-1.5 shrink-0 ${
                            isRead ? "bg-muted-foreground/20" : n.color.replace("text-", "bg-")
                          }`} />
                          <div className="flex-1 min-w-0">
                            <p className={`text-xs font-medium leading-snug ${isRead ? "text-muted-foreground" : ""}`}>
                              {n.title}
                            </p>
                            <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug">{n.body}</p>
                          </div>
                        </div>
                      );
                    })}
                  </>
                )}
              </div>

              {unreadNotifications.length > 0 && (
                <div className="px-4 py-2 border-t">
                  <button
                    onClick={markAllRead}
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

// ─── CountdownPill ────────────────────────────────────────────────────────────

function CountdownPill({
  label,
  event,
  className,
}: {
  label: string;
  event: AppEvent;
  className?: string;
}) {
  const days = event.days_remaining;
  if (days < 0) return null;

  const date = parseISO(event.event_date);
  const weeks = differenceInWeeks(date, new Date());
  const months = differenceInMonths(date, new Date());
  const weekdays = format(date, "EEEE");

  return (
    <div className="relative group">
      <div
        className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium cursor-default ${className}`}
      >
        <span>{label}:</span>
        <span className="font-bold">{days}d</span>
      </div>

      <div
        className="pointer-events-none absolute left-1/2 top-full z-50 mt-2 w-64 -translate-x-1/2 rounded-xl border bg-card p-3 text-left shadow-xl opacity-0 scale-95 transition-all duration-150 group-hover:opacity-100 group-hover:scale-100"
        role="tooltip"
      >
        <p className="text-sm font-semibold text-foreground">{event.title}</p>
        <div className="mt-2 space-y-1.5 text-[11px] text-muted-foreground">
          <div className="flex justify-between gap-3">
            <span>Date</span>
            <span className="font-medium text-foreground">
              {format(date, "EEE, MMM d, yyyy")}
            </span>
          </div>
          <div className="flex justify-between gap-3">
            <span>Countdown</span>
            <span className="font-medium text-foreground">{formatCountdownDetail(days)}</span>
          </div>
          {weeks > 0 && (
            <div className="flex justify-between gap-3">
              <span>Weeks left</span>
              <span className="font-medium text-foreground">{weeks}</span>
            </div>
          )}
          {months > 0 && (
            <div className="flex justify-between gap-3">
              <span>Months left</span>
              <span className="font-medium text-foreground">~{months}</span>
            </div>
          )}
          <div className="flex justify-between gap-3">
            <span>Falls on</span>
            <span className="font-medium text-foreground">{weekdays}</span>
          </div>
          {event.peak_priority && (
            <div className="flex justify-between gap-3">
              <span>Peak focus</span>
              <span className="font-medium text-foreground capitalize">{event.peak_priority}</span>
            </div>
          )}
          {event.location && (
            <div className="flex justify-between gap-3">
              <span>Location</span>
              <span className="font-medium text-foreground">{event.location}</span>
            </div>
          )}
          {event.is_critical && (
            <p className="pt-1 text-[10px] font-medium text-red-400">
              Critical window — within 30 days
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
