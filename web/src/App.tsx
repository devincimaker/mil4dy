import { useEffect, useMemo, useState } from "react";
import { fetchLibrary, fetchPair, renderPair, trackAudioUrl } from "./api";
import { Player } from "./components/Player";
import { StructureStrip, overlapHint } from "./components/StructureStrip";
import { fmtBpm, fmtStamp, fmtTime, prettyType } from "./format";
import type { PairResponse, Track } from "./types";

type Slot = "out" | "in";

export function App() {
  const [tracks, setTracks] = useState<Track[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [outId, setOutId] = useState<string | null>(null);
  const [inId, setInId] = useState<string | null>(null);
  const [active, setActive] = useState<Slot>("out");
  const [pair, setPair] = useState<PairResponse | null>(null);
  const [pairError, setPairError] = useState<string | null>(null);
  const [pairBusy, setPairBusy] = useState(false);
  const [blendUrl, setBlendUrl] = useState<string | null>(null);
  const [renderBusy, setRenderBusy] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);

  useEffect(() => {
    fetchLibrary()
      .then(setTracks)
      .catch((e: Error) => setLoadError(e.message));
  }, []);

  useEffect(() => {
    setBlendUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setRenderError(null);
  }, [outId, inId]);

  useEffect(() => {
    if (!outId || !inId || outId === inId) {
      setPair(null);
      setPairError(null);
      return;
    }
    let cancelled = false;
    setPairBusy(true);
    setPairError(null);
    fetchPair(outId, inId)
      .then((p) => {
        if (!cancelled) setPair(p);
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setPair(null);
          setPairError(e.message);
        }
      })
      .finally(() => {
        if (!cancelled) setPairBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [outId, inId]);

  const byId = useMemo(() => new Map(tracks.map((t) => [t.id, t])), [tracks]);
  const outgoing = outId ? byId.get(outId) ?? pair?.a : undefined;
  const incoming = inId ? byId.get(inId) ?? pair?.b : undefined;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return tracks;
    return tracks.filter((t) =>
      `${t.artist} ${t.title} ${t.camelot} ${t.genre}`.toLowerCase().includes(q),
    );
  }, [tracks, query]);

  const pick = (id: string) => {
    if (id === outId) {
      setActive("out");
      return;
    }
    if (id === inId) {
      setActive("in");
      return;
    }
    if (active === "out" || !outId) {
      setOutId(id);
      setActive(inId ? "out" : "in");
    } else {
      setInId(id);
      setActive("out");
    }
  };

  const hear = async () => {
    if (!outId || !inId) return;
    setRenderBusy(true);
    setRenderError(null);
    try {
      const url = await renderPair(outId, inId);
      setBlendUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
    } catch (e) {
      setRenderError(e instanceof Error ? e.message : "render failed");
    } finally {
      setRenderBusy(false);
    }
  };

  const swap = () => {
    setOutId(inId);
    setInId(outId);
  };

  return (
    <div className="shell">
      <header className="mast">
        <div className="wordmark">
          <span className="brand">mil4dy</span>
          <span className="edition">pair lab</span>
        </div>
        <p className="lede">
          Two tracks. The planner proposes where they meet. You listen.
        </p>
        <div className="mast-meta">
          {tracks.length ? `${tracks.length} in the crate` : "warming the crate…"}
        </div>
      </header>

      <aside className="crate">
        <label className="search">
          <span className="sr-only">Filter crate</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="filter artist, title, key…"
          />
        </label>
        {loadError && <p className="banner err">{loadError}</p>}
        <ul className="crate-list">
          {filtered.map((t) => {
            const role = t.id === outId ? "out" : t.id === inId ? "in" : null;
            return (
              <li key={t.id}>
                <button
                  type="button"
                  className={`crate-row${role ? ` is-${role}` : ""}`}
                  onClick={() => pick(t.id)}
                >
                  <span className="row-title">
                    <em>{t.artist}</em>
                    <span>{t.title}</span>
                  </span>
                  <span className="row-meta">
                    <span>{fmtBpm(t.bpm)}</span>
                    <span>{t.camelot || "—"}</span>
                    <span>{energyPips(t.energy)}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </aside>

      <main className="stage">
        <div className="decks">
          <Deck
            role="out"
            label="outgoing"
            track={outgoing}
            selected={active === "out"}
            onFocus={() => setActive("out")}
            onClear={() => setOutId(null)}
            decision={pair?.decision}
          />
          <button
            type="button"
            className="swap"
            onClick={swap}
            disabled={!outId && !inId}
            title="Swap decks"
          >
            ⇄
          </button>
          <Deck
            role="in"
            label="incoming"
            track={incoming}
            selected={active === "in"}
            onFocus={() => setActive("in")}
            onClear={() => setInId(null)}
            decision={pair?.decision}
          />
        </div>

        <section className="verdict">
          {!outId || !inId ? (
            <p className="empty">
              Pick an outgoing track from the crate, then an incoming one.
              The next click fills the deck that’s highlighted.
            </p>
          ) : pairBusy ? (
            <p className="empty">reading structure…</p>
          ) : pairError ? (
            <p className="banner err">{pairError}</p>
          ) : pair ? (
            <>
              <div className="verdict-head">
                <h2>{prettyType(pair.decision.type)}</h2>
                <p>
                  {pair.decision.length_bars} bars
                  {pair.decision.fx.length
                    ? ` · ${pair.decision.fx.join(", ")}`
                    : ""}
                </p>
              </div>
              <ul className="reasons">
                {pair.decision.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              <dl className="scores">
                <div>
                  <dt>key fit</dt>
                  <dd>{Math.round(pair.decision.camelot_score * 100)}</dd>
                </div>
                <div>
                  <dt>vocal out / in</dt>
                  <dd>
                    {pct(pair.decision.vocal_out)}
                    <span> / </span>
                    {pct(pair.decision.vocal_in)}
                  </dd>
                </div>
                <div>
                  <dt>leave → arrive</dt>
                  <dd>
                    {pair.decision.out_label}
                    <span> → </span>
                    {pair.decision.in_arrival_label}
                  </dd>
                </div>
                <div>
                  <dt>window</dt>
                  <dd>{fmtTime(pair.decision.window_duration_s)}</dd>
                </div>
              </dl>
              <dl className="cue-board">
                <div>
                  <dt>outgoing</dt>
                  <dd>
                    <span className="cue-pair">
                      <span className="cue-k">mix</span>
                      {fmtStamp(pair.decision.out_start_s)}
                    </span>
                    <span className="cue-pair">
                      <span className="cue-k">send</span>
                      {fmtStamp(pair.decision.out_end_s)}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>incoming</dt>
                  <dd>
                    <span className="cue-pair">
                      <span className="cue-k">mix</span>
                      {fmtStamp(pair.decision.in_start_s)}
                    </span>
                    <span className="cue-pair">
                      <span className="cue-k">send</span>
                      {fmtStamp(pair.decision.in_end_s)}
                    </span>
                  </dd>
                </div>
              </dl>
              <Player
                src={blendUrl}
                busy={renderBusy}
                error={renderError}
                onHear={() => void hear()}
                disabled={!pair}
              />
            </>
          ) : null}
        </section>
      </main>
    </div>
  );
}

function Deck({
  role,
  label,
  track,
  selected,
  onFocus,
  onClear,
  decision,
}: {
  role: Slot;
  label: string;
  track?: Track;
  selected: boolean;
  onFocus: () => void;
  onClear: () => void;
  decision?: PairResponse["decision"];
}) {
  const cue = decision ? overlapHint(role, decision) : null;
  return (
    <article
      className={`deck deck-${role}${selected ? " is-active" : ""}`}
      onClick={onFocus}
    >
      <header>
        <span className="deck-role">{label}</span>
        {track && (
          <button type="button" className="ghost tiny" onClick={onClear}>
            clear
          </button>
        )}
      </header>
      {track ? (
        <>
          <h3>
            <span className="artist">{track.artist}</span>
            <span className="title">{track.title}</span>
          </h3>
          <p className="deck-meta">
            <span>{fmtBpm(track.bpm)} bpm</span>
            <span>
              {track.key} {track.scale} · {track.camelot || "no key"}
            </span>
            <span>{fmtTime(track.duration)}</span>
            {track.genre ? <span>{track.genre}</span> : null}
          </p>
          <StructureStrip
            track={track}
            role={role}
            cueStart={cue?.start}
            cueEnd={cue?.end}
          />
          {cue && (
            <dl className="cue-readout">
              <div>
                <dt>mix</dt>
                <dd title={`${cue.start.toFixed(3)}s`}>{fmtStamp(cue.start)}</dd>
              </div>
              <div>
                <dt>send</dt>
                <dd title={`${cue.end.toFixed(3)}s`}>{fmtStamp(cue.end)}</dd>
              </div>
            </dl>
          )}
          <audio className="preview" controls preload="none" src={trackAudioUrl(track.id)} />
        </>
      ) : (
        <p className="deck-empty">
          {selected ? "click a track in the crate" : "click here, then pick a track"}
        </p>
      )}
    </article>
  );
}

function energyPips(e: number): string {
  const n = Math.max(1, Math.min(5, Math.round(e * 5)));
  return "·".repeat(n);
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}
