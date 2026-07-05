"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Settings, User, Bell, Shield, Brain, Database,
  Server, Zap, Clock, Scale, Target,
} from "lucide-react";

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

const EVENTS = [
  { label: "Pre-Wedding Shoot", date: "October 20, 2026", color: "bg-amber-500/10 text-amber-500" },
  { label: "Wedding Day", date: "January 30, 2027", color: "bg-red-500/10 text-red-500" },
];

const PREFERENCES = [
  { label: "No tofu", value: true },
  { label: "No soya chunks", value: true },
  { label: "No creatine", value: true },
  { label: "Whey protein", value: true },
  { label: "Protein bars", value: true },
];

const TECH_INFO = [
  { label: "AI Provider", value: "OpenAI (GPT-4o-mini)" },
  { label: "Memory", value: "PostgreSQL + pgvector" },
  { label: "Agents", value: "10 specialist agents" },
  { label: "Environment", value: "Development" },
  { label: "Backend", value: "FastAPI + LangGraph" },
  { label: "Frontend", value: "Next.js 15 + shadcn/ui" },
];

export default function SettingsPage() {
  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Your profile, preferences, and system configuration
        </p>
      </div>

      {/* Profile */}
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

      {/* Goals */}
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

      {/* Daily schedule */}
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

      {/* Events */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Bell className="h-4 w-4" /> Key Events
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {EVENTS.map((e) => (
            <div
              key={e.label}
              className={`flex items-center justify-between p-3 rounded-lg ${e.color} bg-opacity-10`}
            >
              <span className="text-sm font-medium">{e.label}</span>
              <span className="text-sm">{e.date}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Dietary preferences */}
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

      {/* AI / System info */}
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

      {/* System status */}
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
