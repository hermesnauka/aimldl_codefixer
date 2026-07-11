import { useCallback, useRef, useState } from "react";
import { postChat } from "../api/client";
import type { ChatRequest, ChatStreamEvent } from "../types";

export type ChatStreamStatus = "idle" | "streaming" | "done" | "error";

interface UseChatStreamResult {
  status: ChatStreamStatus;
  events: ChatStreamEvent[];
  streamError: string | null;
  /** Starts a new POST /api/v1/chat SSE stream; resets prior events. */
  sendChat: (request: ChatRequest) => Promise<void>;
  /** Aborts an in-flight stream, if any. */
  cancel: () => void;
}

/**
 * Consumes the Gateway's `POST /api/v1/chat` SSE stream.
 *
 * CONTRACT.md's `/api/v1/chat` needs a JSON POST body, which native
 * `EventSource` cannot send (EventSource is GET-only). So this hook uses
 * `fetch` + the response body's `ReadableStream`, and manually parses SSE
 * framing: events are separated by a blank line (`\n\n`), and within an
 * event we only care about `data: <json>` lines — exactly the framing
 * CONTRACT.md section 2 describes ("Content-Type: text/event-stream",
 * one JSON object per `data:` field).
 */
export function useChatStream(): UseChatStreamResult {
  const [status, setStatus] = useState<ChatStreamStatus>("idle");
  const [events, setEvents] = useState<ChatStreamEvent[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const sendChat = useCallback(async (request: ChatRequest) => {
    cancel();
    const controller = new AbortController();
    abortRef.current = controller;

    setEvents([]);
    setStreamError(null);
    setStatus("streaming");

    try {
      const response = await postChat(request, controller.signal);
      const body = response.body;
      if (!body) {
        throw new Error("Response has no readable body for SSE streaming");
      }

      const reader = body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line. Split conservatively
        // and keep the trailing partial frame in the buffer.
        const frames = buffer.split("\n\n");
        buffer = frames.pop() ?? "";

        for (const frame of frames) {
          const dataLines = frame
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trimStart());

          if (dataLines.length === 0) continue;

          const jsonText = dataLines.join("\n");
          if (!jsonText) continue;

          try {
            const parsed = JSON.parse(jsonText) as ChatStreamEvent;
            setEvents((prev) => [...prev, parsed]);
            if (parsed.type === "done") {
              setStatus("done");
            } else if (parsed.type === "error") {
              setStatus("error");
              setStreamError(parsed.message);
            }
          } catch (parseErr) {
            // Malformed frame from the Gateway — surface but keep reading,
            // one bad frame shouldn't kill the whole reasoning stream.
            // eslint-disable-next-line no-console
            console.error("Failed to parse SSE frame as JSON:", jsonText, parseErr);
          }
        }
      }

      // Flush any remaining buffered frame once the stream closes.
      if (buffer.trim().length > 0) {
        const dataLines = buffer
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart());
        const jsonText = dataLines.join("\n");
        if (jsonText) {
          try {
            const parsed = JSON.parse(jsonText) as ChatStreamEvent;
            setEvents((prev) => [...prev, parsed]);
          } catch {
            // ignore trailing garbage
          }
        }
      }

      setStatus((prev) => (prev === "error" ? prev : "done"));
    } catch (err) {
      if ((err as { name?: string }).name === "AbortError") {
        return;
      }
      setStatus("error");
      setStreamError(err instanceof Error ? err.message : String(err));
    } finally {
      abortRef.current = null;
    }
  }, [cancel]);

  return { status, events, streamError, sendChat, cancel };
}
