export function fmtTime(s: number): string {
  if (!Number.isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

/** One-decimal seconds for grid warnings, e.g. `23.6s` / `30.7s`. */
export function fmtSeconds(s: number): string {
  if (!Number.isFinite(s) || s < 0) return "0s";
  const tenths = Math.round(s * 10) / 10;
  return Number.isInteger(tenths) ? `${tenths}s` : `${tenths.toFixed(1)}s`;
}

export function gridWarnLine(
  bars: number,
  detectedSpan: number,
  expectedSpan: number,
): string {
  return `${bars} bars · ${fmtSeconds(detectedSpan)} (expected ${fmtSeconds(expectedSpan)}) — grid looks off`;
}

export function pulseWarnLine(shiftS: number): string | null {
  if (!Number.isFinite(shiftS) || Math.abs(shiftS) < 0.1) return null;
  const ms = Math.round(Math.abs(shiftS) * 1000);
  return `grid was ${ms}ms off the kick — locked the pulse`;
}

export function fmtBpm(bpm: number): string {
  return Number.isInteger(bpm) ? String(bpm) : bpm.toFixed(1);
}

export function prettyType(type: string): string {
  return type.replaceAll("_", " ");
}
