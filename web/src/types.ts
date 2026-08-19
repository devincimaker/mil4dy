export type SegmentLabel =
  | "intro"
  | "build"
  | "drop"
  | "breakdown"
  | "verse"
  | "outro";

export interface Segment {
  label: SegmentLabel;
  start: number;
  end: number;
  energy: number;
  vocal_likelihood: number;
  bass_ratio: number;
  confidence: number;
}

export interface Track {
  id: string;
  path: string;
  title: string;
  artist: string;
  genre: string;
  duration: number;
  bpm: number;
  key: string;
  scale: string;
  camelot: string;
  key_confidence: number;
  energy: number;
  lufs_integrated: number;
  downbeat_confidence: number;
  beats_engine: string;
  n_beats: number;
  segments: Segment[];
  phrase_starts: number[];
}

export interface Decision {
  type: string;
  length_beats: number;
  length_bars: number;
  out_start_s: number;
  in_start_s: number;
  out_end_s: number;
  in_end_s: number;
  out_label: string;
  in_arrival_label: string;
  swap_beat: number;
  bpm_gap: number;
  camelot_score: number;
  vocal_out: number;
  vocal_in: number;
  fx: string[];
  reasons: string[];
  window_duration_s: number;
  window_expected_s: number;
  out_index_span_s: number;
  in_index_span_s: number;
  out_grid_ok: boolean;
  in_grid_ok: boolean;
  grid_warning: string | null;
  pulse_warning: string | null;
  out_pulse_shift_s: number;
  in_pulse_shift_s: number;
  blend_start_s: number;
  blend_end_s: number;
}

export interface PairResponse {
  a: Track;
  b: Track;
  decision: Decision;
}
