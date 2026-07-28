/** Panneau de résultat : affiche le final_output formaté. */

interface Props {
  output: string | null;
  error: string | null;
}

export function ResultPanel({ output, error }: Props) {
  if (error) {
    return (
      <div className="p-4">
        <h2 className="text-sm font-semibold mb-2" style={{ color: "var(--err)" }}>Erreur</h2>
        <pre className="mono text-xs p-3 rounded" style={{ background: "rgba(248,81,73,0.1)", color: "var(--err)" }}>
          {error}
        </pre>
      </div>
    );
  }

  if (!output) {
    return (
      <div className="p-4 text-sm" style={{ color: "var(--text-1)" }}>
        Le résultat apparaîtra ici une fois le run terminé.
      </div>
    );
  }

  // Tente de pretty-print si c'est du JSON, sinon affiche tel quel
  let display = output;
  try {
    const parsed = JSON.parse(output);
    display = JSON.stringify(parsed, null, 2);
  } catch {
    /* pas du JSON, on garde tel quel */
  }

  return (
    <div className="p-4 flex flex-col h-full">
      <h2 className="text-sm font-semibold mb-2" style={{ color: "var(--accent-2)" }}>
        ✓ Résultat
      </h2>
      <pre className="mono text-sm p-3 rounded overflow-auto flex-1"
        style={{ background: "var(--bg-1)", color: "var(--text-0)", border: "1px solid var(--bg-3)" }}>
        {display}
      </pre>
    </div>
  );
}
