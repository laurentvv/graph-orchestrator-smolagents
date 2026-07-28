/** Visualiseur du Knowledge Graph : entités, claims, provenance.

Affiche une table compacte des claims avec leur statut (approved/rejected/open),
leur kind (observation/refutation/insight) et leur provenance (source + modèle).
*/

import { useEffect, useState } from "react";
import { getKg } from "../api";
import type { KgSnapshot } from "../types";

const STATUS_COLORS: Record<string, string> = {
  approved: "var(--accent-2)",
  rejected: "var(--err)",
  open: "var(--text-1)",
};

const KIND_ICONS: Record<string, string> = {
  observation: "👁",
  refutation: "⚡",
  insight: "💡",
};

export function KgViewer() {
  const [kg, setKg] = useState<KgSnapshot | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (open) getKg().then(setKg).catch(() => {});
  }, [open]);

  // Refresh auto toutes les 5s si ouvert
  useEffect(() => {
    if (!open) return;
    const id = setInterval(() => getKg().then(setKg).catch(() => {}), 5000);
    return () => clearInterval(id);
  }, [open]);

  return (
    <div className="border-t" style={{ borderColor: "var(--bg-3)" }}>
      <button
        onClick={() => setOpen(!open)}
        className="w-full px-4 py-2 text-sm font-medium flex items-center gap-2"
        style={{ background: "var(--bg-1)", color: "var(--text-1)" }}
      >
        <span>{open ? "▼" : "▶"}</span> Knowledge Graph
        {kg && (
          <span className="text-xs" style={{ color: "var(--text-1)" }}>
            ({kg.entities.length} entités, {kg.claims.length} claims, {kg.edges.length} arêtes)
          </span>
        )}
      </button>

      {open && kg && (
        <div className="p-3 overflow-x-auto" style={{ background: "var(--bg-0)" }}>
          {kg.claims.length === 0 ? (
            <p className="text-xs" style={{ color: "var(--text-1)" }}>
              Graphe vide. Le Knowledge Graph se remplit avec les runs en mode <strong>Graphe</strong> ou <strong>Exploration</strong> (Fan-out → Adversaire → Synth). Les runs en mode Chat ne tracent pas de claims.
            </p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: "var(--text-1)", textAlign: "left" }}>
                  <th className="py-1 pr-2">#</th>
                  <th className="py-1 pr-2">Kind</th>
                  <th className="py-1 pr-2">Entité</th>
                  <th className="py-1 pr-2">Statut</th>
                  <th className="py-1 pr-2">Contenu</th>
                  <th className="py-1 pr-2">Provenance</th>
                </tr>
              </thead>
              <tbody className="mono">
                {kg.claims.map((c) => {
                  const prov = kg.provenance.find((p) => p.claim_id === c.id);
                  return (
                    <tr key={c.id} style={{ borderBottom: "1px solid var(--bg-2)" }}>
                      <td className="py-1 pr-2" style={{ color: "var(--text-1)" }}>{c.id}</td>
                      <td className="py-1 pr-2">{KIND_ICONS[c.kind] || "•"} {c.kind}</td>
                      <td className="py-1 pr-2" style={{ color: "var(--accent)" }}>{c.entity_id}</td>
                      <td className="py-1 pr-2" style={{ color: STATUS_COLORS[c.status] || "var(--text-1)" }}>
                        {c.status}
                      </td>
                      <td className="py-1 pr-2" style={{ maxWidth: "300px", color: "var(--text-0)" }}>
                        {c.content.length > 80 ? c.content.slice(0, 80) + "…" : c.content}
                      </td>
                      <td className="py-1 pr-2" style={{ color: "var(--text-1)" }}>
                        {prov ? `${prov.source}` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
