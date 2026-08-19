import { useEffect, useMemo, useRef, useState } from "react";
import {
  deleteTake,
  fetchHistory,
  fetchLibrary,
  fetchPair,
  renderMix,
  renderPair,
  setFavorite,
  trackAudioUrl,
  triggerDownload,
} from "./api";
import { History } from "./components/History";
import { KeepBar } from "./components/KeepBar";
import { Player } from "./components/Player";
import { StructureStrip, overlapHint } from "./components/StructureStrip";
import { fmtBpm, fmtTime, gridWarnLine, prettyType, pulseWarnLine } from "./format";
import type { HistoryTake, PairResponse, Track } from "./types";

type Slot = "out" | "in";

interface Take {
  id: string;
  favorite: boolean;
  blendUrl: string;
  blendFilename: string;
  mixUrl: string | null;
  mixFilename: string | null;
}

interface Listening {
  src: string;
  takeId: string | null;
  caption: string | null;
}

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
  const [take, setTake] = useState<Take | null>(null);
  const [listening, setListening] = useState<Listening | null>(null);
  const [renderBusy, setRenderBusy] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryTake[]>([]);
  const [keepError, setKeepError] = useState<string | null>(null);
  const [mixBusy, setMixBusy] = useState(false);
  const [mixElapsed, setMixElapsed] = useState(0);
  const fromHistoryRef = useRef(false);
  const takeRef = useRef<Take | null>(null);
  takeRef.current = take;

  useEffect(() => {
    fetchLibrary()
      .then(setTracks)
      .catch((e: Error) => setLoadError(e.message));
    fetchHistory()
      .then(setHistory)
      .catch(() => setHistory([]));
  }, []);

  useEffect(() => {
    if (fromHistoryRef.current) {
      fromHistoryRef.current = false;
      return;
    }
    setTake(null);
    setListening(null);
    setRenderError(null);
    setKeepError(null);
  }, [outId, inId]);

  useEffect(() => {
    if (!mixBusy) {
      setMixElapsed(0);
      return;
    }
    const started = Date.now();
    const id = window.setInterval(() => {
      setMixElapsed(Math.floor((Date.now() - started) / 1000));
    }, 500);
    return () => window.clearInterval(id);
  }, [mixBusy]);

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

  const refreshHistory = () =>
    fetchHistory()
      .then(setHistory)
      .catch((e: Error) => setKeepError(e.message));

  const hear = async () => {
    if (!outId || !inId) return;
    setRenderBusy(true);
    setRenderError(null);
    setKeepError(null);
    try {
      const meta = await renderPair(outId, inId);
      const next: Take = {
        id: meta.take_id,
        favorite: meta.favorite,
        blendUrl: meta.url,
        blendFilename: meta.filename,
        mixUrl: null,
        mixFilename: null,
      };
      setTake(next);
      setListening({ src: meta.url, takeId: meta.take_id, caption: null });
      await refreshHistory();
    } catch (e) {
      setRenderError(e instanceof Error ? e.message : "render failed");
    } finally {
      setRenderBusy(false);
    }
  };

  const favoriteTake = async () => {
    const current = takeRef.current;
    if (!current) return;
    setKeepError(null);
    try {
      const rec = await setFavorite(current.id, true);
      setTake({ ...current, favorite: rec.favorite });
      await refreshHistory();
    } catch (e) {
      setKeepError(e instanceof Error ? e.message : "could not favorite");
    }
  };

  const unfavoriteTake = async () => {
    const current = takeRef.current;
    if (!current) return;
    setKeepError(null);
    try {
      const rec = await setFavorite(current.id, false);
      setTake({ ...current, favorite: rec.favorite });
      await refreshHistory();
    } catch (e) {
      setKeepError(e instanceof Error ? e.message : "could not unfavorite");
    }
  };

  const downloadBlend = () => {
    const current = takeRef.current;
    if (!current) return;
    triggerDownload(
      current.blendUrl.includes("?") ? current.blendUrl : `${current.blendUrl}?download=1`,
      current.blendFilename,
    );
  };

  const downloadMix = async () => {
    if (!outId || !inId) return;
    setKeepError(null);
    const current = takeRef.current;
    if (current?.mixUrl && current.mixFilename) {
      triggerDownload(
        current.mixUrl.includes("?") ? current.mixUrl : `${current.mixUrl}?download=1`,
        current.mixFilename,
      );
      return;
    }
    setMixBusy(true);
    try {
      const meta = await renderMix(outId, inId, current?.id);
      const latest = takeRef.current;
      if (latest) {
        setTake({
          ...latest,
          id: meta.take_id,
          mixUrl: meta.url,
          mixFilename: meta.filename,
        });
      }
      await refreshHistory();
      triggerDownload(meta.download_url, meta.filename);
    } catch (e) {
      setKeepError(e instanceof Error ? e.message : "mix render failed");
    } finally {
      setMixBusy(false);
    }
  };

  const playTake = (item: HistoryTake) => {
    fromHistoryRef.current = true;
    setOutId(item.outgoing.id);
    setInId(item.incoming.id);
    const src = item.blend_url ?? item.mix_url;
    setTake({
      id: item.id,
      favorite: item.favorite,
      blendUrl: item.blend_url ?? item.mix_url ?? "",
      blendFilename: item.blend_filename ?? item.mix_filename ?? item.id,
      mixUrl: item.mix_url,
      mixFilename: item.mix_filename,
    });
    setListening({
      src: src ?? "",
      takeId: item.id,
      caption: `playing saved file · ${item.blend_filename ?? item.mix_filename ?? item.id}`,
    });
    setRenderError(null);
    setKeepError(null);
  };

  const toggleFavorite = async (item: HistoryTake) => {
    setKeepError(null);
    try {
      const rec = await setFavorite(item.id, !item.favorite);
      if (takeRef.current?.id === rec.id) {
        setTake({ ...takeRef.current, favorite: rec.favorite });
      }
      await refreshHistory();
    } catch (e) {
      setKeepError(e instanceof Error ? e.message : "could not update favorite");
    }
  };

  const removeTake = async (item: HistoryTake) => {
    setKeepError(null);
    try {
      await deleteTake(item.id);
      if (takeRef.current?.id === item.id) setTake(null);
      if (listening?.takeId === item.id) setListening(null);
      await refreshHistory();
    } catch (e) {
      setKeepError(e instanceof Error ? e.message : "could not remove");
    }
  };

  const downloadHistoryBlend = (item: HistoryTake) => {
    if (!item.blend_download_url || !item.blend_filename) return;
    triggerDownload(item.blend_download_url, item.blend_filename);
  };

  const downloadHistoryMix = (item: HistoryTake) => {
    if (!item.mix_download_url || !item.mix_filename) return;
    triggerDownload(item.mix_download_url, item.mix_filename);
  };

  const swap = () => {
    setOutId(inId);
    setInId(outId);
  };

  const favoriteCount = history.filter((t) => t.favorite).length;

  return (
    <div className="shell">
      <header className="mast">
        <div className="wordmark">
          <span className="brand">mil4dy</span>
          <span className="edition">pair lab</span>
        </div>
        <p className="lede">
          Two tracks. Every Hear is saved. Star the ones that work.
        </p>
        <div className="mast-meta">
          {tracks.length ? `${tracks.length} in the crate` : "warming the crate…"}
          {history.length ? ` · ${history.length} generated` : ""}
          {favoriteCount
            ? ` · ${favoriteCount} favorite${favoriteCount === 1 ? "" : "s"}`
            : ""}
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
          ) : pairBusy && !pair && !listening ? (
            <p className="empty">reading structure…</p>
          ) : pairError && !pair ? (
            <p className="banner err">{pairError}</p>
          ) : pair || listening ? (
            <>
              {pairBusy && !pair && <p className="empty">reading structure…</p>}
              {pair ? (
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
              </>
              ) : null}
              <Player
                src={listening?.src ?? null}
                busy={renderBusy}
                error={renderError}
                onHear={() => void hear()}
                disabled={!pair}
                caption={listening?.caption}
                mixStart={pair?.decision.blend_start_s}
                mixEnd={pair?.decision.blend_end_s}
              />

              <KeepBar
                canKeep={!!take}
                favorited={!!take?.favorite}
                mixBusy={mixBusy}
                mixElapsed={mixElapsed}
                busy={renderBusy}
                onFavorite={() => void favoriteTake()}
                onUnfavorite={() => void unfavoriteTake()}
                onDownloadBlend={downloadBlend}
                onDownloadMix={() => void downloadMix()}
              />
              {keepError && <p className="player-error">{keepError}</p>}
              {pair ? (
              <>
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
                      {fmtTime(pair.decision.out_start_s)}
                    </span>
                    <span className="cue-pair">
                      <span className="cue-k">send</span>
                      {fmtTime(pair.decision.out_end_s)}
                    </span>
                    {pair.decision.out_grid_ok ? null : (
                      <span className="grid-warn">
                        {gridWarnLine(
                          pair.decision.length_bars,
                          pair.decision.out_index_span_s,
                          pair.decision.window_expected_s,
                        )}
                      </span>
                    )}
                    {pulseWarnLine(pair.decision.out_pulse_shift_s) ? (
                      <span className="grid-warn">
                        {pulseWarnLine(pair.decision.out_pulse_shift_s)}
                      </span>
                    ) : null}
                  </dd>
                </div>
                <div>
                  <dt>incoming</dt>
                  <dd>
                    <span className="cue-pair">
                      <span className="cue-k">mix</span>
                      {fmtTime(pair.decision.in_start_s)}
                    </span>
                    <span className="cue-pair">
                      <span className="cue-k">send</span>
                      {fmtTime(pair.decision.in_end_s)}
                    </span>
                    {pair.decision.in_grid_ok ? null : (
                      <span className="grid-warn">
                        {gridWarnLine(
                          pair.decision.length_bars,
                          pair.decision.in_index_span_s,
                          pair.decision.window_expected_s,
                        )}
                      </span>
                    )}
                    {pulseWarnLine(pair.decision.in_pulse_shift_s) ? (
                      <span className="grid-warn">
                        {pulseWarnLine(pair.decision.in_pulse_shift_s)}
                      </span>
                    ) : null}
                  </dd>
                </div>
              </dl>
              </>
              ) : null}
            </>
          ) : null}
        </section>
      </main>

      <History
        takes={history}
        playingId={listening?.takeId ?? null}
        onPlay={playTake}
        onToggleFavorite={(item) => void toggleFavorite(item)}
        onDownloadBlend={downloadHistoryBlend}
        onDownloadMix={downloadHistoryMix}
        onRemove={(item) => void removeTake(item)}
      />
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
            <>
              <dl className="cue-readout">
                <div>
                  <dt>mix</dt>
                  <dd>{fmtTime(cue.start)}</dd>
                </div>
                <div>
                  <dt>send</dt>
                  <dd>{fmtTime(cue.end)}</dd>
                </div>
              </dl>
              {decision && gridOff(role, decision) && (
                <p className="grid-warn">
                  {gridWarnLine(
                    decision.length_bars,
                    role === "out"
                      ? decision.out_index_span_s
                      : decision.in_index_span_s,
                    decision.window_expected_s,
                  )}
                </p>
              )}
              {decision && pulseWarnLine(role === "out" ? decision.out_pulse_shift_s : decision.in_pulse_shift_s) && (
                <p className="grid-warn">
                  {pulseWarnLine(role === "out" ? decision.out_pulse_shift_s : decision.in_pulse_shift_s)}
                </p>
              )}
            </>
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

function gridOff(role: Slot, decision?: PairResponse["decision"]): boolean {
  if (!decision) return false;
  return role === "out" ? !decision.out_grid_ok : !decision.in_grid_ok;
}

function energyPips(e: number): string {
  const n = Math.max(1, Math.min(5, Math.round(e * 5)));
  return "·".repeat(n);
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}
