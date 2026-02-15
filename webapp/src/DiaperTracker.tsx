// @ts-nocheck
import React, { useEffect, useState, useCallback } from "react";
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faBaby, faDroplet, faPoo, faCircle, faChevronDown, faChevronUp } from '@fortawesome/free-solid-svg-icons';

const API_BASE = `http://${process.env.REACT_APP_BACKEND_IP}`;

function timeAgo(isoString) {
  if (!isoString) return "—";
  const diff = (Date.now() - new Date(isoString).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatTime(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  let h = d.getHours(), m = d.getMinutes();
  const ampm = h >= 12 ? "pm" : "am";
  h = h % 12 || 12;
  return `${h}:${m < 10 ? "0" + m : m} ${ampm}`;
}

export default function DiaperTracker() {
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [logging, setLogging] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/diaper/stats`);
      setStats(await res.json());
    } catch (e) { console.error("Failed to fetch diaper stats", e); }
  }, []);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/diaper/history?limit=10`);
      setHistory(await res.json());
    } catch (e) { console.error("Failed to fetch diaper history", e); }
  }, []);

  useEffect(() => {
    fetchStats();
    fetchHistory();
    const interval = setInterval(fetchStats, 60000);
    return () => clearInterval(interval);
  }, [fetchStats, fetchHistory]);

  const logChange = async (type) => {
    setLogging(true);
    try {
      await fetch(`${API_BASE}/api/diaper`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type }),
      });
      await fetchStats();
      await fetchHistory();
    } catch (e) { console.error("Failed to log diaper change", e); }
    setLogging(false);
  };

  const btnStyle = (color) => ({
    padding: "12px 20px",
    fontSize: "16px",
    border: "none",
    borderRadius: "8px",
    cursor: logging ? "not-allowed" : "pointer",
    backgroundColor: color,
    color: "#fff",
    opacity: logging ? 0.6 : 1,
    display: "flex",
    alignItems: "center",
    gap: "8px",
  });

  return (
    <div style={{ padding: "16px" }}>
      <h3 style={{ margin: "0 0 12px 0" }}>
        <FontAwesomeIcon icon={faBaby} style={{ marginRight: "10px" }} />
        Diaper Tracker
      </h3>

      {/* Quick-log buttons */}
      <div style={{ display: "flex", justifyContent: "center", gap: "12px", marginBottom: "16px" }}>
        <button style={btnStyle("#2196F3")} onClick={() => logChange("wet")} disabled={logging}>
          <FontAwesomeIcon icon={faDroplet} /> Wet
        </button>
        <button style={btnStyle("#8D6E63")} onClick={() => logChange("dirty")} disabled={logging}>
          <FontAwesomeIcon icon={faPoo} /> Dirty
        </button>
        <button style={btnStyle("#7B1FA2")} onClick={() => logChange("both")} disabled={logging}>
          <FontAwesomeIcon icon={faCircle} /> Both
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", textAlign: "center", marginBottom: "12px" }}>
          <div>
            <div style={{ fontSize: "24px", fontWeight: "bold" }}>
              {stats.last_change ? timeAgo(stats.last_change.timestamp) : "—"}
            </div>
            <div style={{ fontSize: "12px", opacity: 0.7 }}>Last change</div>
          </div>
          <div>
            <div style={{ fontSize: "24px", fontWeight: "bold" }}>{stats.total}</div>
            <div style={{ fontSize: "12px", opacity: 0.7 }}>Today ({stats.wet}W / {stats.dirty}D)</div>
          </div>
          <div style={{ gridColumn: "1 / -1" }}>
            <div style={{ fontSize: "18px", fontWeight: "bold" }}>{stats.daily_average_7d}</div>
            <div style={{ fontSize: "12px", opacity: 0.7 }}>7-day daily avg</div>
          </div>
        </div>
      )}

      {/* Expandable history */}
      <div
        style={{ cursor: "pointer", textAlign: "center", opacity: 0.7, fontSize: "14px" }}
        onClick={() => setShowHistory(!showHistory)}
      >
        <FontAwesomeIcon icon={showHistory ? faChevronUp : faChevronDown} style={{ marginRight: "6px" }} />
        {showHistory ? "Hide" : "Show"} recent history
      </div>

      {showHistory && history.length > 0 && (
        <div style={{ marginTop: "8px", fontSize: "14px" }}>
          {history.map((evt) => (
            <div key={evt.id} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
              <span style={{ textTransform: "capitalize" }}>{evt.type}</span>
              <span style={{ opacity: 0.7 }}>{formatTime(evt.timestamp)} — {timeAgo(evt.timestamp)}</span>
            </div>
          ))}
        </div>
      )}

      {showHistory && history.length === 0 && (
        <div style={{ textAlign: "center", opacity: 0.5, marginTop: "8px" }}>No events yet</div>
      )}
    </div>
  );
}
