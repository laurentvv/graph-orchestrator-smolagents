/** Client HTTP vers le backend FastAPI. */

import type { HealthResponse, KgSnapshot, RunRequest, RunResponse } from "./types";

const BASE = "/api";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
  return resp.json() as Promise<T>;
}

export function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>(`${BASE}/health`);
}

export function getTools(): Promise<{ tools: string[] }> {
  return fetchJson(`${BASE}/tools`);
}

export function getSkills(): Promise<{ skills: { name: string; description: string }[] }> {
  return fetchJson(`${BASE}/skills`);
}

export function getKg(): Promise<KgSnapshot> {
  return fetchJson<KgSnapshot>(`${BASE}/kg`);
}

export function startRun(req: RunRequest): Promise<RunResponse> {
  return fetchJson<RunResponse>(`${BASE}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

/** Construit l'URL WebSocket pour un run (utilise le proxy Vite en dev). */
export function wsRunUrl(runId: string): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  // En dev, le proxy Vite route /ws vers le backend ; en prod, même origine.
  return `${proto}//${location.host}/ws/run/${runId}`;
}
