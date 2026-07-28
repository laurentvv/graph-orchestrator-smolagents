/** Panneau de saisie : prompt + configuration du run (mode, tools, modèle). */

import { useState } from "react";
import type { RunMode } from "../types";

interface Props {
  onRun: (prompt: string, mode: RunMode, opts?: {
    toolNames?: string[];
    skillName?: string;
    maxSteps?: number;
  }) => void;
  onCancel: () => void;
  running: boolean;
  tools: string[];
  skills: { name: string; description: string }[];
}

const MODES: { value: RunMode; label: string; desc: string }[] = [
  { value: "chat", label: "Chat outillé", desc: "Agent développeur (Python/Node/Web)" },
  { value: "graph", label: "Graphe", desc: "Fan-out → Reduce → Adversaire → Synth" },
  { value: "exploration", label: "Exploration", desc: "Loop-until-dry avec dédup persistante" },
];

export function PromptPanel({ onRun, onCancel, running, tools, skills }: Props) {
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState<RunMode>("chat");
  const [selectedTools, setSelectedTools] = useState<string[]>([]);
  const [skill, setSkill] = useState("coding");

  const toggleTool = (name: string) => {
    setSelectedTools((prev) =>
      prev.includes(name) ? prev.filter((t) => t !== name) : [...prev, name]
    );
  };

  const handleRun = () => {
    if (!prompt.trim() || running) return;
    onRun(prompt, mode, {
      toolNames: selectedTools.length ? selectedTools : undefined,
      skillName: skill,
    });
  };

  return (
    <div className="flex flex-col h-full p-4 gap-4" style={{ background: "var(--bg-1)" }}>
      <div>
        <h2 className="text-lg font-semibold mb-1">Prompt</h2>
        <textarea
          className="w-full rounded-lg p-3 resize-none focus:outline-none focus:ring-1"
          style={{
            background: "var(--bg-2)", color: "var(--text-0)",
            border: "1px solid var(--bg-3)", minHeight: "160px",
          }}
          placeholder="Décris la tâche... ex: 'Calcule les 10 premiers nombres de Fibonacci en Python'"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleRun();
          }}
          disabled={running}
        />
        <p className="text-xs mt-1" style={{ color: "var(--text-1)" }}>
          ⌘/Ctrl+Entrée pour lancer
        </p>
      </div>

      {/* Mode */}
      <div>
        <h3 className="text-sm font-medium mb-2" style={{ color: "var(--text-1)" }}>Mode</h3>
        <div className="flex flex-col gap-1">
          {MODES.map((m) => (
            <button
              key={m.value}
              onClick={() => setMode(m.value)}
              disabled={running}
              className="text-left px-3 py-2 rounded-md transition-colors disabled:opacity-50"
              style={{
                background: mode === m.value ? "var(--accent)" : "var(--bg-2)",
                border: "1px solid var(--bg-3)",
              }}
            >
              <div className="text-sm font-medium">{m.label}</div>
              <div className="text-xs opacity-80">{m.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Outils (mode chat uniquement) */}
      {mode === "chat" && (
        <div>
          <h3 className="text-sm font-medium mb-2" style={{ color: "var(--text-1)" }}>
            Outils {!selectedTools.length && "(tous par défaut)"}
          </h3>
          <div className="flex flex-wrap gap-1">
            {tools.map((t) => (
              <button
                key={t}
                onClick={() => toggleTool(t)}
                disabled={running}
                className="text-xs px-2 py-1 rounded mono transition-colors disabled:opacity-50"
                style={{
                  background: selectedTools.includes(t) ? "var(--accent)" : "var(--bg-2)",
                  border: "1px solid var(--bg-3)",
                }}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Skill (mode chat uniquement) */}
      {mode === "chat" && skills.length > 0 && (
        <div>
          <h3 className="text-sm font-medium mb-2" style={{ color: "var(--text-1)" }}>Skill</h3>
          <select
            value={skill}
            onChange={(e) => setSkill(e.target.value)}
            disabled={running}
            className="w-full px-3 py-2 rounded-md text-sm"
            style={{ background: "var(--bg-2)", color: "var(--text-0)", border: "1px solid var(--bg-3)" }}
          >
            {skills.map((s) => (
              <option key={s.name} value={s.name}>{s.name}</option>
            ))}
          </select>
        </div>
      )}

      {/* Boutons */}
      <div className="mt-auto flex gap-2">
        {running ? (
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2 rounded-md font-medium"
            style={{ background: "var(--err)", color: "#fff" }}
          >
            ■ Arrêter
          </button>
        ) : (
          <button
            onClick={handleRun}
            disabled={!prompt.trim()}
            className="flex-1 px-4 py-2 rounded-md font-medium disabled:opacity-40"
            style={{ background: "var(--accent-2)", color: "#fff" }}
          >
            ▶ Lancer
          </button>
        )}
      </div>
    </div>
  );
}
