"use client";

import { MootSessionHistoryItem } from "@/lib/api";

function formatSessionLabel(startedAt: string) {
  const date = new Date(startedAt);
  if (Number.isNaN(date.getTime())) return startedAt;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function MootSessionsSidebar({
  sessions,
  activeSessionId,
  collapsed,
  onToggleCollapsed,
  onSelectSession,
  onCreateNewSession,
  disabled,
}: {
  sessions: MootSessionHistoryItem[];
  activeSessionId: string;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onSelectSession: (sessionId: string) => void;
  onCreateNewSession: () => void;
  disabled?: boolean;
}) {
  const width = collapsed ? 64 : 320;

  return (
    <aside className="card" style={{ width, padding: collapsed ? 12 : 16, position: "sticky", top: 16, height: "fit-content" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <div style={{ fontWeight: 800, letterSpacing: "0.06em", textTransform: "uppercase", fontSize: "0.85rem" }}>
          {collapsed ? "Sessions" : "Previous Sessions"}
        </div>
        <button type="button" className="btn btn-secondary" onClick={onToggleCollapsed} disabled={disabled} style={{ minWidth: 44, padding: 0 }}>
          {collapsed ? ">" : "<"}
        </button>
      </div>

      {collapsed ? null : (
        <>
          <div style={{ marginTop: 12 }}>
            <button type="button" className="btn btn-primary" onClick={onCreateNewSession} disabled={disabled} style={{ width: "100%" }}>
              New Session
            </button>
          </div>

          <div style={{ marginTop: 14 }}>
            {sessions.length === 0 ? (
              <div className="muted">No sessions yet for this case.</div>
            ) : (
              <div className="list-stack">
                {sessions.map((session) => {
                  const isActive = session.session_id === activeSessionId;
                  const meta = `${session.status.toUpperCase()} • Exchanges: ${session.exchange_count}`;
                  return (
                    <button
                      key={session.session_id}
                      type="button"
                      className={`list-item ${isActive ? "active" : ""}`}
                      onClick={() => onSelectSession(session.session_id)}
                      disabled={disabled}
                    >
                      <div className="list-item-title">{formatSessionLabel(session.started_at)}</div>
                      <div className="list-item-meta">{meta}</div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
