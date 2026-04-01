"use client";

import { useEffect, useRef } from "react";

const BG = "#0b1426";

function patchShadow(el: Element) {
  // Try to access shadow root and override background
  const sr = (el as HTMLElement).shadowRoot;
  if (sr) {
    const s = document.createElement("style");
    s.textContent = `
      :host, :host > *, .wrapper, .ticker-tape, div[class] {
        background: ${BG} !important;
        background-color: ${BG} !important;
      }
    `;
    sr.appendChild(s);

    // Also patch any nested iframes
    sr.querySelectorAll("iframe").forEach(patchIframe);
  }
}

function patchIframe(iframe: HTMLIFrameElement) {
  try {
    const doc = iframe.contentDocument;
    if (!doc) return;
    const s = doc.createElement("style");
    s.textContent = `body, .wrapper, div { background: ${BG} !important; background-color: ${BG} !important; }`;
    doc.head.appendChild(s);
  } catch {
    // cross-origin — can't access, fall through to filter approach
  }
}

export function MarketStrip() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const tape = document.createElement("tv-ticker-tape");
    tape.setAttribute(
      "symbols",
      "OKX:BTCUSD13H2026,OKX:ETHUSDT27H2026,OKX:XRPUSDT,OKX:SOLUSDT",
    );
    tape.setAttribute("color-theme", "dark");
    tape.setAttribute("item-size", "compact");
    tape.setAttribute("show-hover", "");
    container.appendChild(tape);

    const script = document.createElement("script");
    script.type = "module";
    script.src =
      "https://widgets.tradingview-widget.com/w/en/tv-ticker-tape.js";
    container.appendChild(script);

    // Wait for the widget to render, then patch its internals
    const observer = new MutationObserver(() => {
      patchShadow(tape);
      // Also try patching any iframes that appear directly
      container.querySelectorAll("iframe").forEach(patchIframe);
    });
    observer.observe(container, { childList: true, subtree: true });

    // Retry a few times in case rendering is delayed
    const timers = [500, 1500, 3000].map((ms) =>
      setTimeout(() => {
        patchShadow(tape);
        container.querySelectorAll("iframe").forEach(patchIframe);
      }, ms),
    );

    return () => {
      observer.disconnect();
      timers.forEach(clearTimeout);
      container.innerHTML = "";
    };
  }, []);

  return (
    <div ref={containerRef} className="ws-tv-ticker" aria-label="Live market ticker" />
  );
}
