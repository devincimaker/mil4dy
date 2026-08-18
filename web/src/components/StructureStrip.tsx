import type { Decision, Track } from "../types";

interface Props {
  track: Track;
  role: "out" | "in";
  cueStart?: number;
  cueEnd?: number;
}

export function StructureStrip({ track, role, cueStart, cueEnd }: Props) {
  const dur = Math.max(track.duration, 1);
  const segs = track.segments.length
    ? track.segments
    : [{
        label: "verse" as const,
        start: 0,
        end: dur,
        energy: track.energy,
        vocal_likelihood: 0,
        bass_ratio: 0,
        confidence: 0.2,
      }];

  const hasCue = cueStart != null && cueEnd != null && cueEnd > cueStart;

  return (
    <div className={`strip strip-${role}`}>
      <div className="strip-track" role="img" aria-label={`${track.title} structure`}>
        {segs.map((s, i) => {
          const left = (s.start / dur) * 100;
          const width = Math.max(((s.end - s.start) / dur) * 100, 0.4);
          const wide = width > 7;
          return (
            <div
              key={`${s.label}-${i}`}
              className={`seg seg-${s.label}`}
              style={{ left: `${left}%`, width: `${width}%` }}
              title={`${s.label} · ${s.start.toFixed(0)}s–${s.end.toFixed(0)}s · voc ${Math.round(s.vocal_likelihood * 100)}%`}
            >
              {wide ? s.label : ""}
            </div>
          );
        })}
        {hasCue && (
          <div
            className="cue-window"
            style={{
              left: `${(cueStart / dur) * 100}%`,
              width: `${((cueEnd - cueStart) / dur) * 100}%`,
            }}
          />
        )}
      </div>
      <div className="strip-axis">
        <span>0:00</span>
        <span>{axisMid(dur)}</span>
        <span>{axisEnd(dur)}</span>
      </div>
    </div>
  );
}

function axisMid(dur: number): string {
  const m = Math.floor(dur / 2 / 60);
  const s = Math.floor((dur / 2) % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function axisEnd(dur: number): string {
  const m = Math.floor(dur / 60);
  const s = Math.floor(dur % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function overlapHint(role: "out" | "in", d: Decision): { start: number; end: number } {
  return role === "out"
    ? { start: d.out_start_s, end: d.out_end_s }
    : { start: d.in_start_s, end: d.in_end_s };
}
