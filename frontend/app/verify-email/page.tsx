"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { importGuestThreadToUser } from "@/lib/guest-migration";
import { setAuthToken } from "@/lib/session";

const attempted = new Set<string>();

export default function VerifyEmailPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tokenFromUrl = useMemo(() => (searchParams.get("token") || "").trim(), [searchParams]);

  const [token, setToken] = useState(tokenFromUrl);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setToken(tokenFromUrl);
  }, [tokenFromUrl]);

  const completeLoginFlow = useCallback(async (accessToken: string) => {
    setAuthToken(accessToken);
    const importedThreadId = await importGuestThreadToUser(accessToken);
    if (importedThreadId) {
      router.replace(`/app/chat/${importedThreadId}`);
      return;
    }

    const threads = await api.listThreads(accessToken);
    if (threads.length > 0) {
      router.replace(`/app/chat/${threads[0].id}`);
      return;
    }

    const created = await api.createThread(accessToken, "New chat");
    router.replace(`/app/chat/${created.id}`);
  }, [router]);

  const verifyAndLogin = useCallback(async (value: string) => {
    setLoading(true);
    setStatus(null);
    setError(null);
    try {
      const v = await api.verifyLogin(value.trim());
      setStatus("Email verified. Redirecting to your app...");
      await completeLoginFlow(v.access_token);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Verification failed";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [completeLoginFlow]);

  useEffect(() => {
    if (!tokenFromUrl) return;
    if (attempted.has(tokenFromUrl)) return;
    attempted.add(tokenFromUrl);
    void verifyAndLogin(tokenFromUrl);
  }, [tokenFromUrl, verifyAndLogin]);

  return (
    <main className="ws-auth-layout">
      <section className="ws-auth-page-card">
        <h1>Verify Email</h1>
        <p>Enter your verification token. Successful verification auto-signs you in.</p>

        {status ? <div className="ws-status">{status}</div> : null}
        {error ? <div className="ws-error">{error}</div> : null}

        <input className="ws-input" placeholder="Paste token" value={token} onChange={(e) => setToken(e.target.value)} />
        <button className="ws-btn-primary" type="button" onClick={() => verifyAndLogin(token)} disabled={loading}>
          {loading ? "Verifying..." : "Verify and continue"}
        </button>

        <div className="ws-auth-links">
          <Link href="/login">Back to login</Link>
          <Link href="/">Back to guest demo</Link>
        </div>
      </section>
    </main>
  );
}
