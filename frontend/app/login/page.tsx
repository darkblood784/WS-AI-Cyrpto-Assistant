"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { importGuestThreadToUser } from "@/lib/guest-migration";
import { setAuthToken } from "@/lib/session";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onLogin = async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await api.login(email.trim(), password);
      setAuthToken(data.access_token);

      // Navigate to existing thread or create one — don't block on guest import.
      const threads = await api.listThreads(data.access_token);
      let targetThread: string;
      if (threads.length > 0) {
        targetThread = threads[0].id;
      } else {
        const created = await api.createThread(data.access_token, "New chat");
        targetThread = created.id;
      }

      // Fire-and-forget: replay guest demo messages in background
      importGuestThreadToUser(data.access_token).catch(() => {});

      router.replace(`/app/chat/${targetThread}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Login failed";
      if (msg.includes("Email not verified")) {
        setError("Email not verified. Check inbox or use verify page.");
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="ws-auth-layout">
      <section className="ws-auth-page-card">
        <h1>Login</h1>
        <p>Continue your WSAI workspace and active threads.</p>

        {error ? <div className="ws-error">{error}</div> : null}

        <input className="ws-input" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <input
          className="ws-input"
          placeholder="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button className="ws-btn-primary" type="button" onClick={onLogin} disabled={loading}>
          {loading ? "Signing in..." : "Login"}
        </button>

        <div className="ws-auth-links">
          <Link href="/register">Create account</Link>
          <Link href="/verify-email">Verify email</Link>
          <Link href="/">Back to guest demo</Link>
        </div>
      </section>
    </main>
  );
}
