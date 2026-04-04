"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CasePayload,
  CaseSummary,
  DocumentInfo,
  DocumentSuggestion,
  clearToken,
  createCase,
  generateBrief,
  getDocumentSuggestions,
  getMe,
  getBrief,
  listCaseDocuments,
  listCases,
  login,
  register,
  uploadDocument,
  deleteDocument,
} from "@/lib/api";

type AuthMode = "login" | "register";

const emptyCaseForm: CasePayload = {
  title: "",
  case_number: "",
  court_name: "",
  court_number: "",
  opposing_party: "",
  hearing_date: "",
  hearing_time: "",
  notes: "",
  status: "active",
};

function toIsoUtc(localDateTime: string | undefined) {
  if (!localDateTime) return undefined;
  const parsed = new Date(localDateTime);
  if (Number.isNaN(parsed.getTime())) return undefined;
  return parsed.toISOString();
}

// ✅ Status badge with live pulse animation
function StatusBadge({ status }: { status: string }) {
  const config: Record<
    string,
    { label: string; color: string; animate: boolean }
  > = {
    uploaded: { label: "Uploaded", color: "#888", animate: false },
    ocr_running: { label: "OCR Running", color: "#f5a623", animate: true },
    analyzing: { label: "Analyzing", color: "#4a90e2", animate: true },
    ready: { label: "Ready", color: "#27ae60", animate: false },
    failed: { label: "Failed", color: "#e74c3c", animate: false },
  };

  const cfg = config[status] ?? {
    label: status,
    color: "#888",
    animate: false,
  };

  return (
    <span
      style={{
        color: cfg.color,
        fontWeight: 600,
        display: "inline-block",
        animation: cfg.animate
          ? "vakil-pulse 1.2s ease-in-out infinite"
          : "none",
      }}
    >
      {cfg.label}
      <style>{`
        @keyframes vakil-pulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.35; }
        }
      `}</style>
    </span>
  );
}

export default function DashboardPage() {
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  const [userName, setUserName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");

  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [caseForm, setCaseForm] = useState<CasePayload>(emptyCaseForm);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [briefSummary, setBriefSummary] = useState("");
  const [docSuggestions, setDocSuggestions] = useState<DocumentSuggestion[]>(
    [],
  );

  // ✅ This triggers a fresh polling cycle whenever a new upload happens
  const [pollingTrigger, setPollingTrigger] = useState(0);

  // ✅ Track uploading file for UI feedback
  const [uploadingFileName, setUploadingFileName] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedCase = useMemo(
    () => cases.find((item) => item.id === selectedCaseId) || null,
    [cases, selectedCaseId],
  );

  useEffect(() => {
    let cancelled = false;
    const bootstrap = async () => {
      try {
        const me = await getMe();
        if (!cancelled) setUserName(me.full_name);
      } catch {
        if (!cancelled) clearToken();
      } finally {
        if (!cancelled) setAuthLoading(false);
      }
    };
    bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshCases = useCallback(async () => {
    const data = await listCases();
    setCases(data.cases);
    if (!selectedCaseId && data.cases.length > 0) {
      setSelectedCaseId(data.cases[0].id);
    }
  }, [selectedCaseId]);

  const refreshDocuments = useCallback(async (caseId: string) => {
    const data = await listCaseDocuments(caseId);
    setDocuments([...data.documents]);
  }, []);

  const refreshSuggestions = useCallback(async (caseId: string) => {
    const data = await getDocumentSuggestions(caseId);
    setDocSuggestions([...data.suggestions]);
  }, []);

  useEffect(() => {
    if (!userName) return;
    void refreshCases();
  }, [userName, refreshCases]);

  useEffect(() => {
    if (!selectedCaseId) {
      setDocuments([]);
      setDocSuggestions([]);
      return;
    }
    void refreshDocuments(selectedCaseId);
    void refreshSuggestions(selectedCaseId);
  }, [selectedCaseId, refreshDocuments, refreshSuggestions]);

  // ✅ Polling effect — restarts on new upload via pollingTrigger
  useEffect(() => {
    if (!selectedCaseId) return;

    // Immediately fetch once so status appears right away after upload
    void listCaseDocuments(selectedCaseId).then((data) => {
      setDocuments([...data.documents]);
    });

    const interval = setInterval(async () => {
      const data = await listCaseDocuments(selectedCaseId);
      setDocuments([...data.documents]);

      const stillProcessing = data.documents.some(
        (doc) =>
          doc.processing_status !== "ready" &&
          doc.processing_status !== "failed",
      );

      // Stop polling only when everything is done
      if (!stillProcessing) {
        clearInterval(interval);
      }

      const sugg = await getDocumentSuggestions(selectedCaseId);
      setDocSuggestions([...sugg.suggestions]);
    }, 2000); // polls every 2 seconds

    return () => clearInterval(interval);
  }, [selectedCaseId, pollingTrigger]); // ✅ pollingTrigger restarts this on upload

  async function handleDeleteDocument(docId: string) {
    if (!selectedCaseId) return;
    const confirmDelete = window.confirm(
      "Are you sure you want to delete this document?",
    );
    if (!confirmDelete) return;
    setBusy(true);
    setMessage("");
    try {
      await deleteDocument(docId);
      setMessage("Document deleted successfully.");
      await refreshDocuments(selectedCaseId);
      await refreshCases();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleAuthSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setAuthError("");
    try {
      const payload = { email, password };
      if (authMode === "login") {
        const res = await login(payload);
        setUserName(res.user.full_name);
      } else {
        const res = await register({
          ...payload,
          full_name: fullName.trim() || "Advocate",
        });
        setUserName(res.user.full_name);
      }
    } catch (error) {
      setAuthError(
        error instanceof Error ? error.message : "Authentication failed",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateCase(event: React.FormEvent) {
    event.preventDefault();
    setMessage("");
    setBusy(true);
    try {
      if (!caseForm.title?.trim()) {
        setMessage("Case title is required.");
        return;
      }
      await createCase({
        ...caseForm,
        hearing_date: toIsoUtc(caseForm.hearing_date),
      });
      setCaseForm(emptyCaseForm);
      await refreshCases();
      setMessage("Case created.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Could not create case",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(file: File) {
    if (!selectedCaseId) return;
    setBusy(true);
    setMessage("");
    setUploadingFileName(file.name);
    try {
      await uploadDocument(selectedCaseId, file);
      setMessage("Document uploaded and queued for processing.");
      await Promise.all([refreshCases(), refreshDocuments(selectedCaseId)]);
      // ✅ Bump trigger — restarts polling so new doc status updates live
      setPollingTrigger((prev) => prev + 1);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setBusy(false);
      setUploadingFileName("");
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  async function handleGenerateBrief() {
    if (!selectedCaseId) return;
    setBusy(true);
    setMessage("");
    try {
      await generateBrief(selectedCaseId);
      setMessage("Brief generation started.");
      setTimeout(() => {
        void handleLoadBrief();
      }, 1200);
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "Could not start brief generation",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleLoadBrief() {
    if (!selectedCaseId) return;
    setBusy(true);
    setMessage("");
    try {
      const data = await getBrief(selectedCaseId);
      setBriefSummary(data.core_contention);
      setMessage(`Brief loaded (${data.timeline.length} timeline events).`);
    } catch (error) {
      setBriefSummary("");
      setMessage(error instanceof Error ? error.message : "Brief unavailable");
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    clearToken();
    setUserName("");
    setCases([]);
    setSelectedCaseId("");
    setDocuments([]);
    setDocSuggestions([]);
  }

  if (authLoading) {
    return (
      <div className="page-header">
        <h1>Dashboard</h1>
        <p>Loading workspace...</p>
      </div>
    );
  }

  if (!userName) {
    return (
      <div>
        <div className="page-header">
          <h1>VakilAI Access</h1>
          <p>Sign in to open your isolated case vault.</p>
        </div>
        <form
          className="card"
          style={{ maxWidth: 520 }}
          onSubmit={handleAuthSubmit}
        >
          <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
            <button
              type="button"
              className={`btn ${authMode === "login" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setAuthMode("login")}
            >
              Login
            </button>
            <button
              type="button"
              className={`btn ${authMode === "register" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setAuthMode("register")}
            >
              Register
            </button>
          </div>

          <label className="field-label">Email</label>
          <input
            className="field-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            required
          />

          <label className="field-label">Password</label>
          <input
            className="field-input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            type="password"
            minLength={8}
            required
          />

          {authMode === "register" && (
            <>
              <label className="field-label">Full name</label>
              <input
                className="field-input"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                type="text"
                required
              />
            </>
          )}

          {authError ? (
            <p
              style={{
                color: "var(--risk-high)",
                marginTop: 10,
                fontSize: "0.85rem",
              }}
            >
              {authError}
            </p>
          ) : null}
          <button
            type="submit"
            className="btn btn-primary"
            style={{ marginTop: 16 }}
            disabled={busy}
          >
            {busy
              ? "Please wait..."
              : authMode === "login"
                ? "Sign In"
                : "Create Account"}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="white-theme">
      <div className="page-header">
        <h1>Case Dashboard</h1>
        <p>{userName} | Cases sorted by next hearing date</p>
        <div style={{ marginTop: 10 }}>
          <button className="btn btn-secondary" onClick={logout}>
            Log out
          </button>
        </div>
      </div>

      <div className="grid-two">
        <section className="card">
          <h2 className="section-title">Create Case</h2>
          <form onSubmit={handleCreateCase}>
            <label className="field-label">Case title</label>
            <input
              className="field-input"
              value={caseForm.title || ""}
              onChange={(e) =>
                setCaseForm((prev) => ({ ...prev, title: e.target.value }))
              }
              required
            />

            <label className="field-label">Case number</label>
            <input
              className="field-input"
              value={caseForm.case_number || ""}
              onChange={(e) =>
                setCaseForm((prev) => ({
                  ...prev,
                  case_number: e.target.value,
                }))
              }
            />

            <label className="field-label">Court name</label>
            <input
              className="field-input"
              value={caseForm.court_name || ""}
              onChange={(e) =>
                setCaseForm((prev) => ({ ...prev, court_name: e.target.value }))
              }
            />

            <label className="field-label">Next hearing date &amp; time</label>
            <input
              className="field-input"
              type="datetime-local"
              step={60}
              value={caseForm.hearing_date || ""}
              onChange={(e) =>
                setCaseForm((prev) => ({
                  ...prev,
                  hearing_date: e.target.value,
                }))
              }
            />
            <p className="muted" style={{ marginTop: 6 }}>
              Saved in UTC timezone automatically.
            </p>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ marginTop: 16 }}
              disabled={busy}
            >
              Create case
            </button>
          </form>
        </section>

        <section className="card">
          <h2 className="section-title">Your Cases</h2>
          <div className="list-stack">
            {cases.length === 0 ? (
              <p className="muted">No cases yet.</p>
            ) : (
              cases.map((item) => (
                <button
                  key={item.id}
                  className={`list-item ${selectedCaseId === item.id ? "active" : ""}`}
                  onClick={() => setSelectedCaseId(item.id)}
                >
                  <div className="list-item-title">{item.title}</div>
                  <div className="list-item-meta">
                    {item.hearing_date
                      ? new Date(item.hearing_date).toLocaleString()
                      : "No hearing date"}
                  </div>
                  <div className="list-item-meta">
                    Docs {item.document_count} | Ready{" "}
                    {item.ready_document_count} | Contradictions{" "}
                    {item.contradiction_count}
                  </div>
                </button>
              ))
            )}
          </div>
        </section>
      </div>

      <section className="card" style={{ marginTop: 20 }}>
        <h2 className="section-title">Case Documents</h2>
        {selectedCase ? (
          <>
            <div className="upload-area" style={{ padding: "24px" }}>
              <p>Upload PDF to &ldquo;{selectedCase.title}&rdquo;</p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void handleUpload(file);
                }}
                disabled={busy}
              />
            </div>

            <div className="list-stack" style={{ marginTop: 14 }}>
              {uploadingFileName && (
                <div
                  key="uploading"
                  className="list-item static uploading-placeholder"
                >
                  <div className="list-item-title">{uploadingFileName}</div>
                  <div
                    className="list-item-meta"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                    }}
                  >
                    <span
                      style={{ animation: "pulse 1.5s ease-in-out infinite" }}
                    >
                      ●{" "}
                    </span>
                    <span>Uploading and processing...</span>
                  </div>
                  <style>{`
                    @keyframes pulse {
                      0%, 100% { opacity: 0.6; }
                      50% { opacity: 1; }
                    }
                  `}</style>
                </div>
              )}
              {documents.length === 0 && !uploadingFileName ? (
                <p className="muted">
                  No documents uploaded for this case yet.
                </p>
              ) : (
                documents.map((doc) => (
                  <div key={doc.id} className="list-item static">
                    <div className="list-item-title">
                      {doc.original_filename}
                    </div>
                    <div className="list-item-meta">
                      {/* ✅ Live animated status badge */}
                      <StatusBadge status={doc.processing_status} />
                      {" | "}Pages: {doc.page_count ?? "?"} | Clauses:{" "}
                      {doc.clause_count}
                    </div>
                    {doc.processing_status === "failed" &&
                    doc.processing_error ? (
                      <div
                        className="list-item-meta"
                        style={{ color: "var(--risk-high)" }}
                      >
                        Failure reason: {doc.processing_error}
                      </div>
                    ) : null}
                    <div
                      style={{
                        display: "flex",
                        gap: 10,
                        marginTop: 8,
                        flexWrap: "wrap",
                      }}
                    >
                      <Link
                        className="btn btn-secondary"
                        href={`/xray?case=${selectedCase.id}&doc=${doc.id}`}
                      >
                        Open X-Ray
                      </Link>
                      {/* <Link className="btn btn-secondary" href={`/hearing-brief?case=${selectedCase.id}`}>
                        Hearing Brief
                      </Link>
                      <Link className="btn btn-secondary" href={`/contradictions?case=${selectedCase.id}`}>
                        View Contradictions
                      </Link>
                      <Link className="btn btn-secondary" href={`/moot-court?case=${selectedCase.id}`}>
                        Open Moot
                      </Link> */}
                      <button
                        className="btn btn-secondary"
                        style={{
                          borderColor: "rgba(234,106,106,0.45)",
                          background: "rgba(234,106,106,0.1)",
                          color: "var(--risk-high)",
                        }}
                        onClick={() => handleDeleteDocument(doc.id)}
                        disabled={busy}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </>
        ) : (
          <p className="muted">Select a case to manage documents.</p>
        )}
        {message ? (
          <p style={{ marginTop: 12, color: "var(--text-secondary)" }}>
            {message}
          </p>
        ) : null}
      </section>
      {/* 
      <section className="card" style={{ marginTop: 20 }}>
        <h2 className="section-title">Pre-Flight Brief</h2>
        {selectedCase ? (
          <>
            <div className="row-wrap">
              <button className="btn btn-primary" onClick={handleGenerateBrief} disabled={busy}>
                Generate Brief
              </button>
              <button className="btn btn-secondary" onClick={handleLoadBrief} disabled={busy}>
                Load Brief
              </button>
            </div>
            {briefSummary ? (
              <p style={{ marginTop: 12 }}>{briefSummary}</p>
            ) : (
              <p className="muted" style={{ marginTop: 12 }}>No brief loaded yet.</p>
            )}
          </>
        ) : (
          <p className="muted">Select a case to manage hearing brief.</p>
        )}
      </section> */}

      {/* <section className="card" style={{ marginTop: 20 }}>
        <h2 className="section-title">Suggested Next Documents</h2>
        {selectedCase ? (
          docSuggestions.length === 0 ? (
            <p className="muted">No suggestions available.</p>
          ) : (
            <div className="list-stack">
              {docSuggestions.map((item, index) => (
                <article key={`${item.document_type}-${index}`} className="list-item static">
                  <div className="list-item-title">{item.document_type}</div>
                  <div className="list-item-meta">{item.why_needed}</div>
                  <pre className="template-box">{item.starter_template}</pre>
                </article>
              ))}
            </div>
          )
        ) : (
          <p className="muted">Select a case to view document suggestions.</p>
        )}
      </section> */}
    </div>
  );
}
