"use client";

import type { ThreadSummary } from "@/lib/types";

type Props = {
  planName: string;
  dayUsageText: string;
  threads: ThreadSummary[];
  activeThreadId: string | null;
  onOpenThread: (threadId: string) => void;
  onCreateThread: () => void;
};

export function AppSidebar({ planName, dayUsageText, threads, activeThreadId, onOpenThread, onCreateThread }: Props) {
  return (
    <aside className="ws-app-sidebar">
      <div className="ws-brand-row">
        <span className="ws-brand-mark">WS</span>
        <div className="ws-brand-text">Whale Strategy AI</div>
      </div>

      <button className="ws-new-chat" type="button" onClick={onCreateThread}>+ New Chat</button>

      <nav className="ws-nav" aria-label="App sections">
        <div className="ws-nav-item active">Chat</div>
        <div className="ws-nav-item">Dashboard</div>
        <div className="ws-nav-item">Billing</div>
        <div className="ws-nav-item">Settings</div>
      </nav>

      <div className="ws-thread-scroll">
        {threads.length === 0 ? <div className="ws-empty">No threads yet.</div> : null}
        {threads.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`ws-thread-btn${activeThreadId === t.id ? " active" : ""}`}
            onClick={() => onOpenThread(t.id)}
          >
            {t.title}
          </button>
        ))}
      </div>

      <div className="ws-sidebar-foot">
        <div className="ws-card-k">Plan</div>
        <div className="ws-card-v" style={{ fontSize: 30 }}>{planName}</div>
        <div className="ws-card-s">Day usage: {dayUsageText}</div>
      </div>
    </aside>
  );
}
