import type { FinalFixEvent } from "../types";

export default function FinalFixCard({ event }: { event: FinalFixEvent }) {
  return (
    <div className="final-fix">
      <div className="final-fix-header">
        Final Fix ({event.language})
      </div>
      <pre className="final-fix-code">{event.code}</pre>
      <div className="final-fix-explanation">{event.explanation}</div>
    </div>
  );
}
