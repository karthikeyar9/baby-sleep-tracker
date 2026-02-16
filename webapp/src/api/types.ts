export interface WakeWindow {
  awake_minutes: number;
  window_min_minutes: number;
  window_max_minutes: number;
  remaining_minutes: number;
  urgency: string;
  baby_age_months: number;
}

export interface NightSleep {
  total_minutes: number;
  wake_count: number;
  longest_stretch_minutes: number;
}

export interface SleepStatsResponse {
  total_nap_minutes: number;
  nap_count: number;
  longest_nap_minutes: number;
  wake_window: WakeWindow;
  night_sleep: NightSleep;
}

export interface WeeklyDay {
  date: string;
  day_label: string;
  total_nap_minutes: number;
  nap_count: number;
  longest_nap_minutes: number;
}

export interface SleepEvent {
  id: number;
  timestamp: string;
  awake: boolean;
}

export interface CryEvent {
  id: number;
  timestamp: string;
  duration_seconds: number;
}

export interface DiaperEvent {
  id: number;
  type: string;
  timestamp: string;
}

export interface DiaperStats {
  total: number;
  wet: number;
  dirty: number;
  daily_average_7d: number;
  last_change: { timestamp: string; type: string } | null;
}

export interface FeedingEvent {
  id: number;
  type: string;
  amount_ml: number;
  timestamp: string;
}

export interface HealthResponse {
  status: string;
  uptime: number;
}
