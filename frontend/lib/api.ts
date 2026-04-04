export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const TOKEN_KEY = "vakilai_token";

function readToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(TOKEN_KEY);
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
  auth = true,
): Promise<T> {
  const headers = new Headers(init.headers || {});
  const token = readToken();
  if (auth && token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // ignore json parse errors
    }
    throw new Error(detail);
  }
  return response.json();
}

export async function apiFetchBlob(
  path: string,
  init: RequestInit = {},
  auth = true,
): Promise<Blob> {
  const headers = new Headers(init.headers || {});
  const token = readToken();
  if (auth && token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // ignore json parse errors
    }
    throw new Error(detail);
  }
  return response.blob();
}

// Auth
export async function register(payload: {
  email: string;
  password: string;
  full_name: string;
  bar_council_id?: string;
  phone?: string;
}) {
  const data = await apiFetch<AuthResponse>(
    "/api/auth/register",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    false,
  );
  setToken(data.access_token);
  return data;
}

export async function login(payload: { email: string; password: string }) {
  const data = await apiFetch<AuthResponse>(
    "/api/auth/login",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    false,
  );
  setToken(data.access_token);
  return data;
}

export async function getMe() {
  return apiFetch<User>("/api/auth/me");
}

// Cases
export async function listCases() {
  return apiFetch<{ cases: CaseSummary[] }>("/api/cases");
}

export async function createCase(payload: CasePayload) {
  return apiFetch<CaseDetail>("/api/cases", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getCase(caseId: string) {
  return apiFetch<CaseDetail>(`/api/cases/${caseId}`);
}

export async function updateCase(
  caseId: string,
  payload: Partial<CasePayload>,
) {
  return apiFetch<CaseDetail>(`/api/cases/${caseId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deleteCase(caseId: string) {
  return apiFetch<{ status: string }>(`/api/cases/${caseId}`, {
    method: "DELETE",
  });
}

export async function getDocumentSuggestions(caseId: string) {
  return apiFetch<{ case_id: string; suggestions: DocumentSuggestion[] }>(
    `/api/cases/${caseId}/document-suggestions`,
  );
}

// Documents
export async function uploadDocument(caseId: string, file: File) {
  const form = new FormData();
  form.append("case_id", caseId);
  form.append("file", file);
  return apiFetch<{ document_id: string; status: string; message: string }>(
    "/api/documents/upload",
    {
      method: "POST",
      body: form,
    },
  );
}

export async function listCaseDocuments(caseId: string) {
  return apiFetch<{ documents: DocumentInfo[] }>(
    `/api/cases/${caseId}/documents`,
  );
}

export async function listDocuments() {
  return apiFetch<{ documents: DocumentInfo[] }>("/api/documents");
}

export async function getDocumentStatus(docId: string) {
  return apiFetch<DocumentStatus>(`/api/documents/${docId}/status`);
}

export async function deleteDocument(docId: string) {
  return apiFetch<{ status: string }>(`/api/documents/${docId}`, {
    method: "DELETE",
  });
}

export async function getDocumentPdf(docId: string) {
  return apiFetchBlob(`/api/documents/${docId}/file`);
}

// X-Ray + QA
export async function getInsights(docId: string) {
  return apiFetch<XRayInsights>(`/api/xray/${docId}/insights`);
}

export async function createQaSession(payload: {
  case_id: string;
  document_id: string;
}) {
  return apiFetch<{ session_id: string }>("/api/qa/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function askQaSession(sessionId: string, question: string) {
  return apiFetch<{
    answer: string;
    cannot_determine: boolean;
    retrieved_chunks: RetrievedChunk[];
  }>(`/api/qa/sessions/${sessionId}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

export async function getQaMessages(sessionId: string) {
  return apiFetch<{ session_id: string; messages: QaMessage[] }>(
    `/api/qa/sessions/${sessionId}/messages`,
  );
}

// Contradictions
export async function listContradictions(caseId: string) {
  return apiFetch<{
    case_id: string;
    total: number;
    high_count: number;
    medium_count: number;
    contradictions: Contradiction[];
  }>(`/api/cases/${caseId}/contradictions`);
}

export async function rerunContradictions(caseId: string) {
  return apiFetch<{ status: string }>(
    `/api/cases/${caseId}/contradictions/rerun`,
    {
      method: "POST",
    },
  );
}

// Brief
export async function getBrief(caseId: string) {
  return apiFetch<Brief>(`/api/cases/${caseId}/brief`);
}

export async function generateBrief(caseId: string) {
  return apiFetch<{ status: string; message: string }>(
    `/api/cases/${caseId}/brief/generate`,
    {
      method: "POST",
    },
  );
}

// Moot
export async function createMootSession(caseId: string) {
  return apiFetch<{ session_id: string; status: string; case_title: string }>(
    "/api/moot/sessions",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: caseId }),
    },
  );
}

export async function argueMootSession(sessionId: string, argument: string) {
  return apiFetch<{
    response: string;
    transcript_text?: string;
    exchange_count: number;
    session_active: boolean;
    weak_point_hit: boolean;
    argument_feedback?: string;
  }>(`/api/moot/sessions/${sessionId}/argue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ argument }),
  });
}

export async function argueMootSessionWithFeedback(
  sessionId: string,
  argument: string,
  includeFeedback: boolean = true,
) {
  return apiFetch<{
    response: string;
    exchange_count: number;
    session_active: boolean;
    weak_point_hit: boolean;
    argument_feedback?: string;
  }>(`/api/moot/sessions/${sessionId}/argue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ argument, include_feedback: includeFeedback }),
  });
}

export async function argueMootSessionFromAudio(
  sessionId: string,
  audioBlob: Blob,
  includeTts: boolean = false,
  includeFeedback: boolean = true,
) {
  const form = new FormData();
  form.append("file", audioBlob, "argument.webm");
  form.append("include_tts", includeTts ? "true" : "false");
  form.append("include_feedback", includeFeedback ? "true" : "false");

  return apiFetch<{
    response: string;
    transcript_text: string;
    exchange_count: number;
    session_active: boolean;
    weak_point_hit: boolean;
    argument_feedback?: string;
    tts_audio_base64?: string;
    tts_mime?: string;
    tts_error?: string;
  }>(`/api/moot/sessions/${sessionId}/argue-audio`, {
    method: "POST",
    body: form,
  });
}

export async function endMootSession(sessionId: string) {
  return apiFetch<{ summary: MootSummary }>(
    `/api/moot/sessions/${sessionId}/end`,
    {
      method: "POST",
    },
  );
}

export async function getMootMessages(sessionId: string) {
  return apiFetch<{
    session_id: string;
    exchange_count: number;
    status: string;
    messages: MootMessage[];
  }>(`/api/moot/sessions/${sessionId}/messages`);
}

export async function mootTextToSpeech(text: string) {
  return apiFetch<{
    tts_audio_base64?: string;
    tts_mime?: string;
    tts_error?: string;
  }>("/api/moot/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}

// Search
export async function hybridSearch(payload: {
  query: string;
  case_id: string;
  document_id?: string;
  top_k?: number;
}) {
  return apiFetch<{ query: string; results: RetrievedChunk[] }>(
    "/api/search/hybrid",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export async function searchStatutes(query: string) {
  return apiFetch<{ query: string; results: Statute[] }>(
    `/api/search/statutes?query=${encodeURIComponent(query)}`,
  );
}

// Types
export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  user: Pick<User, "id" | "email" | "full_name">;
}

export interface CasePayload {
  title: string;
  case_number?: string;
  court_name?: string;
  court_number?: string;
  opposing_party?: string;
  hearing_date?: string;
  hearing_time?: string;
  status?: "active" | "closed" | "adjourned";
  notes?: string;
}

export interface CaseSummary {
  id: string;
  title: string;
  case_number: string | null;
  court_name: string | null;
  hearing_date: string | null;
  status: string;
  document_count: number;
  ready_document_count: number;
  contradiction_count: number;
  has_brief: boolean;
  created_at: string;
}

export interface DocumentInfo {
  id: string;
  case_id: string;
  original_filename: string;
  processing_status: string;
  processing_error?: string | null;
  page_count: number | null;
  clause_count: number;
  ocr_confidence_avg: number | null;
  detected_language: string;
  was_translated: boolean;
  file_url?: string;
  created_at: string;
}

export interface CaseDetail {
  id: string;
  user_id: string;
  title: string;
  case_number: string | null;
  court_name: string | null;
  court_number: string | null;
  opposing_party: string | null;
  hearing_date: string | null;
  hearing_time: string | null;
  status: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  document_count?: number;
  ready_document_count?: number;
  contradiction_count?: number;
  has_brief?: boolean;
  documents?: DocumentInfo[];
}

export interface DocumentSuggestion {
  document_type: string;
  why_needed: string;
  starter_template: string;
}

export interface DocumentStatus {
  document_id: string;
  status: string;
  processing_error: string | null;
  page_count: number | null;
  ocr_confidence_avg: number | null;
  detected_language: string;
  was_translated: boolean;
  clause_count: number;
}

export interface Insight {
  id: string;
  clause_type: string;
  summary: string;
  anomaly_flag: "HIGH_RISK" | "MEDIUM_RISK" | "STANDARD";
  anomaly_reason: string | null;
  statutory_reference: string | null;
  statutory_id: string | null;
  page_number: number;
  bbox_x0: number;
  bbox_y0: number;
  bbox_x1: number;
  bbox_y1: number;
}

export interface XRayInsights {
  document_id: string;
  total_clauses: number;
  high_risk_count: number;
  medium_risk_count: number;
  standard_count: number;
  insights: Insight[];
}

export interface RetrievedChunk {
  id?: string;
  chunk_id?: string;
  document_id?: string;
  content?: string;
  page_number: number;
  bbox_x0: number;
  bbox_y0: number;
  bbox_x1: number;
  bbox_y1: number;
  rerank_score?: number;
  vector_score?: number;
  bm25_score?: number;
}

export interface QaMessage {
  role: "user" | "assistant";
  content: string;
  retrieved_chunks?: RetrievedChunk[];
  cannot_determine?: boolean;
  created_at: string;
}

export interface Contradiction {
  id: string;
  doc_a_id: string;
  doc_a_name: string;
  doc_b_id: string;
  doc_b_name: string;
  claim_a: string;
  claim_b: string;
  page_a: number | null;
  page_b: number | null;
  bbox_x0_a: number | null;
  bbox_y0_a: number | null;
  bbox_x1_a: number | null;
  bbox_y1_a: number | null;
  bbox_x0_b: number | null;
  bbox_y0_b: number | null;
  bbox_x1_b: number | null;
  bbox_y1_b: number | null;
  severity: "HIGH" | "MEDIUM";
  explanation: string;
  created_at: string;
}

export interface Brief {
  case_id: string;
  generated_at: string;
  documents_used: string[];
  core_contention: string;
  timeline: Array<{ date: string; event: string; source: string }>;
  offensive_arguments: Array<{
    argument: string;
    strength: string;
    basis: string;
    source: string;
  }>;
  defensive_arguments: Array<{
    anticipated_attack: string;
    counter: string;
    source: string;
  }>;
  weak_points: Array<{ issue: string; severity: string; source: string }>;
  key_legal_issues: string[];
  precedents: Array<{
    title: string;
    court: string;
    year: string;
    relevance_to: string;
    url: string;
    headline: string;
  }>;
}

export interface MootMessage {
  role: "user" | "assistant";
  content: string;
  weak_point_hit?: boolean;
  argument_feedback?: string;
  tts_audio_base64?: string;
  tts_mime?: string;
  tts_error?: string;
  created_at: string;
}

export interface PrecedentResult {
  title: string;
  court: string;
  year: string;
  relevance_to: string;
  citation: string;
  url: string;
  headline: string;
}

export async function searchPrecedents(
  query: string,
  limit: number = 3,
): Promise<PrecedentResult[]> {
  const data = await apiFetch<{ query: string; results: PrecedentResult[] }>(
    `/api/search/precedents?query=${encodeURIComponent(query)}&limit=${limit}`,
  );
  return data.results || [];
}

export interface MootSummary {
  strong_arguments: string[];
  weak_arguments: string[];
  weak_points_hit: number;
  coaching_tip: string;
  overall_assessment: "STRONG" | "NEEDS_WORK" | "DEVELOPING";
}

export interface Statute {
  id: string;
  act: string;
  section: string;
  title: string;
  summary: string;
}
