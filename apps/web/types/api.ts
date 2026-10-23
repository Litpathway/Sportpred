export interface Fixture {
  id: number; home: string; away: string; home_logo?: string | null; away_logo?: string | null; competition: string; country: string;
  kickoff: string; status: string; simulated: boolean; home_goals: number | null; away_goals: number | null;
  synced_at: string; odds: Record<string, number>; odds_at: string | null; enrichment: Record<string, unknown>;
  provenance?: {rights?: {prototype_only: boolean; commercial_use: boolean}; observed_at?: string; source?: string; coverage?: string;
    odds?: {source?: string; bookmaker?: string; provider_updated_at?: string | null; observed_at?: string; market_count?: number}}; provider?: string;
}
export interface Prediction {
  id: number; fixture: Fixture; market: string; market_label: string; probability: number;
  raw_probability: number; quality: number; odds: number | null; eligible: boolean; reasons: string[];
  outcome: string; explanation: string; features: { values: Record<string, number>; missing: string[]; available_enrichment?: Record<string, unknown>; home_form: string[]; away_form: string[]; as_of: string };
  created_at: string; model: string; model_approved: boolean;
}
export interface CalibrationPoint { predicted: number; observed: number }
export interface MarketMetric { n: number; brier: number; log_loss: number; accuracy: number; calibration: CalibrationPoint[] }
export interface Model {
  id: number; version: string; approved: boolean; simulated: boolean; trained_until: string; created_at: string;
  metrics: { brier: number; log_loss: number; training_rows: number; validation_rows: number; test_rows: number;
    algorithm: string; markets: Record<string, MarketMetric>; splits: Record<string, {start: string; end: string}> };
}
export interface Performance {
  total: number; won: number; lost: number; void: number; pending: number; accuracy: number | null;
  metrics: MarketMetric | null; roi: number | null; roi_assumptions: string;
  by_market: {name: string; count: number; accuracy: number}[];
  by_probability_band: {name: string; count: number; accuracy: number}[];
  by_model: {name: string; count: number; accuracy: number}[];
  history: {date: string; accuracy: number; count: number}[]; simulated: boolean;
}
export interface Overview {
  upcoming_matches: number; eligible_predictions: number; verified_codes: number; competitions: number;
  threshold: number; demo_mode: boolean; publication_paused: boolean; model: Model | null; performance: Performance;
  data_mode?: "demo" | "personal_research" | "authorized_feed";
}
export interface Page<T> { items: T[]; total: number }
export interface Slip {
  id: number; status: string; joint_probability: number | null; combined_odds: number | null;
  expected_value: number | null; assumption: string; code: string | null; verified: boolean;
  provider: string | null; published_at: string | null; predictions: Prediction[]; failure_reason: string | null;
}
export interface AdminUser { email: string; role: string; csrf_token: string }
export interface PlatformSettings { threshold: number; min_quality: number; publication_paused: boolean; max_legs: number; provider_enabled: boolean }
export interface Job {id: number; name: string; status: string; attempts: number; error: string | null; started_at: string }
export interface Audit {id: number; action: string; actor: string; entity: string; created_at: string; detail: Record<string, unknown> }
export interface Providers {
  fixtures: {name: string; enabled: boolean; last_sync: string | null; status: string};
  booking: {name: string; genuine_enabled: boolean}; recent_failure_count: number;
  sportybet_odds?: {enabled: boolean; region: string; status: string; sync?: {status: string; matched_fixtures: number; observed_at: string} | null};
}
