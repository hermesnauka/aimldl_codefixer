import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { clearSession, getStoredUsername } from "../api/client";
import ExecutionResultCard from "../components/ExecutionResultCard";
import FailoverNotice from "../components/FailoverNotice";
import FinalFixCard from "../components/FinalFixCard";
import ReasoningPanel, {
  StatusIndicator,
} from "../components/ReasoningPanel";
import { useChatStream } from "../hooks/useChatStream";
import type { AgentStage, ChatStreamEvent, Language } from "../types";

interface ChatProps {
  onLogout: () => void;
}

interface TimelineMessage {
  key: string;
  role: "user" | "system";
  content: string;
}

let messageCounter = 0;
function nextKey(prefix: string): string {
  messageCounter += 1;
  return `${prefix}-${messageCounter}`;
}

export default function Chat({ onLogout }: ChatProps) {
  const username = getStoredUsername();
  const { status, events, streamError, sendChat } = useChatStream();

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [language, setLanguage] = useState<Language | "">("");
  const [code, setCode] = useState("");
  const [errorLog, setErrorLog] = useState("");
  const [timeline, setTimeline] = useState<TimelineMessage[]>([]);

  const listEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [timeline, events]);

  // CONTRACT.md §2: `session` is always the first frame of every response
  // and carries the sessionId the Gateway assigned (new or reused) — this is
  // the only way we learn it when the very first turn was sent with
  // sessionId: null.
  useEffect(() => {
    const sessionEvent = events.find(
      (e): e is Extract<ChatStreamEvent, { type: "session" }> =>
        e.type === "session",
    );
    if (sessionEvent && sessionEvent.sessionId !== sessionId) {
      setSessionId(sessionEvent.sessionId);
    }
  }, [events, sessionId]);

  const reasoningText = useMemo(
    () =>
      events
        .filter(
          (e): e is Extract<ChatStreamEvent, { type: "reasoning_token" }> =>
            e.type === "reasoning_token",
        )
        .map((e) => e.token)
        .join(""),
    [events],
  );

  const currentStage: AgentStage | null = useMemo(() => {
    const statusEvents = events.filter(
      (e): e is Extract<ChatStreamEvent, { type: "status" }> =>
        e.type === "status",
    );
    return statusEvents.length > 0
      ? statusEvents[statusEvents.length - 1].stage
      : null;
  }, [events]);

  const isStreaming = status === "streaming";
  const isDone = status === "done";
  const hasError = status === "error";

  function handleLogout() {
    clearSession();
    onLogout();
  }

  function handleNewSession() {
    setSessionId(null);
    setTimeline([]);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!code.trim()) return;

    const userSummary = errorLog.trim()
      ? `${code}\n\n--- error log ---\n${errorLog}`
      : code;
    setTimeline((prev) => [
      ...prev,
      { key: nextKey("user"), role: "user", content: userSummary },
    ]);

    await sendChat({
      sessionId,
      language: language || null,
      code,
      errorLog: errorLog || undefined,
    });
  }

  return (
    <div className="app-shell">
      <header className="masthead-bar">
        <div>
          <h1 className="masthead">
            <span className="masthead-seal">CF</span>
            CodeFixer AI
          </h1>
          <div className="masthead-subtitle">
            Institutional-grade automated debugging
          </div>
        </div>
        <div className="masthead-user">
          {username && <span>Signed in as {username}</span>}
          <button className="btn btn-secondary" onClick={handleNewSession}>
            New session
          </button>
          <button className="btn btn-secondary" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </header>

      <div className="chat-layout">
        <div className="chat-column">
          <div className="card" style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
            <h2 className="card-title">Conversation</h2>
            <div className="message-list">
              {timeline.length === 0 && events.length === 0 && (
                <p className="reasoning-panel-empty">
                  Paste a code snippet and, optionally, an error log below to
                  begin.
                </p>
              )}
              {timeline.map((m) => (
                <div key={m.key} className={`message message--${m.role}`}>
                  <span className="message-role">{m.role}</span>
                  {m.content}
                </div>
              ))}

              {events.map((e, idx) => (
                <ChatEventMessage key={`${status}-${idx}`} event={e} />
              ))}

              {streamError && (
                <div className="message message--system">
                  <span className="message-role">error</span>
                  {streamError}
                </div>
              )}
              <div ref={listEndRef} />
            </div>
          </div>

          <div className="card">
            <h2 className="card-title">Submit Code &amp; Error Log</h2>
            <form className="chat-input-form" onSubmit={handleSubmit}>
              <div className="chat-input-row">
                <div className="field">
                  <label htmlFor="language">Language (optional)</label>
                  <select
                    id="language"
                    value={language}
                    onChange={(e) =>
                      setLanguage(e.target.value as Language | "")
                    }
                  >
                    <option value="">Auto-detect</option>
                    <option value="python">Python</option>
                    <option value="java">Java</option>
                    <option value="javascript">JavaScript</option>
                  </select>
                </div>
              </div>
              <div className="field">
                <label htmlFor="code">Source code</label>
                <textarea
                  id="code"
                  rows={8}
                  placeholder="Paste the uncompiled / failing source snippet here…"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="errorLog">Stack trace / compiler output (optional)</label>
                <textarea
                  id="errorLog"
                  rows={5}
                  placeholder="Paste the full stack trace or compiler output here…"
                  value={errorLog}
                  onChange={(e) => setErrorLog(e.target.value)}
                />
              </div>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={isStreaming || !code.trim()}
              >
                {isStreaming ? "Analyzing…" : "Submit for analysis"}
              </button>
            </form>
          </div>
        </div>

        <div className="chat-column">
          <ReasoningPanel
            reasoningText={reasoningText}
            stage={currentStage}
            isStreaming={isStreaming}
          />
          <div className="card">
            <h2 className="card-title">Agent Status</h2>
            <StatusIndicator
              stage={currentStage}
              isStreaming={isStreaming}
              done={isDone}
              error={hasError}
            />
          </div>
        </div>
      </div>

      <footer className="footer-note">
        CodeFixer AI &mdash; Phase 1 demo. Session: {sessionId ?? "new"}
      </footer>
    </div>
  );
}

function ChatEventMessage({ event }: { event: ChatStreamEvent }) {
  switch (event.type) {
    case "execution_result":
      return <ExecutionResultCard event={event} />;
    case "provider_failover":
      return <FailoverNotice event={event} />;
    case "final_fix":
      return <FinalFixCard event={event} />;
    case "session":
    case "status":
    case "reasoning_token":
    case "done":
      // "session" is consumed by the useEffect above to learn the
      // Gateway-assigned sessionId; the rest are rendered elsewhere
      // (ReasoningPanel / StatusIndicator) or not user-facing on their own.
      return null;
    case "error":
      return (
        <div className="message message--system">
          <span className="message-role">error</span>
          {event.message}
        </div>
      );
    default:
      return null;
  }
}
