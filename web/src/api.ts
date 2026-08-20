import type { HistoryTake, PairResponse, RenderMeta, Track, Verdict } from "./types";

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

export function renderPair(a: string, b: string): Promise<RenderMeta> {
  return fetch("/api/pair/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ a, b }),
  }).then((r) => json<RenderMeta>(r));
}

export function renderMix(a: string, b: string, takeId?: string | null): Promise<RenderMeta> {
  return fetch("/api/pair/mix", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ a, b, take_id: takeId ?? null }),
  }).then((r) => json<RenderMeta>(r));
}

export function fetchHistory(): Promise<HistoryTake[]> {
  return fetch("/api/history").then((r) => json<HistoryTake[]>(r));
}

export function fetchFavorites(): Promise<HistoryTake[]> {
  return fetch("/api/favorites").then((r) => json<HistoryTake[]>(r));
}

export function setFavorite(takeId: string, favorite: boolean): Promise<HistoryTake> {
  return fetch("/api/favorites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ take_id: takeId, favorite }),
  }).then((r) => json<HistoryTake>(r));
}

export function setVerdict(
  takeId: string,
  verdict: Verdict,
  note?: string | null,
): Promise<HistoryTake> {
  const body: { verdict: Verdict; note?: string | null } = { verdict };
  if (note !== undefined) body.note = note;
  return fetch(`/api/history/${takeId}/verdict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => json<HistoryTake>(r));
}

export function setTakeNote(takeId: string, note: string | null): Promise<HistoryTake> {
  return fetch(`/api/history/${takeId}/note`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  }).then((r) => json<HistoryTake>(r));
}

export function deleteTake(id: string): Promise<void> {
  return fetch(`/api/history/${id}`, { method: "DELETE" }).then(async (r) => {
    if (!r.ok) {
      let detail = r.statusText;
      try {
        const body = (await r.json()) as { detail?: string };
        if (body.detail) detail = body.detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
  });
}

export function trackAudioUrl(id: string): string {
  return `/api/tracks/${id}/audio`;
}

export function triggerDownload(url: string, filename: string): void {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
