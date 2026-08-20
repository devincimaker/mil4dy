export function fmtTime(s: number): string {
  if (!Number.isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

/** Whole or one-decimal seconds, e.g. `222s` / `8.4s`. */
export function fmtSeconds(s: number): string {
  if (!Number.isFinite(s) || s < 0) return "0s";
  const tenths = Math.round(s * 10) / 10;
  return Number.isInteger(tenths) ? `${tenths}s` : `${tenths.toFixed(1)}s`;
}

/** Clock + raw second: `3:42 · 222s`. */
export function fmtStamp(s: number): string {
  return `${fmtTime(s)} · ${fmtSeconds(s)}`;
}

export function fmtBpm(bpm: number): string {
  return Number.isInteger(bpm) ? String(bpm) : bpm.toFixed(1);
}

export function prettyType(type: string): string {
  return type.replaceAll("_", " ");
}

export function fmtWhen(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fileTail(path: string): string {
  const parts = path.split(/[\\/]/);
  return parts.filter(Boolean).slice(-3).join("/");
}
