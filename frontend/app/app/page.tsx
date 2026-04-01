"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { getAuthToken } from "@/lib/session";

export default function AppIndexPage() {
  const router = useRouter();

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      router.replace("/login");
      return;
    }

    api
      .listThreads(token)
      .then(async (threads) => {
        if (threads.length > 0) {
          router.replace(`/app/chat/${threads[0].id}`);
          return;
        }
        const created = await api.createThread(token, "New chat");
        router.replace(`/app/chat/${created.id}`);
      })
      .catch(() => router.replace("/login"));
  }, [router]);

  return null;
}
