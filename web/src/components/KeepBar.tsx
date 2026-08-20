interface Props {
  canKeep: boolean;
  favorited: boolean;
  mixBusy: boolean;
  mixElapsed: number;
  busy: boolean;
  onFavorite: () => void;
  onUnfavorite: () => void;
  onDownloadBlend: () => void;
  onDownloadMix: () => void;
}

export function KeepBar({
  canKeep,
  favorited,
  mixBusy,
  mixElapsed,
  busy,
  onFavorite,
  onUnfavorite,
  onDownloadBlend,
  onDownloadMix,
}: Props) {
  const mixLabel = mixBusy
    ? mixElapsed > 0
      ? `mixing both tracks… ${mixElapsed}s`
      : "mixing both tracks…"
    : "Download the mix";

  return (
    <div className="keep-bar">
      <button
        type="button"
        className={`keep-btn${favorited ? " is-on" : ""}`}
        onClick={favorited ? onUnfavorite : onFavorite}
        disabled={!canKeep || busy}
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
        className="keep-btn"
        onClick={onDownloadBlend}
        disabled={!canKeep || busy}
      >
        Download the blend
      </button>
      <button
        type="button"
        className="keep-btn keep-mix"
        onClick={onDownloadMix}
        disabled={!canKeep || busy || mixBusy}
      >
        {mixLabel}
      </button>
      {mixBusy && (
        <progress className="mix-progress" aria-label="Rendering the two-song mix" />
      )}
    </div>
  );
}
