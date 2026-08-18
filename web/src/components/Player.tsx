import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { fmtTime } from "../format";

interface Props {
  src: string | null;
  busy: boolean;
  error: string | null;
  onHear: () => void;
  disabled: boolean;
}

export function Player({ src, busy, error, onHear, disabled }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [t, setT] = useState(0);
  const [dur, setDur] = useState(0);

  useEffect(() => {
    setPlaying(false);
    setT(0);
    setDur(0);
  }, [src]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !src) return;
    const onTime = () => setT(el.currentTime);
    const onMeta = () => setDur(el.duration || 0);
    const onEnd = () => setPlaying(false);
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("loadedmetadata", onMeta);
    el.addEventListener("ended", onEnd);
    void el.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
    return () => {
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("loadedmetadata", onMeta);
      el.removeEventListener("ended", onEnd);
    };
  }, [src]);

  const toggle = () => {
    const el = audioRef.current;
    if (!el) return;
    if (el.paused) {
      void el.play();
      setPlaying(true);
    } else {
      el.pause();
      setPlaying(false);
    }
  };

  const seek = (e: ChangeEvent<HTMLInputElement>) => {
    const el = audioRef.current;
    if (!el) return;
    el.currentTime = Number(e.target.value);
    setT(el.currentTime);
  };

  return (
    <div className="player">
      <audio ref={audioRef} src={src ?? undefined} preload="auto" />
      {!src ? (
        <button
          type="button"
          className="hear"
          onClick={onHear}
          disabled={disabled || busy}
        >
          {busy ? "stretching the overlap…" : "Hear the blend"}
        </button>
      ) : (
        <div className="transport">
          <button type="button" className="play" onClick={toggle} aria-label={playing ? "Pause" : "Play"}>
            {playing ? "pause" : "play"}
          </button>
          <span className="clock">{fmtTime(t)}</span>
          <input
            className="scrub"
            type="range"
            min={0}
            max={dur || 0}
            step={0.05}
            value={t}
            onChange={seek}
            aria-label="Position"
          />
          <span className="clock">{fmtTime(dur)}</span>
          <button type="button" className="ghost" onClick={onHear} disabled={busy}>
            {busy ? "rendering…" : "render again"}
          </button>
        </div>
      )}
      {error && <p className="player-error">{error}</p>}
    </div>
  );
}
