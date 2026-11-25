// Server-side client for the ContextBoss REST API (packages/contextboss-api).
const BASE = process.env.CONTEXTBOSS_API_URL ?? "http://127.0.0.1:8787";
const KEY = process.env.CONTEXTBOSS_API_KEY ?? "";

export interface Entry {
  id: string;
  content: string;
  namespace: string;
  tags: string[];
  provenance: Record<string, unknown>;
  tier: string;
  pinned: boolean;
  importance: number;
  metadata: Record<string, unknown>;
  version: number;
  created_at: number;
  updated_at: number;
}

export interface Stats {
  entries: number;
  total_tokens: number;
  namespaces: Record<string, number>;
  tiers: Record<string, number>;
}

export interface Inspect {
  entry: Entry;
  tensions: Array<{ kind: string; detail: string; severity: string }>;
  versions: Array<{ version: number; tokens: number; updated_at: number }>;
  similar: Array<{ id: string; score: number; content: string }>;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(KEY ? { Authorization: `Bearer ${KEY}` } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  stats: (namespace?: string) =>
    req<Stats>(`/v1/stats${namespace ? `?namespace=${encodeURIComponent(namespace)}` : ""}`),
  search: (q = "", namespace?: string) => {
    const p = new URLSearchParams({ q: q ?? "", limit: "100" });
    if (namespace) p.set("namespace", namespace);
    return req<Entry[]>(`/v1/contexts?${p}`);
  },
  get: (id: string) => req<Entry>(`/v1/contexts/${id}`),
  inspect: (id: string) => req<Inspect>(`/v1/contexts/${id}/inspect`),
  compact: (id: string, target_tokens: number) =>
    req<Entry>(`/v1/contexts/${id}/compact`, {
      method: "POST",
      body: JSON.stringify({ target_tokens }),
    }),
  remove: (id: string) => req<{ deleted: boolean }>(`/v1/contexts/${id}`, { method: "DELETE" }),
  assemble: (body: {
    query: string;
    budget?: number;
    system?: string;
    task?: string;
    namespace?: string;
  }) => req<{ text: string; tokens: number; entries: string[] }>(`/v1/assemble`, {
    method: "POST",
    body: JSON.stringify(body),
  }),
};
