"use client";

import { useEffect, useRef, useState } from "react";
import {
  CaseSummary,
  MootMessage,
  MootSummary,
  MootSessionHistoryItem,
  argueMootSessionFromAudio,
  argueMootSessionWithFeedback,
  createMootSession,
  endMootSession,
  getMootMessages,
  getMootCaseSessionsHistory,
  getMootSessionHistory,
  listCases,
  mootTextToSpeech,
} from "@/lib/api";

import MootSessionsSidebar from "@/components/MootSessionsSidebar";

export default function MootCourtPage() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [sessionStatus, setSessionStatus] = useState<"" | "active" | "ended">("");
  const [sessionsHistory, setSessionsHistory] = useState<MootSessionHistoryItem[]>([]);
  const [sessionsCollapsed, setSessionsCollapsed] = useState(false);
  const [messages, setMessages] = useState<MootMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isMicProcessing, setIsMicProcessing] = useState(false);
  const [ttsLoadingKey, setTtsLoadingKey] = useState<string | null>(null);
  const [summary, setSummary] = useState<MootSummary | null>(null);
  const [error, setError] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<BlobPart[]>([]);
  const cancelRecordingRef = useRef(false);

  useEffect(() => {
    void (async () => {
      try {
        const data = await listCases();
        setCases(data.cases);
        const queryCase = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("case") : null;
        setSelectedCaseId(queryCase || data.cases[0]?.id || "");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load cases");
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedCaseId) {
      setSessionsHistory([]);
      setSessionId("");
      setSessionStatus("");
      setMessages([]);
      setSummary(null);
      return;
    }

    void (async () => {
      setError("");
      try {
        const history = await getMootCaseSessionsHistory(selectedCaseId);
        setSessionsHistory(history.sessions || []);

        // If the current session doesn't belong to this case anymore, clear it.
        if (sessionId && !history.sessions?.some((s) => s.session_id === sessionId)) {
          setSessionId("");
          setSessionStatus("");
          setMessages([]);
          setSummary(null);
        }
      } catch (err) {
        setSessionsHistory([]);
        setError(err instanceof Error ? err.message : "Could not load session history");
      }
    })();
    // Intentionally *not* depending on sessionId to avoid reloading history on every message send.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCaseId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const readOnlySession = Boolean(sessionId && sessionStatus === "ended");

  async function reloadHistory(caseId: string) {
    if (!caseId) return;
    try {
      const history = await getMootCaseSessionsHistory(caseId);
      setSessionsHistory(history.sessions || []);
    } catch {
      // Non-fatal: keep current UI state.
    }
  }

  async function openSession(targetSessionId: string) {
    if (!targetSessionId) return;
    setBusy(true);
    setError("");
    try {
      const data = await getMootSessionHistory(targetSessionId);
      setSessionId(data.session_id);
      setSessionStatus(data.status);
      setMessages(data.messages || []);
      setSummary(data.summary || null);
      setInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open session");
    } finally {
      setBusy(false);
    }
  }

  async function startSession() {
    if (!selectedCaseId) return;
    setBusy(true);
    setError("");
    setSummary(null);
    try {
      const created = await createMootSession(selectedCaseId);
      setSessionId(created.session_id);
      setSessionStatus("active");
      const transcript = await getMootMessages(created.session_id);
      setMessages(transcript.messages);
      setSessionStatus(transcript.status === "ended" ? "ended" : "active");
      await reloadHistory(selectedCaseId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start session");
    } finally {
      setBusy(false);
    }
  }

  async function sendArgument(event: React.FormEvent) {
    event.preventDefault();
    if (!sessionId || readOnlySession || !input.trim()) return;
    const value = input.trim();
    setInput("");
    setBusy(true);
    setError("");
    try {
      const result = await argueMootSessionWithFeedback(sessionId, value, true);
      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          content: value,
          argument_feedback: result.argument_feedback,
          created_at: new Date().toISOString(),
        },
        {
          role: "assistant",
          content: result.response,
          weak_point_hit: result.weak_point_hit,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send argument");
    } finally {
      setBusy(false);
    }
  }

  async function endSession() {
    // Stop any active recording before ending.
    cancelRecordingRef.current = true;
    try {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
    } catch {
      // ignore
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    mediaRecorderRef.current = null;
    audioChunksRef.current = [];

    if (!sessionId || readOnlySession) return;
    const endedSessionId = sessionId;
    setBusy(true);
    setError("");
    try {
      const result = await endMootSession(endedSessionId);
      setSummary(result.summary);
      setSessionStatus("ended");
      const transcript = await getMootMessages(endedSessionId);
      setMessages(transcript.messages);

      await reloadHistory(selectedCaseId);

      // Reset UI so the user can start a new session.
      setSessionId("");
      setSessionStatus("");
      setIsRecording(false);
      setIsMicProcessing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not end session");
    } finally {
      setBusy(false);
    }
  }

  async function playTts(ttsAudioBase64: string, ttsMime: string) {
    const audioUrl = `data:${ttsMime};base64,${ttsAudioBase64}`;
    const audio = new Audio(audioUrl);
    try {
      await audio.play();
    } catch (err) {
      const name = err instanceof Error ? err.name : "";
      // Autoplay blocks are common; UI provides a manual Play fallback.
      if (name === "NotAllowedError") return;
      setError("Could not play TTS audio.");
    }
  }

  async function playOrGenerateTtsForAssistantMessage(message: MootMessage, index: number) {
    if (message.role !== "assistant") return;
    const key = `${message.created_at}-${index}`;
    if (ttsLoadingKey) return;

    // If we already have cached audio, just play it.
    if (message.tts_audio_base64 && message.tts_mime) {
      await playTts(message.tts_audio_base64, message.tts_mime);
      return;
    }

    setTtsLoadingKey(key);
    setError("");
    try {
      const result = await mootTextToSpeech(message.content);
      setMessages((prev) =>
        prev.map((m, i) =>
          i === index
            ? {
                ...m,
                tts_audio_base64: result.tts_audio_base64,
                tts_mime: result.tts_mime,
                tts_error: result.tts_error,
              }
            : m
        )
      );
      if (result.tts_audio_base64 && result.tts_mime) {
        await playTts(result.tts_audio_base64, result.tts_mime);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate audio");
    } finally {
      setTtsLoadingKey(null);
    }
  }

  async function startRecording() {
    if (!sessionId || readOnlySession || isRecording || busy || isMicProcessing) return;
    setError("");
    setIsRecording(true);
    setBusy(false);
    setIsMicProcessing(false);
    cancelRecordingRef.current = false;

    const activeSessionId = sessionId;
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("Microphone not supported in this browser.");
      }
      if (!window.MediaRecorder) {
        throw new Error("MediaRecorder not supported in this browser.");
      }

      // Request mic access.
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      // Pick a supported mimeType for best compatibility.
      const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
      let mimeType: string | undefined = undefined;
      for (const c of candidates) {
        if (window.MediaRecorder.isTypeSupported(c)) {
          mimeType = c;
          break;
        }
      }

      audioChunksRef.current = [];
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      recorder.onstop = async () => {
        const chunks = audioChunksRef.current;
        audioChunksRef.current = [];

        try {
          if (cancelRecordingRef.current) {
            return;
          }
          const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
          const result = await argueMootSessionFromAudio(activeSessionId, blob, ttsEnabled, true);

          setMessages((prev) => [
            ...prev,
            {
              role: "user",
              content: result.transcript_text,
              argument_feedback: result.argument_feedback,
              created_at: new Date().toISOString(),
            },
            {
              role: "assistant",
              content: result.response,
              weak_point_hit: result.weak_point_hit,
              tts_audio_base64: result.tts_audio_base64,
              tts_mime: result.tts_mime,
              tts_error: result.tts_error,
              created_at: new Date().toISOString(),
            },
          ]);

          await reloadHistory(selectedCaseId);

          if (result.tts_audio_base64 && result.tts_mime) {
            void playTts(result.tts_audio_base64, result.tts_mime);
          }
        } catch (err) {
          setError(err instanceof Error ? err.message : "Could not transcribe and send argument");
        } finally {
          streamRef.current?.getTracks().forEach((t) => t.stop());
          streamRef.current = null;
          mediaRecorderRef.current = null;
          if (!cancelRecordingRef.current) {
            setBusy(false);
          }
          setIsMicProcessing(false);
          setIsRecording(false);
          cancelRecordingRef.current = false;
        }
      };

      recorder.start();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start microphone recording");
      setBusy(false);
      setIsMicProcessing(false);
      setIsRecording(false);
    }
  }

  function stopRecording() {
    if (!mediaRecorderRef.current) return;
    try {
      setBusy(true);
      setIsMicProcessing(true);
      // Flip UI immediately so the Stop button becomes "Processing..." while we wait for `onstop`.
      setIsRecording(false);
      mediaRecorderRef.current.stop();
    } catch {
      // ignore; onstop may not fire
      setBusy(false);
      setIsMicProcessing(false);
      setIsRecording(false);
    }
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: sessionsCollapsed ? "76px minmax(0, 1fr)" : "340px minmax(0, 1fr)",
        gap: 16,
        alignItems: "start",
      }}
    >
      <MootSessionsSidebar
        sessions={sessionsHistory}
        activeSessionId={sessionId}
        collapsed={sessionsCollapsed}
        onToggleCollapsed={() => setSessionsCollapsed((v) => !v)}
        onSelectSession={(id) => void openSession(id)}
        onCreateNewSession={() => void startSession()}
        disabled={busy || !selectedCaseId}
      />

      <div>
        <div className="page-header">
          <h1>Moot Court Mode</h1>
          <p>Multi-turn opposing counsel simulation grounded in your case files.</p>
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

            {!sessionId ? (
              <button className="btn btn-primary" onClick={startSession} disabled={busy || !selectedCaseId}>
                {busy ? "Starting..." : "Start Session"}
              </button>
            ) : sessionStatus === "active" ? (
              <button className="btn btn-secondary" onClick={endSession} disabled={busy || isRecording || isMicProcessing}>
                End Session
              </button>
            ) : (
              <button className="btn btn-primary" onClick={startSession} disabled={busy || !selectedCaseId}>
                {busy ? "Starting..." : "New Session"}
              </button>
            )}
          </div>
          {error ? <p style={{ marginTop: 10, color: "var(--risk-high)" }}>{error}</p> : null}
          {readOnlySession ? <p className="muted" style={{ marginTop: 10 }}>Viewing an ended session (read-only).</p> : null}
        </section>

        <div className="chat-container">
        <div className="chat-header">
          <div>
            <h3 style={{ fontSize: "0.95rem", fontWeight: 700 }}>Opposing Counsel</h3>
            <p style={{ fontSize: "0.78rem", color: "var(--text-tertiary)" }}>
              Session: {sessionId ? sessionId.slice(0, 8) : "not started"}
            </p>
          </div>
          <span className={`badge ${busy ? "badge-medium-risk" : "badge-standard"}`}>{busy ? "Processing" : "Ready"}</span>
        </div>

        <div className="chat-messages">
          {messages.length === 0 ? (
            <div className="muted" style={{ textAlign: "center", marginTop: 80 }}>
              Start a session and submit your opening argument (text or microphone).
            </div>
          ) : (
            messages.map((message, index) => (
              <article key={`${message.created_at}-${index}`} className={`chat-message ${message.role === "user" ? "user" : "ai"}`}>
                {message.role === "assistant" ? <div className="message-label">Opposing Counsel</div> : null}
                <div>{message.content}</div>
                {message.role === "user" && message.argument_feedback ? (
                  <div style={{ marginTop: 8, fontSize: "0.78rem", color: "var(--text-tertiary)" }}>
                    Feedback: {message.argument_feedback}
                  </div>
                ) : null}
                {message.role === "assistant" && message.tts_error ? (
                  <div style={{ marginTop: 8, fontSize: "0.78rem", color: "var(--text-tertiary)" }}>
                    Audio: {message.tts_error}
                  </div>
                ) : null}
                {message.role === "assistant" ? (
                  <div style={{ marginTop: 10 }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => void playOrGenerateTtsForAssistantMessage(message, index)}
                      disabled={busy || isRecording || isMicProcessing || ttsLoadingKey === `${message.created_at}-${index}`}
                    >
                      {ttsLoadingKey === `${message.created_at}-${index}`
                        ? "Processing..."
                        : message.tts_audio_base64 && message.tts_mime
                          ? "Play audio"
                          : "Audio"}
                    </button>
                  </div>
                ) : null}
                {message.weak_point_hit ? (
                  <div style={{ marginTop: 8, fontSize: "0.78rem", color: "var(--risk-medium)" }}>Weak point exploited</div>
                ) : null}
              </article>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

          <div style={{ marginTop: 14, marginBottom: 10, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <label className="field-inline" style={{ gap: 8 }}>
              <input
                type="checkbox"
                checked={ttsEnabled}
                onChange={(e) => setTtsEnabled(e.target.checked)}
                  disabled={!sessionId || readOnlySession || busy || isRecording || isMicProcessing}
              />
              <span style={{ fontSize: "0.9rem" }}>Speak opponent response</span>
            </label>

            {!isRecording && !isMicProcessing ? (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={!sessionId || readOnlySession || busy}
                onClick={startRecording}
              >
                Start Mic
              </button>
            ) : isRecording ? (
              <button
                type="button"
                className="btn btn-danger"
                disabled={!sessionId}
                onClick={stopRecording}
              >
                Stop & Send
              </button>
            ) : (
              <button type="button" className="btn btn-secondary" disabled>
                Processing...
              </button>
            )}
          </div>

        <form className="chat-input-area" onSubmit={sendArgument}>
          <textarea
            className="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="State your argument..."
            disabled={!sessionId || readOnlySession || busy || isRecording || isMicProcessing}
          />
          <button className="btn btn-primary" disabled={!sessionId || readOnlySession || busy || isRecording || isMicProcessing || !input.trim()}>
            Submit
          </button>
        </form>
      </div>

      {summary ? (
        <section className="card" style={{ marginTop: 16 }}>
          <h2 className="section-title">Session Summary</h2>
          <p className="muted">Overall assessment: {summary.overall_assessment}</p>
          <p style={{ marginTop: 8 }}>{summary.coaching_tip}</p>
          <p style={{ marginTop: 8 }}>Weak points hit: {summary.weak_points_hit}</p>
        </section>
      ) : null}
      </div>
    </div>
  );
}
