import { useState } from "react";
import type { AgentStage } from "../types";

interface ReasoningPanelProps {
  reasoningText: string;
  stage: AgentStage | null;
  isStreaming: boolean;
}

const STAGE_LABELS: Record<AgentStage, string> = {
  routing: "Routing",
  reasoning: "Reasoning",
  executing: "Executing",
  self_correcting: "Self-correcting",
  finalizing: "Finalizing",
};

/**
 * US-02: "a dedicated, collapsible panel titled 'Agent Reasoning Process',
 * formatted according to the NBP color palette" — shows streamed
 * reasoning_token events live as they arrive.
 */
export default function ReasoningPanel({
  reasoningText,
  stage,
  isStreaming,
}: ReasoningPanelProps) {
  const [open, setOpen] = useState(true);

  return (
    <section className="reasoning-panel">
      <button
        type="button"
        className="reasoning-panel-header"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
      >
        <span className="reasoning-panel-title">
          <span
            className={`reasoning-panel-chevron${open ? " reasoning-panel-chevron--open" : ""}`}
            aria-hidden="true"
          >
            &#9656;
          </span>
          Agent Reasoning Process
        </span>
        {stage && (
          <StatusIndicator stage={stage} isStreaming={isStreaming} />
        )}
      </button>
      {open && (
        <div className="reasoning-panel-body">
          {reasoningText.length > 0 ? (
            reasoningText
          ) : (
            <span className="reasoning-panel-empty">
              No reasoning tokens yet — submit code to begin.
            </span>
          )}
        </div>
      )}
    </section>
  );
}

export function StatusIndicator({
  stage,
  isStreaming,
  done,
  error,
}: {
  stage: AgentStage | null;
  isStreaming: boolean;
  done?: boolean;
  error?: boolean;
}) {
  let dotClass = "status-dot";
  let label = stage ? STAGE_LABELS[stage] : "Idle";

  if (error) {
    dotClass += " status-dot--error";
    label = "Error";
  } else if (done) {
    dotClass += " status-dot--done";
    label = "Done";
  } else if (!isStreaming) {
    dotClass += " status-dot--done";
  }

  return (
    <span className="status-indicator">
      <span className={dotClass} aria-hidden="true" />
      {label}
    </span>
  );
}
