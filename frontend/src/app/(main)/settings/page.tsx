"use client";

import { useCallback, useEffect, useState } from "react";
import { format, parseISO } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  User, Bell, Shield, Brain, Server, Zap, Clock, Scale, Target, Loader2, Pencil, Check, X,
} from "lucide-react";
import { apiClient } from "@/services/api";
import { toast } from "sonner";
import { todayStr } from "@/components/shared/DatePickerBar";

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

const PROFILE = [
  { label: "Name", value: "Demo User" },
  { label: "Age", value: "28 years" },
  { label: "Height", value: "6'1\" (185 cm)" },
  { label: "Starting Weight", value: "100 kg" },
  { label: "Target Weight", value: "85 kg" },
  { label: "Diet", value: "Vegetarian (eggs after gym)" },
];

const SCHEDULE_INFO = [
  { label: "Office hours", value: "10:30 AM – 8:00 PM" },
  { label: "Swimming", value: "8:00 AM (weekdays)" },
  { label: "Gym", value: "9:00 PM – 10:00 PM" },
  { label: "Lunch break", value: "1:00 PM – 2:00 PM" },
  { label: "Target sleep", value: "12:00 AM" },
  { label: "Target wake", value: "7:00 AM" },
];

const TECH_INFO = [
  { label: "AI Provider", value: "OpenAI (GPT-4o-mini)" },
  { label: "Memory", value: "PostgreSQL + pgvector" },
  { label: "Agents", value: "10 specialist agents" },
  { label: "Environment", value: "Development" },
  { label: "Backend", value: "FastAPI + LangGraph" },
  { label: "Frontend", value: "Next.js 15 + shadcn/ui" },
];

function eventAccent(eventType: string): string {
  const t = eventType.toLowerCase();
  if (t.includes("wedding") && !t.includes("pre")) return "bg-red-500/10 text-red-500";
  if (t.includes("photo") || t.includes("pre")) return "bg-amber-500/10 text-amber-500";
  return "bg-primary/10 text-primary";
}

export default function SettingsPage() {
  const [events, setEvents] = useState<AppEvent[]>([]);
  const [loadingEvents, setLoadingEvents] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftDate, setDraftDate] = useState("");
  const [savingId, setSavingId] = useState<string | null>(null);

  const loadEvents = useCallback(async () => {
    try {
      const res = await apiClient.get("/api/v1/events/", { params: { include_past: true } });
      setEvents(res.data ?? []);
    } catch {
      toast.error("Failed to load events.");
    } finally {
      setLoadingEvents(false);
    }
  }, []);

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  const startEdit = (event: AppEvent) => {
    setEditingId(event.id);
    setDraftDate(event.event_date);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setDraftDate("");
  };

  const saveDate = async (event: AppEvent) => {
    if (!draftDate) {
      toast.error("Pick a date.");
      return;
    }
    if (draftDate === event.event_date) {
      cancelEdit();
      return;
    }
    setSavingId(event.id);
    try {
      const res = await apiClient.patch(`/api/v1/events/${event.id}`, {
        event_date: draftDate,
      });
      setEvents((prev) =>
        prev
          .map((e) => (e.id === event.id ? { ...e, ...res.data } : e))
          .sort((a, b) => a.event_date.localeCompare(b.event_date)),
      );
      toast.success(`${event.title} updated to ${format(parseISO(draftDate), "MMM d, yyyy")}`);
      cancelEdit();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to update event.";
      toast.error(msg);
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Your profile, preferences, and system configuration
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <User className="h-4 w-4" /> Profile
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {PROFILE.map((item) => (
            <div key={item.label} className="flex items-center justify-between py-1">
              <span className="text-sm text-muted-foreground">{item.label}</span>
              <span className="text-sm font-medium">{item.value}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Target className="h-4 w-4" /> Goals (Priority Order)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {[
              "Fat Loss", "Broad Shoulders", "V-Taper", "Bigger Arms", "Bigger Back",
              "Better Posture", "Bigger Chest", "Strong Legs", "Visible Abs",
              "Athletic Performance", "Endurance",
            ].map((goal, i) => (
              <Badge key={goal} variant={i === 0 ? "default" : "secondary"} className="text-xs">
                {i + 1}. {goal}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Clock className="h-4 w-4" /> Daily Schedule
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {SCHEDULE_INFO.map((item) => (
            <div key={item.label} className="flex items-center justify-between py-1">
              <span className="text-sm text-muted-foreground">{item.label}</span>
              <span className="text-sm font-medium">{item.value}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Bell className="h-4 w-4" /> Key Events
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {loadingEvents ? (
            <div className="flex justify-center py-6">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : events.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">No events configured yet.</p>
          ) : (
            events.map((event) => {
              const editing = editingId === event.id;
              const saving = savingId === event.id;
              return (
                <div
                  key={event.id}
                  className={`flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between p-3 rounded-lg ${eventAccent(event.event_type)}`}
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{event.title}</p>
                    <p className="text-[11px] opacity-80 mt-0.5">
                      {event.days_remaining >= 0
                        ? `${event.days_remaining} days remaining`
                        : `${Math.abs(event.days_remaining)} days ago`}
                      {event.peak_priority ? ` · ${event.peak_priority} peak` : ""}
                    </p>
                  </div>

                  {editing ? (
                    <div className="flex items-center gap-2">
                      <Input
                        type="date"
                        value={draftDate}
                        min={todayStr()}
                        onChange={(e) => setDraftDate(e.target.value)}
                        className="h-8 w-[150px] bg-background text-foreground"
                        disabled={saving}
                      />
                      <Button
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => saveDate(event)}
                        disabled={saving}
                      >
                        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8"
                        onClick={cancelEdit}
                        disabled={saving}
                      >
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">
                        {format(parseISO(event.event_date), "MMMM d, yyyy")}
                      </span>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8 text-current"
                        onClick={() => startEdit(event)}
                        aria-label={`Edit ${event.title} date`}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Scale className="h-4 w-4" /> Dietary Preferences
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2 mb-2">
              <span className="text-xs text-muted-foreground font-medium">Consumes:</span>
              {["Milk", "Paneer", "Curd", "Whey Protein", "Protein Bars", "Eggs (post-gym only)"].map((f) => (
                <Badge key={f} variant="outline" className="text-xs text-green-400 border-green-400/30">{f}</Badge>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="text-xs text-muted-foreground font-medium">Avoids:</span>
              {["Tofu", "Soya Chunks", "Creatine"].map((f) => (
                <Badge key={f} variant="outline" className="text-xs text-red-400 border-red-400/30">{f}</Badge>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Brain className="h-4 w-4" /> AI System
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {TECH_INFO.map((item) => (
            <div key={item.label} className="flex items-center justify-between py-1">
              <span className="text-sm text-muted-foreground">{item.label}</span>
              <span className="text-sm font-mono font-medium">{item.value}</span>
            </div>
          ))}
          <Separator className="my-2" />
          <div className="flex items-start gap-3 p-3 rounded-lg bg-muted/30">
            <Zap className="h-4 w-4 text-primary shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-medium">Multi-Agent Pipeline</p>
              <p className="text-xs text-muted-foreground mt-1">
                Coach → Memory → Knowledge → Workout → Nutrition → Swimming →
                Analytics → Scheduler → Event → Reflection
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Server className="h-4 w-4" /> System Status
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {[
            { service: "FastAPI Backend", status: "Running", color: "bg-green-400" },
            { service: "Next.js Frontend", status: "Running", color: "bg-green-400" },
            { service: "PostgreSQL", status: "Running", color: "bg-green-400" },
            { service: "Redis", status: "Running", color: "bg-green-400" },
            { service: "Celery Worker", status: "Running", color: "bg-green-400" },
            { service: "Clerk Auth", status: "Placeholder (Dev mode)", color: "bg-yellow-400" },
          ].map((s) => (
            <div key={s.service} className="flex items-center justify-between py-1">
              <div className="flex items-center gap-2">
                <div className={`h-2 w-2 rounded-full ${s.color} animate-pulse`} />
                <span className="text-sm">{s.service}</span>
              </div>
              <span className="text-xs text-muted-foreground">{s.status}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="flex items-center gap-2 p-4 rounded-lg bg-muted/30 border border-border/50">
        <Shield className="h-4 w-4 text-muted-foreground shrink-0" />
        <p className="text-xs text-muted-foreground">
          FitnessOS is protected by HTTP Basic Authentication. All data is stored privately on your
          DigitalOcean droplet. No data is shared with third parties.
        </p>
      </div>
    </div>
  );
}
