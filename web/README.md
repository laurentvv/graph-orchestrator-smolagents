# Graph Orchestrator — Web IDE

Interface React (IDE agent sombre) pour le backend `agent_server/`.

## Développement

```bash
# 1. Démarrer le backend FastAPI (depuis la racine du projet)
uv run uvicorn agent_server.app:app --host 127.0.0.1 --port 8000

# 2. Démarrer le frontend (depuis web/)
cd web
npm install
npm run dev
```

L'UI est servie sur http://localhost:5173. Le proxy Vite route `/api` et `/ws`
vers le backend (port 8000).

## Build production

```bash
npm run build   # génère web/dist/ (servable statiquement)
```

## Structure

- `src/App.tsx` — layout IDE 3 colonnes (prompt | timeline | résultat) + KG
- `src/components/PromptPanel.tsx` — saisie + config (mode, outils, skill)
- `src/components/LiveTimeline.tsx` — timeline temps réel des étapes (WebSocket)
- `src/components/ResultPanel.tsx` — résultat final formaté
- `src/components/KgViewer.tsx` — visualisation du Knowledge Graph
- `src/hooks/useAgentStream.ts` — hook WebSocket (streaming, accumulateur d'état)
- `src/api.ts` — client HTTP vers le backend
