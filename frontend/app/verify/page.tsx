"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function LegacyVerifyRedirectPage() {
  const router = useRouter();
  const search = useSearchParams();

  useEffect(() => {
    const token = (search.get("token") || "").trim();
    if (token) {
      router.replace(`/verify-email?token=${encodeURIComponent(token)}`);
    } else {
      router.replace("/verify-email");
    }
  }, [router, search]);

  return null;
}
