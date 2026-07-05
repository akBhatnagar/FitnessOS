"use client";

import { useState, useRef, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Send, Loader2, Bot, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import ReactMarkdown from "react-markdown";
import { apiClient } from "@/services/api";
import { cn } from "@/lib/utils";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

const QUICK_PROMPTS = [
  "What should I eat today?",
  "How's my progress this week?",
  "Give me today's workout",
  "How many days to my wedding?",
];

export function QuickChat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hey! I'm your AI fitness coach. I know everything about your goals, schedule, and progress. What's on your mind today?",
    },
  ]);
  const [input, setInput] = useState("");
  const [sessionId] = useState(() => crypto.randomUUID());
  const bottomRef = useRef<HTMLDivElement>(null);

  const sendMessage = useMutation({
    mutationFn: (message: string) =>
      apiClient
        .post("/api/v1/chat/message", { message, session_id: sessionId })
        .then((r) => r.data),
    onMutate: (message) => {
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "user", content: message },
      ]);
      setInput("");
    },
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", content: data.response },
      ]);
    },
    onError: () => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "Sorry, I had trouble responding. Please try again.",
        },
      ]);
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    if (input.trim() && !sendMessage.isPending) {
      sendMessage.mutate(input.trim());
    }
  };

  return (
    <div className="flex flex-col rounded-xl border bg-card h-80">
      {/* Header */}
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary">
          <Bot className="h-3 w-3 text-primary-foreground" />
        </div>
        <h3 className="font-semibold text-sm">AI Coach</h3>
        <div className="ml-auto flex items-center gap-1">
          <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse-slow" />
          <span className="text-xs text-muted-foreground">Live</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn("flex gap-2 max-w-[85%]", msg.role === "user" && "ml-auto flex-row-reverse")}
          >
            <div
              className={cn(
                "flex h-6 w-6 shrink-0 items-center justify-center rounded-full mt-0.5",
                msg.role === "user" ? "bg-primary" : "bg-muted"
              )}
            >
              {msg.role === "user" ? (
                <User className="h-3 w-3 text-primary-foreground" />
              ) : (
                <Bot className="h-3 w-3 text-muted-foreground" />
              )}
            </div>
            <div
              className={cn(
                "rounded-xl px-3 py-2 text-sm",
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted"
              )}
            >
              <div className="prose-chat">
                <ReactMarkdown>{msg.content}</ReactMarkdown>
              </div>
            </div>
          </div>
        ))}
        {sendMessage.isPending && (
          <div className="flex gap-2">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted mt-0.5">
              <Bot className="h-3 w-3 text-muted-foreground" />
            </div>
            <div className="bg-muted rounded-xl px-3 py-2">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Quick prompts */}
      {messages.length === 1 && (
        <div className="px-4 pb-2 flex flex-wrap gap-1.5">
          {QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              onClick={() => sendMessage.mutate(prompt)}
              disabled={sendMessage.isPending}
              className="rounded-full border px-3 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              {prompt}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="border-t p-3 flex gap-2">
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Ask your coach..."
          className="min-h-0 h-9 resize-none text-sm py-2"
          rows={1}
        />
        <Button
          size="sm"
          onClick={handleSend}
          disabled={!input.trim() || sendMessage.isPending}
          className="h-9 w-9 p-0 shrink-0"
        >
          {sendMessage.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Send className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>
    </div>
  );
}
