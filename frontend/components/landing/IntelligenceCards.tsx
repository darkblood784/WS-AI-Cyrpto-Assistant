const cards = [
  { label: "Market Bias", value: "Live", hint: "AI reads price action + sentiment", featured: true },
  { label: "Key Levels", value: "Auto", hint: "Support & resistance from structure" },
  { label: "Momentum", value: "Tracked", hint: "RSI, EMA, MACD across timeframes" },
  { label: "Altcoin Flows", value: "Scanned", hint: "Rotation and relative strength" },
  { label: "Narrative Heat", value: "Monitored", hint: "Trending themes and sectors" },
  { label: "Risk Tone", value: "Assessed", hint: "Volatility and headline sensitivity" },
];

export function IntelligenceCards() {
  return (
    <section className="ws-intel-grid" aria-label="Live intelligence cards">
      {cards.map((c) => (
        <article key={c.label} className={`ws-intel-card${"featured" in c && c.featured ? " ws-intel-featured" : ""}`}>
          {"featured" in c && c.featured && <span className="ws-live-dot ws-live-dot-sm" />}
          <div className="ws-card-k">{c.label}</div>
          <div className="ws-card-v ws-card-v-compact">{c.value}</div>
          <div className="ws-card-s">{c.hint}</div>
        </article>
      ))}
    </section>
  );
}
