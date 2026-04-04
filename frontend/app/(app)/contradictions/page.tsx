"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CaseSummary, Contradiction, listCases, listContradictions, rerunContradictions } from "@/lib/api";

export default function ContradictionsPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [rows, setRows] = useState<Contradiction[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const data = await listCases();
        setCases(data.cases);
        const next =
          (typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("case") : null) ||
          data.cases[0]?.id ||
          "";
        setSelectedCaseId(next);
      } catch (err) {
        setMessage(err instanceof Error ? err.message : "Could not load cases");
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedCaseId) {
      setRows([]);
      return;
    }
    void refresh(selectedCaseId);
  }, [selectedCaseId]);

  async function refresh(caseId: string) {
    setBusy(true);
    setMessage("");
    try {
      const data = await listContradictions(caseId);
      setRows(data.contradictions);
    } catch (err) {
      setRows([]);
      setMessage(err instanceof Error ? err.message : "Could not load contradictions");
    } finally {
      setBusy(false);
    }
  }

  async function rerun() {
    if (!selectedCaseId) return;
    setBusy(true);
    setMessage("");
    try {
      await rerunContradictions(selectedCaseId);
      setMessage("Contradiction rerun queued. Refreshing latest results...");
      await refresh(selectedCaseId);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not queue contradiction rerun");
    } finally {
      setBusy(false);
    }
  }

  const highCount = rows.filter((item) => item.severity === "HIGH").length;
  const mediumCount = rows.filter((item) => item.severity === "MEDIUM").length;

  return (
    <div>
      <div className="page-header">
        <h1>Contradiction Engine</h1>
        <p>Pairwise factual conflicts across ready case documents.</p>
      </div>

      <section className="card" style={{ marginBottom: 16 }}>
        <div className="row-wrap">
          <label className="field-inline">
            <span>Case</span>
            <select value={selectedCaseId} onChange={(e) => setSelectedCaseId(e.target.value)} className="field-input">
              <option value="">Select case</option>
              {cases.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
          <button className="btn btn-primary" onClick={rerun} disabled={busy || !selectedCaseId}>
            {busy ? "Running..." : "Re-run contradictions"}
          </button>
        </div>
        {message ? <p style={{ marginTop: 10, color: "var(--text-secondary)" }}>{message}</p> : null}
      </section>

      <section className="card">
        <div className="row-wrap" style={{ justifyContent: "space-between", marginBottom: 14 }}>
          <h2 className="section-title" style={{ margin: 0 }}>
            Findings ({rows.length})
          </h2>
          <div className="row-wrap">
            <span className="badge badge-high-risk">High {highCount}</span>
            <span className="badge badge-medium-risk">Medium {mediumCount}</span>
          </div>
        </div>

        {rows.length === 0 ? (
          <p className="muted">No contradictions found yet for this case.</p>
        ) : (
          rows.map((item) => (
            <article key={item.id} className="contradiction-card">
              <div className={`severity-bar ${item.severity.toLowerCase()}`} />
              <div className="statements">
                <div className="statement">
                  <div className="statement-label doc-a">
                    {item.doc_a_name} {item.page_a ? `| Page ${item.page_a}` : ""}
                  </div>
                  <div className="statement-text">
                    &ldquo;{item.claim_a}&rdquo;
                  </div>
                </div>
                <div className="statement">
                  <div className="statement-label doc-b">
                    {item.doc_b_name} {item.page_b ? `| Page ${item.page_b}` : ""}
                  </div>
                  <div className="statement-text">
                    &ldquo;{item.claim_b}&rdquo;
                  </div>
                </div>
              </div>
              <div className="explanation">
                <strong>{item.severity}:</strong> {item.explanation}
                <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                  <Link className="btn btn-secondary" href={`/xray?case=${selectedCaseId}&doc=${item.doc_a_id}`}>
                    View Doc A in X-Ray
                  </Link>
                  <Link className="btn btn-secondary" href={`/xray?case=${selectedCaseId}&doc=${item.doc_b_id}`}>
                    View Doc B in X-Ray
                  </Link>
                </div>
              </div>
            </article>
          ))
        )}
      </section>
    </div>
  );
}
