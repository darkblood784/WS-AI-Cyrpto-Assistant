import Link from "next/link";

export function LandingTopNav() {
  return (
    <header className="ws-landing-nav">
      <div className="ws-brand-row ws-brand-row-tight">
        <span className="ws-brand-mark">WS</span>
        <div className="ws-brand-text">Whale Strategy AI</div>
      </div>
      <nav className="ws-landing-auth-links" aria-label="Auth navigation">
        <Link className="ws-btn-ghost-link" href="/login">Login</Link>
        <Link className="ws-btn-primary" href="/register">Create account</Link>
      </nav>
    </header>
  );
}
