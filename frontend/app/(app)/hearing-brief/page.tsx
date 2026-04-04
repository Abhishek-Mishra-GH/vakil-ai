"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Brief,
  CaseSummary,
  generateBrief,
  getBrief,
  listCases,
} from "@/lib/api";

function parseBriefCollection<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? (parsed as T[]) : [];
    } catch {
      return [];
    }
  }
  return [];
}

function formatDate(value: string | null | undefined) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not available";
  return date.toLocaleString();
}

function formatTimelineDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export default function HearingBriefPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [brief, setBrief] = useState<Brief | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const selectedCase = useMemo(
    () => cases.find((item) => item.id === selectedCaseId) || null,
    [cases, selectedCaseId],
  );

  const hearingCountdownHours = useMemo(() => {
    if (!selectedCase?.hearing_date) return null;
    const target = new Date(selectedCase.hearing_date).getTime();
    if (Number.isNaN(target)) return null;
    const diff = target - Date.now();
    if (diff <= 0) return 0;
    return Math.ceil(diff / (1000 * 60 * 60));
  }, [selectedCase?.hearing_date]);

  useEffect(() => {
    void (async () => {
      try {
        const result = await listCases();
        setCases(result.cases);
        const queryCase =
          typeof window !== "undefined"
            ? new URLSearchParams(window.location.search).get("case")
            : null;
        setSelectedCaseId(queryCase || result.cases[0]?.id || "");
      } catch (err) {
        setMessage(err instanceof Error ? err.message : "Could not load cases");
      }
    })();
  }, []);

  const loadBrief = useCallback(
    async (caseId = selectedCaseId) => {
      if (!caseId) return;
      setBusy(true);
      setMessage("");
      try {
        const data = await getBrief(caseId);
        setBrief(data);
      } catch (err) {
        setBrief(null);
        setMessage(err instanceof Error ? err.message : "Brief unavailable");
      } finally {
        setBusy(false);
      }
    },
    [selectedCaseId],
  );

  useEffect(() => {
    if (!selectedCaseId) {
      setBrief(null);
      return;
    }
    void loadBrief(selectedCaseId);
  }, [loadBrief, selectedCaseId]);

  async function queueBriefGeneration() {
    if (!selectedCaseId) return;
    setBusy(true);
    setMessage("");
    try {
      await generateBrief(selectedCaseId);
      setMessage("Brief generation started. Refresh after a few seconds.");
      setTimeout(() => {
        void loadBrief(selectedCaseId);
      }, 1800);
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : "Could not start brief generation",
      );
    } finally {
      setBusy(false);
    }
  }

  const pillars = parseBriefCollection<Brief["offensive_arguments"][number]>(
    brief?.offensive_arguments,
  ).slice(0, 3);
  const threats = parseBriefCollection<Brief["defensive_arguments"][number]>(
    brief?.defensive_arguments,
  );
  const weakPoints = parseBriefCollection<Brief["weak_points"][number]>(
    brief?.weak_points,
  );
  const timeline = parseBriefCollection<Brief["timeline"][number]>(
    brief?.timeline,
  );
  const precedents = parseBriefCollection<Brief["precedents"][number]>(
    brief?.precedents,
  );
  const keyIssues = parseBriefCollection<string>(brief?.key_legal_issues);
  const docsUsed = parseBriefCollection<string>(brief?.documents_used);

  return (
    <div className="brief-shell white-theme">
      <div className="page-header">
        <h1>Hearing Brief</h1>
        <p>Structured strategic briefing for upcoming hearings.</p>
      </div>

      <section className="card" style={{ marginBottom: 16 }}>
        <div className="row-wrap">
          <label className="field-inline">
            <span>Case</span>
            <select
              className="field-input"
              value={selectedCaseId}
              onChange={(event) => setSelectedCaseId(event.target.value)}
            >
              <option value="">Select case</option>
              {cases.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn btn-primary"
            onClick={queueBriefGeneration}
            disabled={busy || !selectedCaseId}
          >
            {busy ? "Working..." : "Generate Brief"}
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => void loadBrief()}
            disabled={busy || !selectedCaseId}
          >
            Refresh
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => window.print()}
            disabled={!brief}
          >
            Export PDF
          </button>
        </div>
        {message ? (
          <p className="muted" style={{ marginTop: 10 }}>
            {message}
          </p>
        ) : null}
      </section>

      <section className="brief-hero">
        <div>
          <div className="eyebrow">Immediate Preparation Required</div>
          <h2>{selectedCase?.title || "Select a case"}</h2>
          <p>
            {selectedCase?.case_number || "Case number pending"} |{" "}
            {selectedCase?.court_name || "Court not provided"}
          </p>
          <p className="muted">
            Next hearing: {formatDate(selectedCase?.hearing_date)}
          </p>
        </div>
        <div className="countdown-box">
          <div>Hearing Countdown</div>
          <strong>{hearingCountdownHours ?? "--"} HRS</strong>
        </div>
      </section>

      <section className="brief-grid">
        <article className="brief-card quote-card">
          <h3>Core Dispute</h3>
          <p>
            {brief?.core_contention ||
              "Generate and load a brief to see the core dispute."}
          </p>
        </article>

        <article className="brief-card">
          <h3>Your Top Strategic Pillars</h3>
          {pillars.length === 0 ? (
            <p className="muted">No pillars available yet.</p>
          ) : (
            <div className="brief-list">
              {pillars.map((item, index) => (
                <div
                  key={`${item.argument}-${index}`}
                  className="brief-list-item"
                >
                  <div className="brief-index">
                    {String(index + 1).padStart(2, "0")}
                  </div>
                  <div>
                    <h4>{item.argument}</h4>
                    <p>{item.basis}</p>
                    <span className="pill">{item.source}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="brief-card">
          <h3>Procedural Timeline</h3>
          {timeline.length === 0 ? (
            <p className="muted">No timeline events available.</p>
          ) : (
            <div className="timeline-list">
              {timeline.map((item, index) => (
                <div key={`${item.event}-${index}`} className="timeline-item">
                  <span className="timeline-dot" />
                  <div>
                    <small>{formatTimelineDate(item.date)}</small>
                    <h4>{item.event}</h4>
                    <p>{item.source}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="brief-card">
          <h3>Opposition Tactical Threat</h3>
          {threats.length === 0 ? (
            <p className="muted">No opposition strategies captured yet.</p>
          ) : (
            <div className="brief-list">
              {threats.map((item, index) => (
                <div
                  key={`${item.anticipated_attack}-${index}`}
                  className="threat-item"
                >
                  <small>State&apos;s Claim</small>
                  <h4>{item.anticipated_attack}</h4>
                  <small>VakilAI Counter</small>
                  <p>{item.counter}</p>
                  <span className="pill">{item.source}</span>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="brief-card">
          <h3>Internal Weak Points</h3>
          {weakPoints.length === 0 ? (
            <p className="muted">No weak points identified.</p>
          ) : (
            <div className="brief-list">
              {weakPoints.map((item, index) => (
                <div key={`${item.issue}-${index}`} className="weak-point-item">
                  <div
                    className="row-wrap"
                    style={{ justifyContent: "space-between" }}
                  >
                    <h4>{item.issue}</h4>
                    <span
                      className={`pill ${item.severity === "HIGH" ? "pill-high" : ""}`}
                    >
                      {item.severity}
                    </span>
                  </div>
                  <p>{item.source}</p>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="brief-card">
          <h3>Key Legal Issues</h3>
          {keyIssues.length === 0 ? (
            <p className="muted">No legal issues available.</p>
          ) : (
            <div className="pill-cloud">
              {keyIssues.map((item, index) => (
                <span key={`${item}-${index}`} className="pill">
                  {item}
                </span>
              ))}
            </div>
          )}
          <h3 style={{ marginTop: 24 }}>Documents Used</h3>
          {docsUsed.length === 0 ? (
            <p className="muted">No document trace available.</p>
          ) : (
            <div className="pill-cloud">
              {docsUsed.map((item, index) => (
                <span key={`${item}-${index}`} className="pill">
                  {item}
                </span>
              ))}
            </div>
          )}
        </article>
      </section>

      <section className="card" style={{ marginTop: 18 }}>
        <h3 className="section-title">Suggested Precedents</h3>
        {precedents.length === 0 ? (
          <p className="muted">No precedents available yet.</p>
        ) : (
          <div className="precedent-grid">
            {precedents.map((item, index) => (
              <article
                key={`${item.title}-${index}`}
                className="precedent-card"
              >
                <div className="precedent-head">
                  <h4>{item.title}</h4>
                  <span className="pill">{item.year}</span>
                </div>
                <p>{item.headline}</p>
                <small>
                  {item.court} | Relevance: {item.relevance_to}
                </small>
                {item.url ? (
                  <a href={item.url} target="_blank" rel="noreferrer">
                    Read Brief
                  </a>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
