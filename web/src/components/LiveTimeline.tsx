/** Timeline live : affiche les étapes de l'agent en temps réel (depuis le WebSocket).

Chaque étape montre : numéro, tool_calls (avec icône), observations (bloc code),
tokens consommés, durée. C'est le composant phare de l'IDE agent.
*/

import type { StepData } from "../types";
import type { RunStatus } from "../hooks/useAgentStream";

interface Props {
  steps: StepData[];
  status: RunStatus;
  statusMessages: string[];
}

/** Icône selon le nom de l'outil appelé. */
function toolIcon(name: string): string {
  if (name.startsWith("python")) return "🐍";
  if (name.startsWith("node")) return "🟢";
  if (name.includes("file") || name.includes("dir") || name.includes("list")) return "📄";
  if (name.includes("search") || name.includes("web")) return "🔍";
  if (name.includes("final")) return "✅";
  return "🔧";
}

export function LiveTimeline({ steps, status, statusMessages }: Props) {
  return (
    <div className="flex flex-col h-full overflow-y-auto p-4 gap-2">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold" style={{ color: "var(--text-1)" }}>
          Timeline
        </h2>
        <StatusBadge status={status} />
      </div>

      {/* Messages de statut */}
      {statusMessages.map((msg, i) => (
        <div key={`s-${i}`} className="text-xs italic px-2" style={{ color: "var(--text-1)" }}>
          ⟳ {msg}
        </div>
      ))}

      {/* Étapes */}
      {steps.map((step, i) => (
        <StepCard key={i} step={step} />
      ))}

      {status === "running" && steps.length === 0 && (
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--text-1)" }}>
          <span className="pulse-dot" style={{ color: "var(--accent-2)" }}>●</span>
          En attente de la première étape...
        </div>
      )}

      {status === "running" && steps.length > 0 && (
        <div className="flex items-center gap-2 text-sm" style={{ color: "var(--accent-2)" }}>
          <span className="pulse-dot">●</span> Exécution en cours...
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: RunStatus }) {
  const map: Record<RunStatus, { label: string; color: string }> = {
    idle: { label: "Prêt", color: "var(--text-1)" },
    running: { label: "En cours", color: "var(--warn)" },
    done: { label: "Terminé", color: "var(--accent-2)" },
    error: { label: "Erreur", color: "var(--err)" },
  };
  const { label, color } = map[status];
  return (
    <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: "var(--bg-2)", color }}>
      {status === "running" && <span className="pulse-dot">● </span>}
      {label}
    </span>
  );
}

function StepCard({ step }: { step: StepData }) {
  const hasError = !!step.error;
  return (
    <div
      className="rounded-md p-3"
      style={{ background: "var(--bg-1)", border: `1px solid ${hasError ? "var(--err)" : "var(--bg-3)"}` }}
    >
      {/* En-tête : numéro + outils + tokens */}
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <span
          className="text-xs font-bold px-1.5 py-0.5 rounded"
          style={{ background: "var(--bg-3)", color: "var(--text-0)" }}
        >
          #{step.step_number}
        </span>
        {step.tool_calls?.map((tc, i) => (
          <span key={i} className="text-xs mono px-1.5 py-0.5 rounded flex items-center gap-1"
            style={{ background: "var(--bg-2)", color: "var(--accent)" }}>
            {toolIcon(tc.name)} {tc.name}
          </span>
        ))}
        {step.duration_s != null && (
          <span className="text-xs ml-auto" style={{ color: "var(--text-1)" }}>
            {step.duration_s}s
          </span>
        )}
        {step.input_tokens != null && (
          <span className="text-xs" style={{ color: "var(--text-1)" }}>
            {(step.input_tokens + (step.output_tokens ?? 0)).toLocaleString()} tok
          </span>
        )}
      </div>

      {/* Arguments des tool calls */}
      {step.tool_calls?.map((tc, i) =>
        tc.arguments && tc.arguments !== "" ? (
          <pre key={`a-${i}`} className="mono text-xs p-2 rounded mb-1 overflow-x-auto"
            style={{ background: "var(--bg-0)", color: "var(--text-1)" }}>
            {tc.arguments.length > 300 ? tc.arguments.slice(0, 300) + "…" : tc.arguments}
          </pre>
        ) : null
      )}

      {/* Code action (CodeAgent) */}
      {step.code_action && (
        <pre className="mono text-xs p-2 rounded mb-1 overflow-x-auto"
          style={{ background: "var(--bg-0)", color: "var(--accent-2)" }}>
          {step.code_action.length > 500 ? step.code_action.slice(0, 500) + "…" : step.code_action}
        </pre>
      )}

      {/* Observations (sortie de l'outil) */}
      {step.observations && (
        <pre className="mono text-xs p-2 rounded overflow-x-auto"
          style={{ background: "var(--bg-0)", color: "var(--text-0)",
                   border: "1px solid var(--bg-3)" }}>
          {step.observations.length > 1000 ? step.observations.slice(0, 1000) + "\n…[tronqué]" : step.observations}
        </pre>
      )}

      {/* Erreur */}
      {step.error && (
        <pre className="mono text-xs p-2 rounded mt-1"
          style={{ background: "rgba(248,81,73,0.1)", color: "var(--err)" }}>
          {step.error}
        </pre>
      )}
    </div>
  );
}
