"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { GuestLimitModal } from "@/components/ui/GuestLimitModal";
import { IntelligenceCards } from "@/components/landing/IntelligenceCards";
import { LandingTopNav } from "@/components/landing/LandingTopNav";
import { MarketStrip } from "@/components/landing/MarketStrip";
import { SampleBrief } from "@/components/landing/SampleBrief";
import {
  GUEST_LIMIT,
  createGuestState,
  getGuestState,
  guestCanSend,
  guestRemainingPrompts,
  saveGuestState,
  type GuestState,
} from "@/lib/guest";

const quickActions = [
  "Why is the market moving today?",
  "What narratives are leading?",
  "Which alts are outperforming?",
  "What are BTC key levels?",
  "Build a low-risk setup for SOL",
];

function makeId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

const demoReplies: Record<string, string> = {
  "Why is the market moving today?": [
    "Bottom line:",
    "Majors are leading with BTC holding structure and ETH showing improving relative strength. Alt breadth is still selective — this is constructive but not broad risk-on yet.",
    "",
    "What is driving it:",
    "Liquidity is rotating into liquid leaders. Volume confirms the move is real, not just a low-liquidity drift. Momentum is shifting but hasn't fully confirmed.",
    "",
    "Trade implication:",
    "Favor liquid leaders and confirmed continuation setups. Avoid chasing random alts until breadth improves.",
    "",
    "Invalidation:",
    "If BTC loses reclaim structure or ETH relative strength fades, the move likely slips back into chop.",
    "",
    "Operator takeaway:",
    "This is a 'prove it' tape — constructive lean, but let price confirm before adding risk.",
    "",
    "[Demo] Sign up for live briefs with real-time data, levels, and invalidation.",
  ].join("\n"),
  "What are BTC key levels?": [
    "Bottom line:",
    "BTC is trading near decision structure. The next move depends on whether current support holds or gives way.",
    "",
    "What matters now:",
    "Watch the EMA20 and SMA50 for directional confirmation. Holding above both keeps the bullish read alive. Losing both opens downside to the SMA200.",
    "",
    "Trade implication:",
    "Longs are valid above key MAs with stops below structure. Shorts only make sense on a confirmed rejection with volume.",
    "",
    "Invalidation:",
    "A close below the SMA50 with expanding volume would invalidate the bullish setup.",
    "",
    "Operator takeaway:",
    "Levels are where opinions become positions — respect them or sit out.",
    "",
    "[Demo] Sign up to get exact live levels, RSI, MACD, and invalidation structure.",
  ].join("\n"),
  "Which alts are outperforming?": [
    "Bottom line:",
    "Alt breadth is narrow. A few liquid names are outperforming, but this is selective rotation — not a broad alt season.",
    "",
    "What is driving it:",
    "Capital is flowing into alts with strong narrative backing and improving relative strength vs BTC. Most smaller caps are still lagging.",
    "",
    "Trade implication:",
    "Only trade alts showing confirmed RS breakouts. If BTC stalls, alt outperformance can reverse fast.",
    "",
    "Invalidation:",
    "If BTC dominance spikes or total alt market cap breaks structure, alt trades should be cut.",
    "",
    "Operator takeaway:",
    "Be selective. In a narrow breadth environment, concentration beats diversification.",
    "",
    "[Demo] Sign up to get live alt scans, relative strength, and narrative tracking.",
  ].join("\n"),
  "What narratives are leading?": [
    "Bottom line:",
    "Narrative leadership rotates fast. The strongest themes right now are the ones pulling real volume, not just social mentions.",
    "",
    "What matters now:",
    "Track which sectors are seeing sustained inflows vs one-day spikes. Real narrative strength shows in multi-day follow-through.",
    "",
    "Trade implication:",
    "Align with narratives that have both volume confirmation and structural setups. Ignore noise-only themes.",
    "",
    "Operator takeaway:",
    "Narratives create opportunity windows — but timing the entry matters more than picking the theme.",
    "",
    "[Demo] Sign up for live narrative tracking, sector heat maps, and flow analysis.",
  ].join("\n"),
  "Build a low-risk setup for SOL": [
    "Bottom line:",
    "A low-risk setup means defined entry, defined stop, and asymmetric reward. SOL needs to be at a structural level for that to exist.",
    "",
    "Setup structure:",
    "Wait for SOL to retest a key MA (EMA20 or SMA50) with decreasing volume on the pullback. Entry on reclaim, stop below structure, target the next resistance.",
    "",
    "Trade implication:",
    "If SOL is mid-range with no clear level test, there is no setup — patience is the position.",
    "",
    "Invalidation:",
    "If the pullback breaks below the SMA50 with volume expansion, the setup is dead. Move on.",
    "",
    "Operator takeaway:",
    "Low-risk doesn't mean low-conviction. It means the math works — small loss if wrong, meaningful gain if right.",
    "",
    "[Demo] Sign up for live setup scans with exact entry, stop, and target levels.",
  ].join("\n"),
};

function demoAssistantReply(message: string): string {
  // Check for matching demo reply
  const lowerMsg = message.toLowerCase();
  for (const [key, reply] of Object.entries(demoReplies)) {
    if (key.toLowerCase() === lowerMsg) return reply;
  }
  // Default reply for unmatched questions
  return [
    "Bottom line:",
    `Your question — "${message}" — needs live market data to answer properly.`,
    "",
    "WSAI briefs include:",
    "- Directional bias with structural reasoning",
    "- Key levels with invalidation logic",
    "- Trade implications — not just information, but what to do with it",
    "- Risk framing so you know when you're wrong",
    "",
    "Sign up to get strategist-grade briefs with real-time data.",
  ].join("\n");
}

export default function LandingPage() {
  const [guest, setGuest] = useState<GuestState>(() => {
    if (typeof window === "undefined") return createGuestState();
    return getGuestState();
  });
  const [draft, setDraft] = useState(() => {
    if (typeof window === "undefined") return "";
    return getGuestState().draft || "";
  });
  const [showLimitModal, setShowLimitModal] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    saveGuestState({ ...guest, draft });
  }, [guest, draft]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [guest.messages.length]);

  const remaining = useMemo(() => guestRemainingPrompts(guest), [guest]);
  const hasMessages = guest.messages.length > 0;

  const onSend = (override?: string) => {
    const text = (override ?? draft).trim();
    if (!text) return;

    if (!guestCanSend(guest)) {
      setShowLimitModal(true);
      return;
    }

    const next: GuestState = {
      ...guest,
      sessionId: guest.sessionId || makeId("guest"),
      promptsUsed: guest.promptsUsed + 1,
      messages: [
        ...guest.messages,
        { id: makeId("u"), role: "user", content: text },
        { id: makeId("a"), role: "assistant", content: demoAssistantReply(text) },
      ],
      draft: "",
    };

    setGuest(next);
    setDraft("");

    if (next.promptsUsed >= GUEST_LIMIT) {
      setShowLimitModal(true);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <main className="ws-landing">
      <LandingTopNav />
      <MarketStrip />

      {/* Hero: command surface */}
      <section className="ws-hero-section">
        <div className="ws-kicker"><span className="ws-live-dot" />WSAI Operator Desk</div>
        <h1 className="ws-hero-headline">Ask before you act.</h1>
        <p className="ws-hero-sub">
          WSAI turns narrative, momentum, levels, and risk into a clear crypto trading brief.
          Built for crypto-native decision making.
        </p>

        {/* Trust chips */}
        <div className="ws-trust-row">
          <span className="ws-trust-chip">Live market context</span>
          <span className="ws-trust-chip">Risk-aware analysis</span>
          <span className="ws-trust-chip">Structured trade briefs</span>
          <span className="ws-trust-chip">Save threads after signup</span>
        </div>

        {/* Composer + Sample brief side by side */}
        <div className="ws-command-surface">
          <div className="ws-hero-composer">
            <div className="ws-compose">
              <textarea
                placeholder="Ask anything crypto: BTC sentiment today, ETH momentum, SOL setup, or risk-aware invalidation levels."
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={2}
              />
              <button className="ws-send" type="button" onClick={() => onSend()}>
                Ask WSAI
              </button>
            </div>
            <div className="ws-composer-meta">
              <span className="ws-free-tag" suppressHydrationWarning>{remaining} free question{remaining !== 1 ? "s" : ""} remaining</span>
              <span className="ws-composer-hint">instant brief</span>
            </div>

            {/* Quick actions */}
            <div className="ws-quick-row" aria-label="Quick market actions">
              {quickActions.map((p) => (
                <button key={p} className="ws-chip" type="button" onClick={() => onSend(p)}>
                  {p}
                </button>
              ))}
            </div>
          </div>

          <SampleBrief />
        </div>
      </section>

      {/* Intelligence cards — always visible */}
      <IntelligenceCards />

      {/* Chat thread — only shows when messages exist */}
      {hasMessages && (
        <section className="ws-thread-section">
          <div className="ws-thread-head">
            <span>Thread</span>
            <span className="ws-thread-count">{guest.messages.filter(m => m.role === "user").length} question{guest.messages.filter(m => m.role === "user").length !== 1 ? "s" : ""}</span>
          </div>
          <div className="ws-thread-messages">
            {guest.messages.map((m) => (
              <div key={m.id} className={`ws-msg ${m.role === "user" ? "user" : "assistant"}`}>
                <div className="ws-msg-role">{m.role}</div>
                <div className="ws-msg-content">{m.content}</div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
        </section>
      )}

      <GuestLimitModal open={showLimitModal} onClose={() => setShowLimitModal(false)} />
    </main>
  );
}
