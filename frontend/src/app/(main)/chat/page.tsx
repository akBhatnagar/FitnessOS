"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Send,
  Loader2,
  Bot,
  User,
  Sparkles,
  ChevronRight,
  History,
  Plus,
  MessageSquare,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import ReactMarkdown from "react-markdown";
import { streamChatMessage } from "@/services/chatStream";
import { apiClient } from "@/services/api";
import { cn } from "@/lib/utils";
import { format, parseISO } from "date-fns";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  followUpSuggestions?: string[];
}

interface SessionSummary {
  session_id: string;
  preview: string;
  last_message_at: string;
  message_count: number;
}

const CONVERSATION_STARTERS = [
  { emoji: "💪", text: "Create this week's workout plan" },
  { emoji: "🥗", text: "Plan my meals for today" },
  { emoji: "📊", text: "Analyze my progress this month" },
  { emoji: "🏊", text: "Give me a swimming lesson" },
  { emoji: "⚡", text: "How can I hit my wedding target?" },
  { emoji: "😴", text: "Help me fix my sleep schedule" },
];

const FALLBACK_STATUS = [
  "Working on it…",
  "Researching…",
  "Still thinking…",
  "Almost there…",
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [statusMessage, setStatusMessage] = useState("Working on it…");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const statusIdxRef = useRef(0);

  // Fetch session list
  const { data: sessionsData, refetch: refetchSessions } = useQuery({
    queryKey: ["chat-sessions"],
    queryFn: () => apiClient.get("/api/v1/chat/sessions").then((r) => r.data),
    enabled: historyOpen,
    staleTime: 30_000,
  });

  const sessions: SessionSummary[] = sessionsData?.sessions ?? [];

  const loadSession = async (sid: string) => {
    setLoadingHistory(true);
    try {
      const res = await apiClient.get(`/api/v1/chat/history/${sid}`);
      const loaded: Message[] = res.data.messages
        .filter((m: { role: string }) => m.role === "user" || m.role === "assistant")
        .map((m: { id: string; role: string; content: string; created_at: string }) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          timestamp: new Date(m.created_at),
        }));
      setMessages(loaded);
      setSessionId(sid);
      setHistoryOpen(false);
    } catch {
      // silently ignore
    } finally {
      setLoadingHistory(false);
    }
  };

  const startNewChat = () => {
    setMessages([]);
    setSessionId(crypto.randomUUID());
    setHistoryOpen(false);
  };

  const sendMessage = useMutation({
    mutationFn: (message: string) =>
      streamChatMessage(message, sessionId, {
        onStatus: (msg) => {
          statusIdxRef.current = 0;
          setStatusMessage(msg);
        },
        onHeartbeat: () => {
          statusIdxRef.current = (statusIdxRef.current + 1) % FALLBACK_STATUS.length;
          setStatusMessage((prev) => {
            if (prev && !FALLBACK_STATUS.includes(prev)) return prev;
            return FALLBACK_STATUS[statusIdxRef.current];
          });
        },
      }),
    onMutate: (message) => {
      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: message,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setInput("");
      setStatusMessage("Working on it…");
      statusIdxRef.current = 0;
    },
    onSuccess: (data) => {
      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.response || "I couldn't generate a response. Please try again.",
        timestamp: new Date(),
        followUpSuggestions: data.follow_up_suggestions,
      };
      setMessages((prev) => [...prev, assistantMsg]);
      // Invalidate session list so new session appears
      refetchSessions();
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
  }, [messages, sendMessage.isPending, statusMessage]);

  const handleSend = useCallback(() => {
    if (input.trim() && !sendMessage.isPending) {
      sendMessage.mutate(input.trim());
    }
  }, [input, sendMessage]);

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full gap-0">
      {/* History sidebar */}
      {historyOpen && (
        <div className="flex flex-col w-72 shrink-0 border-r bg-card/50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <span className="font-semibold text-sm">Chat History</span>
            <button
              onClick={() => setHistoryOpen(false)}
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="px-3 py-2">
            <Button variant="outline" size="sm" className="w-full gap-2" onClick={startNewChat}>
              <Plus className="h-4 w-4" />
              New Chat
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto space-y-1 px-2 pb-4">
            {loadingHistory && (
              <div className="flex justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            )}
            {!loadingHistory && sessions.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-8 px-2">
                No previous conversations yet
              </p>
            )}
            {sessions.map((s) => (
              <button
                key={s.session_id}
                onClick={() => loadSession(s.session_id)}
                className={cn(
                  "w-full text-left rounded-lg px-3 py-2.5 transition-colors hover:bg-accent group",
                  s.session_id === sessionId && "bg-accent"
                )}
              >
                <div className="flex items-start gap-2">
                  <MessageSquare className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs font-medium truncate leading-snug">
                      {s.preview || "Conversation"}
                    </p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {s.last_message_at
                        ? format(parseISO(s.last_message_at), "MMM d, h:mm a")
                        : ""}{" "}
                      · {s.message_count} msgs
                    </p>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Chat area */}
      <div className="flex flex-col flex-1 min-w-0 max-w-4xl mx-auto px-0 sm:px-4">
        {/* Header */}
        <div className="pb-4 border-b mb-4">
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setHistoryOpen((o) => !o); }}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-muted hover:bg-accent transition-colors"
              title="Chat history"
            >
              <History className="h-4 w-4 text-muted-foreground" />
            </button>
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
                  <span className="text-sm text-muted-foreground animate-pulse">
                    {statusMessage}
                  </span>
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
    </div>
  );
}
