import { useMemo, useState } from "react";
import { fileTail, fmtWhen, prettyType } from "../format";
import type { HistoryTake } from "../types";

interface Props {
  takes: HistoryTake[];
  playingId: string | null;
  onPlay: (take: HistoryTake) => void;
  onToggleFavorite: (take: HistoryTake) => void;
  onDownloadBlend: (take: HistoryTake) => void;
  onDownloadMix: (take: HistoryTake) => void;
  onRemove: (take: HistoryTake) => void;
}

export function History({
  takes,
  playingId,
  onPlay,
  onToggleFavorite,
  onDownloadBlend,
  onDownloadMix,
  onRemove,
}: Props) {
  const [filter, setFilter] = useState<"all" | "favorites">("all");
  const starred = useMemo(() => takes.filter((t) => t.favorite), [takes]);
  const shown = filter === "favorites" ? starred : takes;

  return (
    <aside className="kept">
      <header className="kept-head">
        <div>
          <h2>Generated mixes</h2>
          <p>Every Hear is saved. Star the ones that worked.</p>
        </div>
        <span className="kept-count">
          {takes.length ? `${takes.length} saved` : "none yet"}
          {starred.length ? ` · ${starred.length} favorite${starred.length === 1 ? "" : "s"}` : ""}
        </span>
      </header>
      {takes.length > 0 && (
        <div className="kept-filter" role="tablist" aria-label="History filter">
          <button
            type="button"
            role="tab"
            aria-selected={filter === "all"}
            className={filter === "all" ? "is-on" : ""}
            onClick={() => setFilter("all")}
          >
            All
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={filter === "favorites"}
            className={filter === "favorites" ? "is-on" : ""}
            onClick={() => setFilter("favorites")}
          >
            Favorites
          </button>
        </div>
      )}
      {takes.length === 0 ? (
        <p className="kept-empty">No generated mixes yet. Hear a blend — it stays here.</p>
      ) : shown.length === 0 ? (
        <p className="kept-empty">Nothing favorited yet. Star a take that worked.</p>
      ) : (
        <ul className="kept-list">
          {shown.map((take, i) => {
            const active = take.id === playingId;
            const latest = filter === "all" && i === 0;
            return (
              <li
                key={take.id}
                className={`kept-item${active ? " is-playing" : ""}${take.favorite ? " is-kept" : ""}`}
              >
                <button
                  type="button"
                  className={`star${take.favorite ? " is-on" : ""}`}
                  onClick={() => onToggleFavorite(take)}
                  aria-pressed={take.favorite}
                  aria-label={take.favorite ? "Unfavorite" : "Favorite"}
                  title={take.favorite ? "Unfavorite" : "Favorite"}
                >
                  {take.favorite ? "★" : "☆"}
                </button>
                <button type="button" className="kept-main" onClick={() => onPlay(take)}>
                  <span className="kept-pair">
                    <span className="kept-leg is-out">
                      <em>{take.outgoing.artist}</em>
                      <span>{take.outgoing.title}</span>
                    </span>
                    <span className="kept-arrow" aria-hidden>
                      →
                    </span>
                    <span className="kept-leg is-in">
                      <em>{take.incoming.artist}</em>
                      <span>{take.incoming.title}</span>
                    </span>
                    {latest && <span className="kept-latest">latest</span>}
                  </span>
                  <span className="kept-meta">
                    <span>{prettyType(take.decision.type)}</span>
                    <span>{fmtWhen(take.created_at)}</span>
                    <span className="kept-file" title={take.blend_path ?? take.mix_path ?? ""}>
                      {fileTail(take.blend_path ?? take.mix_path ?? take.id)}
                    </span>
                  </span>
                </button>
                <div className="kept-actions">
                  <button
                    type="button"
                    onClick={() => onDownloadBlend(take)}
                    disabled={!take.blend_download_url}
                  >
                    blend
                  </button>
                  <button
                    type="button"
                    onClick={() => onDownloadMix(take)}
                    disabled={!take.mix_path}
                    title={take.mix_path ? undefined : "Full mix not rendered yet"}
                  >
                    mix
                  </button>
                  <button type="button" className="danger" onClick={() => onRemove(take)}>
                    remove
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
