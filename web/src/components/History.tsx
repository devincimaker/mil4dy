import { useEffect, useMemo, useState } from "react";
import { fileTail, fmtWhen, prettyType } from "../format";
import type { HistoryTake, Verdict } from "../types";

type Filter = "all" | "favorites" | "downvoted";

interface Props {
  takes: HistoryTake[];
  playingId: string | null;
  onPlay: (take: HistoryTake) => void;
  onToggleFavorite: (take: HistoryTake) => void;
  onToggleDownvote: (take: HistoryTake) => void;
  onSaveNote: (take: HistoryTake, note: string) => void;
  onDownloadBlend: (take: HistoryTake) => void;
  onDownloadMix: (take: HistoryTake) => void;
  onRemove: (take: HistoryTake) => void;
}

export function History({
  takes,
  playingId,
  onPlay,
  onToggleFavorite,
  onToggleDownvote,
  onSaveNote,
  onDownloadBlend,
  onDownloadMix,
  onRemove,
}: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const starred = useMemo(
    () => takes.filter((t) => verdictOf(t) === "favorite"),
    [takes],
  );
  const missed = useMemo(
    () => takes.filter((t) => verdictOf(t) === "downvoted"),
    [takes],
  );
  const shown =
    filter === "favorites" ? starred : filter === "downvoted" ? missed : takes;

  const empty =
    takes.length === 0
      ? "No generated mixes yet. Hear a blend — it stays here."
      : shown.length === 0 && filter === "favorites"
        ? "Nothing favorited yet. Star a take that worked."
        : shown.length === 0 && filter === "downvoted"
          ? "Nothing marked bad yet."
          : null;

  return (
    <aside className="kept">
      <header className="kept-head">
        <div>
          <h2>Generated mixes</h2>
          <p>Every Hear is saved. Star what worked. Mark what didn't.</p>
        </div>
        <span className="kept-count">
          {takes.length ? `${takes.length} saved` : "none yet"}
          {starred.length
            ? ` · ${starred.length} favorite${starred.length === 1 ? "" : "s"}`
            : ""}
          {missed.length
            ? ` · ${missed.length} didn't work`
            : ""}
        </span>
      </header>
      {takes.length > 0 && (
        <div className="kept-filter" role="tablist" aria-label="History filter">
          <FilterTab
            id="all"
            label="All"
            selected={filter === "all"}
            onSelect={setFilter}
          />
          <FilterTab
            id="favorites"
            label="Favorites"
            selected={filter === "favorites"}
            onSelect={setFilter}
          />
          <FilterTab
            id="downvoted"
            label="Didn't work"
            selected={filter === "downvoted"}
            onSelect={setFilter}
          />
        </div>
      )}
      {empty ? (
        <p className="kept-empty">{empty}</p>
      ) : (
        <ul className="kept-list">
          {shown.map((take, i) => {
            const active = take.id === playingId;
            const latest = filter === "all" && i === 0;
            const verdict = verdictOf(take);
            return (
              <li
                key={take.id}
                className={`kept-item${active ? " is-playing" : ""}${
                  verdict === "favorite" ? " is-kept" : ""
                }${verdict === "downvoted" ? " is-down" : ""}`}
              >
                <div className="kept-verdict">
                  <button
                    type="button"
                    className={`star${verdict === "favorite" ? " is-on" : ""}`}
                    onClick={() => onToggleFavorite(take)}
                    aria-pressed={verdict === "favorite"}
                    aria-label={verdict === "favorite" ? "Unfavorite" : "Favorite"}
                    title={verdict === "favorite" ? "Unfavorite" : "Favorite"}
                  >
                    {verdict === "favorite" ? "★" : "☆"}
                  </button>
                  <button
                    type="button"
                    className={`down${verdict === "downvoted" ? " is-on" : ""}`}
                    onClick={() => onToggleDownvote(take)}
                    aria-pressed={verdict === "downvoted"}
                    aria-label={verdict === "downvoted" ? "Clear downvote" : "Downvote"}
                    title={verdict === "downvoted" ? "Clear downvote" : "Downvote"}
                  >
                    <ThumbDown filled={verdict === "downvoted"} />
                  </button>
                </div>
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
                <NoteField
                  value={take.note ?? ""}
                  onCommit={(next) => onSaveNote(take, next)}
                />
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}

function FilterTab({
  id,
  label,
  selected,
  onSelect,
}: {
  id: Filter;
  label: string;
  selected: boolean;
  onSelect: (id: Filter) => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      className={`${selected ? "is-on" : ""}${id === "downvoted" && selected ? " is-down" : ""}`}
      onClick={() => onSelect(id)}
    >
      {label}
    </button>
  );
}

function NoteField({
  value,
  onCommit,
}: {
  value: string;
  onCommit: (note: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    setDraft(value);
  }, [value]);
  return (
    <label className="kept-note-wrap">
      <span className="sr-only">Debug note</span>
      <input
        className="kept-note"
        value={draft}
        placeholder="add a note…"
        onChange={(e) => setDraft(e.target.value)}
        onClick={(e) => e.stopPropagation()}
        onBlur={() => {
          if (draft !== value) onCommit(draft);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
        }}
      />
    </label>
  );
}

function ThumbDown({ filled }: { filled: boolean }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        d="M17 14V2"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      <path
        d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H17a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22a3.13 3.13 0 0 1-3-3.88Z"
        fill={filled ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function verdictOf(take: HistoryTake): Verdict {
  if (take.verdict === "favorite" || take.verdict === "downvoted" || take.verdict === "none") {
    return take.verdict;
  }
  return take.favorite ? "favorite" : "none";
}
