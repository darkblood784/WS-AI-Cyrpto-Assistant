const lines = [
  { label: "Market Bias", value: "Assessed from price action and volume" },
  { label: "Leadership", value: "Which assets are leading or lagging" },
  { label: "Risk Tone", value: "Volatility regime and headline sensitivity" },
  { label: "Setup Quality", value: "Entry conditions and trade structure" },
  { label: "Invalidation", value: "Levels where the thesis breaks down" },
];

export function SampleBrief() {
  return (
    <div className="ws-sample-brief">
      <div className="ws-brief-head">
        <span className="ws-live-dot" />
        <span className="ws-brief-label">What You Get</span>
        <span className="ws-brief-ts">per question</span>
      </div>
      <div className="ws-brief-body">
        {lines.map((l) => (
          <div key={l.label} className="ws-brief-row">
            <span className="ws-brief-k">{l.label}</span>
            <span className="ws-brief-v">{l.value}</span>
          </div>
        ))}
      </div>
      <div className="ws-brief-foot">
        Every answer is a structured brief, not a generic chatbot reply
      </div>
    </div>
  );
}
