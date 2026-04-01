"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onRegister = async () => {
    setStatus(null);
    setError(null);
    setLoading(true);
    try {
      await api.register(email.trim(), password);
      setStatus("Registered. Check email for verification link.");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Register failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const onResend = async () => {
    setStatus(null);
    setError(null);
    setLoading(true);
    try {
      const data = await api.resendVerification(email.trim());
      if (data.already_verified) {
        setStatus("Email already verified. You can login now.");
      } else {
        setStatus("Verification email resent.");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Resend failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="ws-auth-layout">
      <section className="ws-auth-page-card">
        <h1>Create Account</h1>
        <p>Start with Free, then upgrade to Plus or Pro when needed.</p>

        {status ? <div className="ws-status">{status}</div> : null}
        {error ? <div className="ws-error">{error}</div> : null}

        <input className="ws-input" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input
          className="ws-input"
          placeholder="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <div className="ws-auth-actions">
          <button className="ws-btn-primary" type="button" onClick={onRegister} disabled={loading}>
            {loading ? "Creating..." : "Create account"}
          </button>
          <button className="ws-btn-ghost" type="button" onClick={onResend} disabled={loading}>
            Resend verification
          </button>
        </div>

        <div className="ws-auth-links">
          <Link href="/login">Already have account? Login</Link>
          <Link href="/">Back to guest demo</Link>
        </div>
      </section>
    </main>
  );
}
