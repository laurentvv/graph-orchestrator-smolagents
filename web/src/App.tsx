/** App IDE : layout 3 colonnes (prompt | timeline | résultat) + barre de statut + KG.

Inspiré de Cursor/Devin : sombre, dense, monospace pour le code.
*/

import { useEffect, useState } from "react";
import { PromptPanel } from "./components/PromptPanel";
import { LiveTimeline } from "./components/LiveTimeline";
import { ResultPanel } from "./components/ResultPanel";
import { KgViewer } from "./components/KgViewer";
import { useAgentStream } from "./hooks/useAgentStream";
import { getHealth } from "./api";
import type { HealthResponse, RunMode } from "./types";

export default function App() {
  const { state, run, cancel } = useAgentStream();
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => {});
  }, [state.status === "done"]); // refresh après un run

  return (
    <div className="flex flex-col h-screen">
      {/* Barre de titre */}
      <header
        className="flex items-center gap-4 px-4 py-2"
        style={{ background: "var(--bg-1)", borderBottom: "1px solid var(--bg-3)" }}
      >
        <h1 className="text-base font-semibold">
          🕸️ Graph Orchestrator <span style={{ color: "var(--text-1)" }}>— Agent IDE</span>
        </h1>
        <div className="ml-auto flex items-center gap-4 text-xs" style={{ color: "var(--text-1)" }}>
          {health && (
            <>
              <span>
                ● <span style={{ color: health.ollama_reachable ? "var(--accent-2)" : "var(--err)" }}>
                  Ollama {health.ollama_reachable ? "OK" : "KO"}
                </span>
              </span>
              <span>{health.tools_available.length} outils</span>
              <span>{health.skills_available.length} skills</span>
              <span>
                {health.mcp_servers.filter((m) => m.configured).length}/{health.mcp_servers.length} MCP
              </span>
            </>
          )}
        </div>
      </header>

      {/* Layout 3 colonnes */}
      <div className="flex flex-1 overflow-hidden">
        {/* Colonne gauche : prompt + config */}
        <div className="w-80 flex-shrink-0 overflow-y-auto" style={{ borderRight: "1px solid var(--bg-3)" }}>
          <PromptPanel
            onRun={(prompt, mode, opts) => run(prompt, mode as RunMode, opts)}
            onCancel={cancel}
            running={state.status === "running"}
            tools={health?.tools_available ?? []}
            skills={health?.skills_available ?? []}
          />
        </div>

        {/* Colonne centre : timeline live */}
        <div className="flex-1 overflow-hidden" style={{ borderRight: "1px solid var(--bg-3)" }}>
          <LiveTimeline
            steps={state.steps}
            status={state.status}
            statusMessages={state.statusMessages}
          />
        </div>

        {/* Colonne droite : résultat */}
        <div className="w-96 flex-shrink-0 overflow-y-auto" style={{ background: "var(--bg-0)" }}>
          <ResultPanel output={state.finalOutput} error={state.error} />
        </div>
      </div>

      {/* KG viewer repliable */}
      <KgViewer />
    </div>
  );
}
