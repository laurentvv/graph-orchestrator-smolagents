/** Hook React : lance un run et streame les événements via WebSocket.

Gère : connexion WS, parsing des événements, accumulateur d'état (steps + résultat),
reconnexion, erreurs, statut (idle/running/done/error).
*/

import { useCallback, useRef, useState } from "react";
import { cancelRun, startRun, wsRunUrl } from "../api";
import type { RunEvent, RunMode, StepData } from "../types";

export type RunStatus = "idle" | "running" | "done" | "error";

export interface AgentState {
  status: RunStatus;
  steps: StepData[];
  finalOutput: string | null;
  error: string | null;
  statusMessages: string[];
}

const INITIAL: AgentState = {
  status: "idle",
  steps: [],
  finalOutput: null,
  error: null,
  statusMessages: [],
};

export function useAgentStream() {
  const [state, setState] = useState<AgentState>(INITIAL);
  const wsRef = useRef<WebSocket | null>(null);
  const runIdRef = useRef<string | null>(null);

  const reset = useCallback(() => {
    setState(INITIAL);
  }, []);

  const run = useCallback(
    async (prompt: string, mode: RunMode, opts?: {
      modelId?: string;
      toolNames?: string[];
      skillName?: string;
      maxSteps?: number;
    }) => {
      // Reset
      setState({ ...INITIAL, status: "running" });

      try {
        // 1. Lance le run côté backend
        const { run_id } = await startRun({
          prompt,
          mode,
          model_id: opts?.modelId,
          tool_names: opts?.toolNames,
          skill_name: opts?.skillName,
          max_steps: opts?.maxSteps ?? 20,
        });
        runIdRef.current = run_id;

        // 2. Connecte le WebSocket pour le streaming live
        const ws = new WebSocket(wsRunUrl(run_id));
        wsRef.current = ws;

        ws.onmessage = (ev) => {
          try {
            const event: RunEvent = JSON.parse(ev.data);
            setState((prev) => {
              switch (event.type) {
                case "step": {
                  const step = event.data as unknown as StepData;
                  return { ...prev, steps: [...prev.steps, step] };
                }
                case "final": {
                  // Normalise en string (le backend peut envoyer un objet ou une string)
                  let output = event.data.output;
                  if (output != null && typeof output !== "string") {
                    try {
                      output = JSON.stringify(output, null, 2);
                    } catch {
                      output = String(output);
                    }
                  }
                  return { ...prev, finalOutput: output as string | null, status: "done" };
                }
                case "status": {
                  const msg = (event.data.message as string) ?? "";
                  const done = event.data.done as boolean;
                  if (done) {
                    return { ...prev, status: prev.status === "error" ? "error" : "done" };
                  }
                  return { ...prev, statusMessages: [...prev.statusMessages, msg] };
                }
                case "error": {
                  return {
                    ...prev,
                    error: (event.data.message as string) ?? "Erreur inconnue",
                    status: "error",
                  };
                }
                default:
                  return prev;
              }
            });
          } catch {
            /* ignore parse errors */
          }
        };

        ws.onerror = () => {
          setState((prev) => ({ ...prev, error: "Connexion WebSocket perdue", status: "error" }));
        };

        ws.onclose = () => {
          setState((prev) => {
            if (prev.status === "running") {
              return { ...prev, status: "done" };
            }
            return prev;
          });
        };
      } catch (e) {
        setState({
          ...INITIAL,
          status: "error",
          error: e instanceof Error ? e.message : String(e),
        });
      }
    },
    []
  );

  const cancel = useCallback(async () => {
    // 1. Demande l'annulation côté backend (tue la tâche)
    if (runIdRef.current) {
      try {
        await cancelRun(runIdRef.current);
      } catch {
        /* ignore si déjà terminé */
      }
    }
    // 2. Ferme le WS côté client
    wsRef.current?.close();
    setState((prev) => ({ ...prev, status: "idle" }));
  }, []);

  return { state, run, reset, cancel };
}
