import type { PairResponse, Track } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export function fetchLibrary(): Promise<Track[]> {
  return fetch("/api/library").then((r) => json<Track[]>(r));
}

export function fetchPair(a: string, b: string): Promise<PairResponse> {
  const q = new URLSearchParams({ a, b });
  return fetch(`/api/pair?${q}`).then((r) => json<PairResponse>(r));
}

export async function renderPair(a: string, b: string): Promise<string> {
  const res = await fetch("/api/pair/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ a, b }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export function trackAudioUrl(id: string): string {
  return `/api/tracks/${id}/audio`;
}
