"use client";

import { useRouter, useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { AppSidebar } from "@/components/app/AppSidebar";
import { api } from "@/lib/api";
import { clearAuthToken, getAuthToken } from "@/lib/session";
import type { Entitlements, Me, ThreadDetail, ThreadSummary, Usage } from "@/lib/types";

function draftKey(threadId: string): string {
  return `wsai_draft_${threadId}`;
}

export default function AuthChatPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const threadIdFromRoute = Array.isArray(params.id) ? params.id[0] : params.id;

  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);

  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [activeThread, setActiveThread] = useState<ThreadDetail | null>(null);
  const [draft, setDraft] = useState("");

  const [loadingPage, setLoadingPage] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = getAuthToken();
    if (!t) {
      router.replace("/login");
      return;
    }
    setToken(t);
  }, [router]);

  useEffect(() => {
    if (!token) return;

    setLoadingPage(true);
    setError(null);

    Promise.all([api.me(token), api.entitlements(token), api.usage(token), api.listThreads(token)])
      .then(async ([m, e, u, t]) => {
        setMe(m);
        setEntitlements(e);
        setUsage(u);
        setThreads(t);

        const preferred = t.find((x) => x.id === threadIdFromRoute)?.id || t[0]?.id || null;
        if (!preferred) {
          const created = await api.createThread(token, "New chat");
          router.replace(`/app/chat/${created.id}`);
          return;
        }

        const detail = await api.getThread(token, preferred);
        setActiveThread(detail);
        setDraft(window.localStorage.getItem(draftKey(preferred)) || "");
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : "Failed to load app";
        const lower = msg.toLowerCase();
        const authError =
          lower.includes("invalid token") ||
          lower.includes("missing bearer token") ||
          lower.includes("wrong token") ||
          lower.includes("user not found");
        if (authError) {
          clearAuthToken();
          router.replace("/login");
          return;
        }
        setError(msg);
      })
      .finally(() => setLoadingPage(false));
  }, [token, threadIdFromRoute, router]);

  useEffect(() => {
    if (!activeThread) return;
    window.localStorage.setItem(draftKey(activeThread.id), draft);
  }, [activeThread, draft]);

  const openThread = async (id: string) => {
    if (!token) return;
    setError(null);
    try {
      const detail = await api.getThread(token, id);
      setActiveThread(detail);
      setDraft(window.localStorage.getItem(draftKey(id)) || "");
      router.replace(`/app/chat/${id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to open thread");
    }
  };

  const onCreateThread = async () => {
    if (!token) return;
    setError(null);
    try {
      const created = await api.createThread(token, "New chat");
      const list = await api.listThreads(token);
      setThreads(list);
      router.replace(`/app/chat/${created.id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create thread");
    }
  };

  const onSend = async (override?: string) => {
    if (!token || !activeThread) return;
    const text = (override ?? draft).trim();
    if (!text || sending) return;

    setSending(true);
    setError(null);

    const optimisticUser = { id: `u_${Date.now()}`, role: "user" as const, content: text };
    setActiveThread((prev) =>
      prev ? { ...prev, messages: [...prev.messages, optimisticUser] } : prev,
    );
    setDraft("");

    try {
      const resp = await api.chat(token, text, activeThread.id);
      const updated = await api.getThread(token, resp.thread_id);
      setActiveThread(updated);
      const [nextUsage, nextThreads] = await Promise.all([api.usage(token), api.listThreads(token)]);
      setUsage(nextUsage);
      setThreads(nextThreads);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Send failed");
      setActiveThread((prev) =>
        prev
          ? { ...prev, messages: prev.messages.filter((m) => m.id !== optimisticUser.id) }
          : prev,
      );
      setDraft(text);
    } finally {
      setSending(false);
    }
  };

  const dayUsageText = useMemo(() => {
    if (!usage?.day) return "-";
    return `${usage.day.used}/${usage.day.limit ?? "∞"}`;
  }, [usage]);

  if (loadingPage) {
    return <main className="ws-app-shell"><div className="ws-app-loading">Loading your cockpit...</div></main>;
  }

  return (
    <main className="ws-app-shell">
      <AppSidebar
        planName={entitlements?.plan_name || "Free"}
        dayUsageText={dayUsageText}
        threads={threads}
        activeThreadId={activeThread?.id || null}
        onOpenThread={openThread}
        onCreateThread={onCreateThread}
      />

      <section className="ws-app-main">
        <div className="ws-app-topbar">
          <div className="ws-app-title">{activeThread?.title || "New chat"}</div>
          <div className="ws-app-user">{me?.email}</div>
        </div>

        {error ? <div className="ws-error">{error}</div> : null}

        <div className="ws-app-messages">
          {!activeThread || activeThread.messages.length === 0 ? (
            <div className="ws-empty-state">
              <h3>Start your strategy thread</h3>
              <p>Ask about sentiment, structure, invalidation, or risk-aware entries.</p>
            </div>
          ) : (
            activeThread.messages.map((m) => (
              <div key={m.id} className={`ws-msg ${m.role === "user" ? "user" : "assistant"}`}>
                <div className="ws-msg-role">{m.role}</div>
                <div className="ws-msg-content">{m.content}</div>
              </div>
            ))
          )}
        </div>

        <div className="ws-app-composer">
          <div className="ws-compose-head">
            <span>Ask WSAI</span>
            <span style={{ fontFamily: "var(--font-ibm-plex-mono)" }}>mode: chat</span>
          </div>
          <div className="ws-compose">
            <textarea
              placeholder="Ask anything crypto: BTC sentiment today, SOL 4h RSI, or build me a low-risk swing setup."
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={3}
            />
            <button className="ws-send" type="button" onClick={() => onSend()} disabled={sending}>
              {sending ? "Sending..." : "Send"}
            </button>
          </div>

          <div className="ws-prompts">
            <button className="ws-chip" type="button" onClick={() => onSend("BTC market sentiment this week?")}>BTC market sentiment this week?</button>
            <button className="ws-chip" type="button" onClick={() => onSend("Show BTC key levels on 4h")}>Show BTC key levels on 4h</button>
            <button className="ws-chip" type="button" onClick={() => onSend("Why is ETH moving today?")}>Why is ETH moving today?</button>
          </div>
        </div>
      </section>
    </main>
  );
}
