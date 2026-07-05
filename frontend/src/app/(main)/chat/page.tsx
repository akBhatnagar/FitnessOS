"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Send, Loader2, Bot, User, Sparkles, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import ReactMarkdown from "react-markdown";
import { apiClient } from "@/services/api";
import { cn } from "@/lib/utils";
import { format } from "date-fns";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  followUpSuggestions?: string[];
}

const CONVERSATION_STARTERS = [
  { emoji: "💪", text: "Create this week's workout plan" },
  { emoji: "🥗", text: "Plan my meals for today" },
  { emoji: "📊", text: "Analyze my progress this month" },
  { emoji: "🏊", text: "Give me a swimming lesson" },
  { emoji: "⚡", text: "How can I hit my wedding target?" },
  { emoji: "😴", text: "Help me fix my sleep schedule" },
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId] = useState(() => crypto.randomUUID());
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const sendMessage = useMutation({
    mutationFn: (message: string) =>
      apiClient
        .post("/api/v1/chat/message", { message, session_id: sessionId })
        .then((r) => r.data),
    onMutate: (message) => {
      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: message,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setInput("");
    },
    onSuccess: (data) => {
      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.response,
        timestamp: new Date(),
        followUpSuggestions: data.follow_up_suggestions,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    },
    onError: () => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "I encountered an issue. Please try again.",
          timestamp: new Date(),
        },
      ]);
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sendMessage.isPending]);

  const handleSend = useCallback(() => {
    if (input.trim() && !sendMessage.isPending) {
      sendMessage.mutate(input.trim());
    }
  }, [input, sendMessage]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full max-w-4xl mx-auto">
      {/* Header */}
      <div className="pb-4 border-b mb-4">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary">
            <Sparkles className="h-4 w-4 text-primary-foreground" />
          </div>
          <div>
            <h1 className="font-bold text-lg">FitnessOS Coach</h1>
            <p className="text-xs text-muted-foreground">
              Your AI trainer · Knows your full history
            </p>
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse-slow" />
            <span className="text-xs text-muted-foreground">Online</span>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-6 pb-4">
        {isEmpty ? (
          <div className="space-y-8 py-8">
            <div className="text-center space-y-2">
              <div className="flex justify-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
                  <Sparkles className="h-8 w-8 text-primary" />
                </div>
              </div>
              <h2 className="text-xl font-bold">What would you like help with?</h2>
              <p className="text-muted-foreground text-sm max-w-md mx-auto">
                I remember everything — your workouts, meals, sleep, goals, and upcoming events.
                Ask me anything.
              </p>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {CONVERSATION_STARTERS.map((starter) => (
                <button
                  key={starter.text}
                  onClick={() => sendMessage.mutate(starter.text)}
                  className="flex items-center gap-3 rounded-xl border bg-card p-3 text-left hover:bg-accent transition-colors text-sm"
                >
                  <span className="text-xl">{starter.emoji}</span>
                  <span className="font-medium">{starter.text}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={cn("flex gap-3", msg.role === "user" && "flex-row-reverse")}>
              <div
                className={cn(
                  "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
                  msg.role === "user" ? "bg-primary" : "bg-muted"
                )}
              >
                {msg.role === "user" ? (
                  <User className="h-4 w-4 text-primary-foreground" />
                ) : (
                  <Bot className="h-4 w-4 text-muted-foreground" />
                )}
              </div>
              <div className={cn("flex-1 max-w-[80%]", msg.role === "user" && "text-right")}>
                <div
                  className={cn(
                    "inline-block rounded-2xl px-4 py-3 text-sm text-left",
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground rounded-tr-sm"
                      : "bg-muted rounded-tl-sm"
                  )}
                >
                  <div className="prose-chat">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mt-1 px-1">
                  {format(msg.timestamp, "h:mm a")}
                </p>

                {/* Follow-up suggestions */}
                {msg.followUpSuggestions && msg.followUpSuggestions.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-2">
                    {msg.followUpSuggestions.map((suggestion) => (
                      <button
                        key={suggestion}
                        onClick={() => sendMessage.mutate(suggestion)}
                        className="flex items-center gap-1 rounded-full border px-3 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
                      >
                        {suggestion}
                        <ChevronRight className="h-3 w-3" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))
        )}

        {sendMessage.isPending && (
          <div className="flex gap-3">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
              <Bot className="h-4 w-4 text-muted-foreground" />
            </div>
            <div className="bg-muted rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Thinking...</span>
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t pt-4">
        <div className="flex gap-3 items-end">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Message your coach..."
            className="min-h-[48px] max-h-36 resize-none text-sm"
            rows={1}
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || sendMessage.isPending}
            size="icon"
            className="h-12 w-12 shrink-0"
          >
            {sendMessage.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-2 text-center">
          Press Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
