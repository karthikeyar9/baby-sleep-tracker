import { fetchApi, fetchText, fetchCSV } from "./client";
import type {
  SleepStatsResponse,
  WeeklyDay,
  SleepEvent,
  DiaperStats,
  DiaperEvent,
  FeedingEvent,
} from "./types";

export const sleep = {
  getStats: () => fetchApi<SleepStatsResponse>("/api/sleep/stats"),
  getWeekly: () => fetchApi<WeeklyDay[]>("/api/sleep/weekly"),
  getEvents: () => fetchApi<SleepEvent[]>("/api/sleep/events"),
};

export const diaper = {
  log: (type: string) =>
    fetchApi<{ status: string }>("/api/diaper", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type }),
    }),
  getStats: () => fetchApi<DiaperStats>("/api/diaper/stats"),
  getHistory: (limit = 10) =>
    fetchApi<DiaperEvent[]>(`/api/diaper/history?limit=${limit}`),
};

export const feeding = {
  log: (data: { type: string; amount_ml?: number }) =>
    fetchApi<{ status: string }>("/api/feeding", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  getHistory: (limit = 10) =>
    fetchApi<FeedingEvent[]>(`/api/feeding/history?limit=${limit}`),
};

export const legacy = {
  getClassificationProba: () => fetchText("/getClassificationProbabilities"),
  getResultAndReasons: () => fetchText("/getResultAndReasons"),
  getNotificationsEnabled: () => fetchText("/getSleepNotificationsEnabled"),
  setNotificationsEnabled: (enabled: boolean) =>
    fetch(`http://${process.env.REACT_APP_BACKEND_IP}/setSleepNotificationsEnabled/${enabled}`),
  retrainWithNewSample: (classification: string) =>
    fetch(`http://${process.env.REACT_APP_BACKEND_IP}/retrainWithNewSample/${classification}`),
  setAIFocusRegion: (bounds: string) =>
    fetch(`http://${process.env.REACT_APP_BACKEND_IP}/setAIFocusRegion/${bounds}`),
};

export const csv = {
  getSleepLogs: async (forecast: boolean) => {
    const file = forecast ? "sleep_logs_forecasted" : "sleep_logs";
    const sleepLogs = await fetchCSV(file);
    sleepLogs.forEach((d: any) => {
      d.time = new Date((d.time as any) * 1000);
    });
    return sleepLogs;
  },
};
