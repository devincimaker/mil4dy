import { useEffect, useRef, useState } from "react";
import type { Verdict } from "../types";

interface Props {
  canKeep: boolean;
  verdict: Verdict;
  note: string;
  mixBusy: boolean;
  mixElapsed: number;
  busy: boolean;
  onFavorite: () => void;
  onUnfavorite: () => void;
  onDownvote: (note: string) => void;
  onClearDownvote: () => void;
  onSaveNote: (note: string) => void;
  onDownloadBlend: () => void;
  onDownloadMix: () => void;
}

export function KeepBar({
  canKeep,
  verdict,
  note,
  mixBusy,
  mixElapsed,
  busy,
  onFavorite,
  onUnfavorite,
  onDownvote,
  onClearDownvote,
  onSaveNote,
  onDownloadBlend,
  onDownloadMix,
}: Props) {
  const [draft, setDraft] = useState(note);
  const skipNoteBlur = useRef(false);
  const favorited = verdict === "favorite";
  const downvoted = verdict === "downvoted";

  const holdNoteBlur = () => {
    skipNoteBlur.current = true;
  };

  useEffect(() => {
    setDraft(note);
  }, [note]);

  const mixLabel = mixBusy
    ? mixElapsed > 0
      ? `mixing both tracks… ${mixElapsed}s`
      : "mixing both tracks…"
    : "Download the mix";

  const locked = !canKeep || busy;

  return (
    <div className="keep-bar">
      <button
        type="button"
        className={`keep-btn keep-fav${favorited ? " is-on" : ""}`}
        onMouseDown={holdNoteBlur}
        onClick={favorited ? onUnfavorite : onFavorite}
        disabled={locked}
        aria-pressed={favorited}
        title={
          canKeep
            ? "Already saved. Star it if this take worked."
            : "Hear the blend first — every Hear is saved automatically"
        }
      >
        {favorited ? "Unfavorite" : "Favorite"}
      </button>
      <button
        type="button"
        className={`keep-btn keep-down${downvoted ? " is-down" : ""}`}
        onMouseDown={holdNoteBlur}
        onClick={() => (downvoted ? onClearDownvote() : onDownvote(draft))}
        disabled={locked}
        aria-pressed={downvoted}
        title={
          canKeep
            ? "Mark this take as a miss. The file stays so you can debug it."
            : "Hear the blend first — every Hear is saved automatically"
        }
      >
        Didn't work
      </button>
      <button
        type="button"
        className="keep-btn keep-blend"
        onClick={onDownloadBlend}
        disabled={locked}
      >
        Download the blend
      </button>
      <button
        type="button"
        className="keep-btn keep-mix"
        onClick={onDownloadMix}
        disabled={locked || mixBusy}
      >
        {mixLabel}
      </button>
      <label className="keep-note-wrap">
        <span className="sr-only">Debug note</span>
        <input
          className="keep-note"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => {
            if (skipNoteBlur.current) {
              skipNoteBlur.current = false;
              return;
            }
            if (draft !== note) onSaveNote(draft);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
          disabled={locked}
          placeholder="optional note — why it failed, or why it worked"
        />
      </label>
      {mixBusy && (
        <progress className="mix-progress" aria-label="Rendering the two-song mix" />
      )}
    </div>
  );
}
