import type { ExecutionResultEvent } from "../types";

/**
 * US-03: "The compilation or unit test output (success/failure status) is
 * returned to the chat interface as system metadata." exitCode 0 = success.
 */
export default function ExecutionResultCard({
  event,
}: {
  event: ExecutionResultEvent;
}) {
  const success = event.exitCode === 0;
  return (
    <div className="execution-result">
      <div
        className={`execution-result-header ${
          success
            ? "execution-result-header--success"
            : "execution-result-header--failure"
        }`}
      >
        <span>{success ? "Execution succeeded" : "Execution failed"}</span>
        <span>exit code {event.exitCode}</span>
      </div>
      <div className="execution-result-body">
        <div className="execution-result-meta">
          <span>language: {event.language}</span>
          <span>duration: {event.durationMs} ms</span>
        </div>
        {event.stdout && (
          <>
            <strong>stdout</strong>
            <pre className="execution-result-stream">{event.stdout}</pre>
          </>
        )}
        {event.stderr && (
          <>
            <strong>stderr</strong>
            <pre className="execution-result-stream">{event.stderr}</pre>
          </>
        )}
      </div>
    </div>
  );
}
