import type { ProviderFailoverEvent } from "../types";

/** US-04: transparent notice when the Orchestrator fails over LLM providers. */
export default function FailoverNotice({
  event,
}: {
  event: ProviderFailoverEvent;
}) {
  return (
    <div className="failover-notice">
      Provider failover: <strong>{event.from}</strong> &rarr;{" "}
      <strong>{event.to}</strong> ({event.reason})
    </div>
  );
}
