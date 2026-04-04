"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  CaseSummary,
  DocumentInfo,
  Insight,
  askQaSession,
  createQaSession,
  getDocumentPdf,
  getInsights,
  getQaMessages,
  listCaseDocuments,
  listCases,
  QaMessage,
  searchPrecedents,
  PrecedentResult,
} from "@/lib/api";

import "./xray-light.css";
const XrayPdfCanvas = dynamic(() => import("@/components/XrayPdfCanvas"), {
  ssr: false,
  loading: () => (
    <p className="xray-canvas-note" style={{ padding: 20 }}>
      Loading PDF...
    </p>
  ),
});

export default function XRayPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [selectedDocId, setSelectedDocId] = useState("");
  const [insights, setInsights] = useState<Insight[]>([]);
  const [selectedInsightId, setSelectedInsightId] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [qaSessionId, setQaSessionId] = useState("");
  const [qaQuestion, setQaQuestion] = useState("");
  const [qaMessages, setQaMessages] = useState<QaMessage[]>([]);
  const [pdfUrl, setPdfUrl] = useState("");
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfPageCount, setPdfPageCount] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [portalNode, setPortalNode] = useState<HTMLElement | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>(
    {
      HIGH_RISK: true,
      MEDIUM_RISK: true,
      STANDARD: false,
    },
  );
  const [riskFilter, setRiskFilter] = useState<string>("ALL");
  const [precedentsModalOpen, setPrecedentsModalOpen] = useState(false);
  const [precedentsLoading, setPrecedentsLoading] = useState(false);
  const [precedentsList, setPrecedentsList] = useState<PrecedentResult[]>([]);
  const [precedentsError, setPrecedentsError] = useState("");
  const [selectedPrecedentIssue, setSelectedPrecedentIssue] = useState("");

  useEffect(() => {
    setMounted(true);
    const target = document.getElementById("topnav-portal-target");
    if (target) setPortalNode(target);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const caseData = await listCases();
        setCases(caseData.cases);
        const queryCase =
          typeof window !== "undefined"
            ? new URLSearchParams(window.location.search).get("case")
            : null;
        const nextCaseId = queryCase || caseData.cases[0]?.id || "";
        setSelectedCaseId(nextCaseId);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load cases");
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedCaseId) {
      setDocuments([]);
      setSelectedDocId("");
      return;
    }
    void (async () => {
      try {
        const docData = await listCaseDocuments(selectedCaseId);
        setDocuments(docData.documents);
        const queryDoc =
          typeof window !== "undefined"
            ? new URLSearchParams(window.location.search).get("doc")
            : null;
        const nextDoc =
          queryDoc ||
          docData.documents.find((item) => item.processing_status === "ready")
            ?.id ||
          docData.documents[0]?.id ||
          "";
        setSelectedDocId(nextDoc);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Could not load documents",
        );
      }
    })();
  }, [selectedCaseId]);

  useEffect(() => {
    if (!selectedDocId || !selectedCaseId) {
      setInsights([]);
      setQaSessionId("");
      setQaMessages([]);
      return;
    }
    void (async () => {
      try {
        const data = await getInsights(selectedDocId);
        setInsights(data.insights);
        const firstPage = data.insights[0]?.page_number || 1;
        setCurrentPage(firstPage);
        setSelectedInsightId(data.insights[0]?.id || "");

        const session = await createQaSession({
          case_id: selectedCaseId,
          document_id: selectedDocId,
        });
        setQaSessionId(session.session_id);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Could not load x-ray insights",
        );
      }
    })();
  }, [selectedCaseId, selectedDocId]);

  useEffect(() => {
    if (!qaSessionId) return;
    void (async () => {
      try {
        const data = await getQaMessages(qaSessionId);
        setQaMessages(data.messages);
      } catch (err) {
        console.error(err);
      }
    })();
  }, [qaSessionId]);

  useEffect(() => {
    let active = true;
    let objectUrl = "";
    if (!selectedDocId) {
      setPdfUrl("");
      return () => {
        active = false;
      };
    }

    setPdfLoading(true);
    void (async () => {
      try {
        const blob = await getDocumentPdf(selectedDocId);
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setPdfUrl(objectUrl);
      } catch (err) {
        if (!active) return;
        setPdfUrl("");
        setError(
          err instanceof Error ? err.message : "Could not load PDF file",
        );
      } finally {
        if (active) setPdfLoading(false);
      }
    })();

    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [selectedDocId]);

  const selectedInsight = useMemo(
    () => insights.find((item) => item.id === selectedInsightId) || null,
    [insights, selectedInsightId],
  );
  const selectedCase = useMemo(
    () => cases.find((item) => item.id === selectedCaseId) || null,
    [cases, selectedCaseId],
  );
  const selectedDocument = useMemo(
    () => documents.find((item) => item.id === selectedDocId) || null,
    [documents, selectedDocId],
  );

  const grouped = useMemo(() => {
    const output: Record<string, Insight[]> = {
      HIGH_RISK: [],
      MEDIUM_RISK: [],
      STANDARD: [],
    };
    insights.forEach((item) => output[item.anomaly_flag]?.push(item));
    return output;
  }, [insights]);

  const visibleOverlays = insights.filter(
    (item) => item.page_number === currentPage,
  );
  const pageNumbers = useMemo(() => {
    const total = pdfPageCount || 1;
    return Array.from({ length: total }, (_, index) => index + 1);
  }, [pdfPageCount]);

  const filteredInsights = useMemo(() => {
    if (riskFilter === "ALL") return insights;
    return insights.filter((item) => item.anomaly_flag === riskFilter);
  }, [insights, riskFilter]);

  async function askQuestion(event: React.FormEvent) {
    event.preventDefault();
    if (!qaSessionId || !qaQuestion.trim()) return;

    const questionText = qaQuestion.trim();
    setQaQuestion("");
    setBusy(true);

    const tempUserMsg: QaMessage = {
      role: "user",
      content: questionText,
      created_at: new Date().toISOString(),
    };
    setQaMessages((prev) => [...prev, tempUserMsg]);

    try {
      const result = await askQaSession(qaSessionId, questionText);
      const tempAiMsg: QaMessage = {
        role: "assistant",
        content: result.answer,
        created_at: new Date().toISOString(),
      };
      setQaMessages((prev) => [...prev, tempAiMsg]);
    } catch (err) {
      const errorMsg: QaMessage = {
        role: "assistant",
        content: err instanceof Error ? err.message : "Question failed",
        created_at: new Date().toISOString(),
      };
      setQaMessages((prev) => [...prev, errorMsg]);
    } finally {
      setBusy(false);
    }
  }

  async function handleViewPrecedents(issue: string) {
    if (!issue) return;
    setPrecedentsModalOpen(true);
    setPrecedentsLoading(true);
    setPrecedentsError("");
    setSelectedPrecedentIssue(issue);
    try {
      const res = await searchPrecedents(issue, 3);
      setPrecedentsList(res);
    } catch (err) {
      setPrecedentsError(
        err instanceof Error ? err.message : "Failed to load precedents",
      );
    } finally {
      setPrecedentsLoading(false);
    }
  }

  return (
    <div className="xray-light-wrapper">
      {portalNode &&
        createPortal(
          <div className="xray-controls-row" style={{ marginBottom: 0 }}>
            <select
              value={selectedCaseId}
              onChange={(e) => setSelectedCaseId(e.target.value)}
              className="xray-light-select"
            >
              <option value="">Select case</option>
              {cases.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
            <select
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
              className="xray-light-select"
            >
              <option value="">Select document</option>
              {documents.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.original_filename} ({item.processing_status})
                </option>
              ))}
            </select>
          </div>,
          portalNode,
        )}

      {error && <p style={{ color: "#ef4444", marginBottom: 16 }}>{error}</p>}

      <div className="xray-light-grid">
        <div className="xray-light-pdf-pane">
          <div className="xray-light-pdf-controls" suppressHydrationWarning>
            <button
              suppressHydrationWarning
              onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
              disabled={currentPage <= 1}
            >
              Prev
            </button>
            <select
              value={currentPage}
              onChange={(e) => setCurrentPage(Number(e.target.value))}
              className="xray-light-select"
              style={{ width: 140 }}
            >
              {pageNumbers.map((page) => (
                <option key={page} value={page}>
                  Page {page} of {pdfPageCount || "--"}
                </option>
              ))}
            </select>
            <button
              suppressHydrationWarning
              onClick={() =>
                setCurrentPage((prev) =>
                  Math.min(
                    pageNumbers[pageNumbers.length - 1] || prev + 1,
                    prev + 1,
                  ),
                )
              }
              disabled={
                pageNumbers.length > 0 &&
                currentPage >= pageNumbers[pageNumbers.length - 1]
              }
            >
              Next
            </button>
            <div
              style={{
                width: 1,
                height: 20,
                background: "#d1d5db",
                margin: "0 8px",
              }}
            />
            <button
              onClick={() => setZoom((z) => Math.max(0.5, z - 0.2))}
              disabled={zoom <= 0.5}
            >
              -
            </button>
            <span
              style={{ fontSize: "0.8rem", width: "40px", textAlign: "center" }}
            >
              {Math.round(zoom * 100)}%
            </span>
            <button
              onClick={() => setZoom((z) => Math.min(2.5, z + 0.2))}
              disabled={zoom >= 2.5}
            >
              +
            </button>
          </div>
          <div className="xray-light-pdf-canvas">
            {pdfUrl ? (
              <XrayPdfCanvas
                currentPage={currentPage}
                pdfUrl={pdfUrl}
                zoom={zoom}
                selectedInsightId={selectedInsight?.id || ""}
                visibleOverlays={visibleOverlays}
                onLoadError={(message) => setError(message)}
                onLoadSuccess={(pageCount) => {
                  setPdfPageCount(pageCount);
                  if (currentPage > pageCount) setCurrentPage(1);
                }}
                onSelectInsight={(insightId) => setSelectedInsightId(insightId)}
              />
            ) : (
              <p style={{ marginTop: 40 }}>
                {pdfLoading ? "Loading PDF..." : "PDF unavailable"}
              </p>
            )}
          </div>
        </div>

        <div className="xray-light-clauses">
          <div className="ci-header">
            <span className="ci-header-label">AI ANALYSIS</span>
            <div className="ci-filter-tabs">
              {(["ALL", "HIGH_RISK", "MEDIUM_RISK", "STANDARD"] as const).map(
                (level) => (
                  <button
                    key={level}
                    className={`ci-tab ${riskFilter === level ? "ci-tab--active" : ""} ${level === "HIGH_RISK" ? "ci-tab--high" : level === "MEDIUM_RISK" ? "ci-tab--medium" : ""}`}
                    onClick={() => setRiskFilter(level)}
                  >
                    {level === "ALL" ? "ALL" : level.replace("_", " ")}
                  </button>
                ),
              )}
            </div>
            <span className="ci-count">
              {filteredInsights.length} CLAUSES FOUND
            </span>
          </div>
          <div className="xray-light-clauses-content">
            {filteredInsights.length === 0 && (
              <p
                style={{
                  color: "#6b7280",
                  padding: "20px",
                  textAlign: "center",
                  fontSize: "0.85rem",
                }}
              >
                No clauses found for this filter.
              </p>
            )}
            {filteredInsights.map((insight) => {
              const riskClass =
                insight.anomaly_flag === "HIGH_RISK"
                  ? "high-risk"
                  : insight.anomaly_flag === "MEDIUM_RISK"
                    ? "medium-risk"
                    : "standard";
              const riskIcon =
                insight.anomaly_flag === "HIGH_RISK"
                  ? "⚠"
                  : insight.anomaly_flag === "MEDIUM_RISK"
                    ? "ⓘ"
                    : "✓";
              return (
                <div
                  key={insight.id}
                  className={`ci-card ci-card--${riskClass} ${selectedInsightId === insight.id ? "ci-card--selected" : ""}`}
                  onClick={() => {
                    setSelectedInsightId(insight.id);
                    setCurrentPage(insight.page_number);
                  }}
                >
                  <div className="ci-card-top">
                    <span
                      className={`ci-card-label ci-card-label--${riskClass}`}
                    >
                      {insight.clause_type}{" "}
                      <span style={{ opacity: 0.5, margin: "0 6px" }}>•</span>{" "}
                      {insight.anomaly_flag.replace("_", " ")}
                    </span>
                    <span className={`ci-card-icon ci-card-icon--${riskClass}`}>
                      {riskIcon}
                    </span>
                  </div>
                  <div className="ci-card-summary">{insight.summary}</div>
                  {insight.anomaly_reason && (
                    <div
                      className={`ci-card-banner ci-card-banner--${riskClass}`}
                    >
                      <span className="ci-card-banner-icon">!</span>
                      <span>{insight.anomaly_reason}</span>
                    </div>
                  )}
                  <div className="ci-card-footer">
                    <span className="ci-card-statute">
                      {insight.statutory_reference &&
                      insight.statutory_reference.toUpperCase() !== "N/A"
                        ? `§ ${insight.statutory_reference}`
                        : `PAGE ${insight.page_number}`}
                    </span>
                    <button
                      className="ci-card-action"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (insight.anomaly_flag !== "HIGH_RISK") {
                          handleViewPrecedents(
                            insight.summary || insight.clause_type,
                          );
                        }
                      }}
                    >
                      {insight.anomaly_flag === "HIGH_RISK"
                        ? "DRAFT REBUTTAL"
                        : "VIEW PRECEDENTS"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="xray-light-chat">
          <h2>
            AI Chat Assistant
            <button className="xray-light-chat-close">✕</button>
          </h2>
          <div className="xray-light-chat-messages">
            {qaMessages.map((msg, i) => (
              <div key={i} className="xray-light-msg">
                <div
                  className={`xray-light-msg-avatar ${msg.role === "assistant" ? "ai" : "user"}`}
                >
                  <div className="xray-light-avatar-icon">
                    {msg.role === "assistant" ? "AI" : "U"}
                  </div>
                  {msg.role === "assistant" ? "AI" : "User"}
                </div>
                <div className="xray-light-msg-content">{msg.content}</div>
              </div>
            ))}
            {busy && (
              <div className="xray-light-msg">
                <div className="xray-light-msg-avatar ai">
                  <div className="xray-light-avatar-icon">AI</div>
                  AI
                </div>
                <div className="xray-light-msg-content xray-light-typing">
                  <span className="typing-dot"></span>
                  <span className="typing-dot"></span>
                  <span className="typing-dot"></span>
                </div>
              </div>
            )}
          </div>
          <form
            className="xray-light-chat-input"
            onSubmit={askQuestion}
            suppressHydrationWarning
          >
            <input
              placeholder="Ask about this document..."
              value={qaQuestion}
              onChange={(e) => setQaQuestion(e.target.value)}
            />
            <span className="cmd-k">CMD + K</span>
            <button
              type="submit"
              suppressHydrationWarning
              disabled={busy || !qaSessionId || !qaQuestion.trim()}
            >
              {busy ? "..." : "ASK"}
            </button>
          </form>
        </div>
      </div>

      {precedentsModalOpen && (
        <div
          className="xray-light-modal-overlay"
          onClick={() => setPrecedentsModalOpen(false)}
        >
          <div
            className="xray-light-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="xray-light-modal-header">
              <h3>Legal Precedents</h3>
              <button
                className="xray-light-modal-close"
                onClick={() => setPrecedentsModalOpen(false)}
              >
                ✕
              </button>
            </div>
            <div className="xray-light-modal-content">
              <p className="precedent-issue-label">
                ISSUE: <span>{selectedPrecedentIssue}</span>
              </p>

              {precedentsLoading ? (
                <div className="precedent-loading">
                  <div className="spinner"></div>
                  <p>Searching Indian Kanoon for relevant case law...</p>
                </div>
              ) : precedentsError ? (
                <p className="precedent-error">{precedentsError}</p>
              ) : precedentsList.length === 0 ? (
                <p className="precedent-empty">
                  No highly relevant precedents found.
                </p>
              ) : (
                <div className="precedent-list">
                  {precedentsList.map((p, i) => (
                    <div key={i} className="precedent-card">
                      <div className="precedent-card-header">
                        <h4>{p.title}</h4>
                        <span className="precedent-year">{p.year}</span>
                      </div>
                      <div className="precedent-court">{p.court}</div>
                      <p
                        className="precedent-headline"
                        dangerouslySetInnerHTML={{ __html: p.headline }}
                      />
                      <div className="precedent-footer">
                        <a
                          href={p.url}
                          target="_blank"
                          rel="noreferrer"
                          className="precedent-link"
                        >
                          Read Full Judgment ↗
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
