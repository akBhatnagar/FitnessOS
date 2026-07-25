/**
 * Streaming chat client — uses SSE over fetch so the UI can show live
 * status while the multi-agent pipeline runs (no hard client timeout).
 */

export interface ChatStreamDone {
  response: string;
  session_id: string;
  agent_trace?: string[];
  follow_up_suggestions?: string[];
  confidence_score?: number | null;
  request_id?: string;
}

export type ChatStreamHandlers = {
  onStatus?: (message: string, node?: string) => void;
  onHeartbeat?: () => void;
};

function apiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";
  return raw.replace(/\/api\/?$/, "");
}

function authHeader(): Record<string, string> {
  const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
  const isDevMode =
    !clerkKey ||
    !(
      (clerkKey.startsWith("pk_test_") || clerkKey.startsWith("pk_live_")) &&
      clerkKey.length > 30
    );

  if (isDevMode) {
    return { Authorization: "Bearer dev-token" };
  }

  if (typeof window !== "undefined") {
    const token = window.sessionStorage.getItem("fitnessos_clerk_token");
    if (token) {
      return { Authorization: `Bearer ${token}` };
    }
  }
  return {};
}

export async function streamChatMessage(
  message: string,
  sessionId: string,
  handlers: ChatStreamHandlers = {},
): Promise<ChatStreamDone> {
  const res = await fetch(`${apiBaseUrl()}/api/v1/chat/message`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...authHeader(),
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
      stream: true,
    }),
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }

  if (!res.body) {
    throw new Error("No response body from chat stream");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload: ChatStreamDone | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const line = part
        .split("\n")
        .find((l) => l.startsWith("data: "));
      if (!line) continue;

      let event: Record<string, unknown>;
      try {
        event = JSON.parse(line.slice(6));
      } catch {
        continue;
      }

      const type = event.type as string | undefined;
      if (type === "status") {
        handlers.onStatus?.(
          (event.message as string) || "Working on it…",
          event.node as string | undefined,
        );
      } else if (type === "heartbeat") {
        handlers.onHeartbeat?.();
      } else if (type === "done" || type === "error") {
        finalPayload = {
          response: (event.response as string) || "",
          session_id: (event.session_id as string) || sessionId,
          agent_trace: event.agent_trace as string[] | undefined,
          follow_up_suggestions: event.follow_up_suggestions as
            | string[]
            | undefined,
          confidence_score: event.confidence_score as number | null | undefined,
          request_id: event.request_id as string | undefined,
        };
        if (type === "error" && !finalPayload.response) {
          throw new Error(
            (event.message as string) || "I encountered an issue. Please try again.",
          );
        }
      }
    }
  }

  if (!finalPayload) {
    throw new Error("Chat stream ended without a response");
  }

  if (!finalPayload.response) {
    throw new Error("I couldn't generate a response. Please try again.");
  }

  return finalPayload;
}
