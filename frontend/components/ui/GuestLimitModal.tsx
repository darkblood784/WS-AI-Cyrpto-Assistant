"use client";

import Link from "next/link";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function GuestLimitModal({ open, onClose }: Props) {
  if (!open) return null;

  return (
    <div className="ws-modal-backdrop" role="dialog" aria-modal="true">
      <div className="ws-modal-card">
        <h3>Guest limit reached</h3>
        <p>Continue this thread with a free account.</p>
        <p className="ws-modal-note">Your analysis will be saved automatically after signup or login.</p>
        <div className="ws-modal-actions">
          <Link className="ws-btn-primary" href="/register">Create Account</Link>
          <Link className="ws-btn-ghost-link" href="/login">Login</Link>
          <button className="ws-btn-ghost" type="button" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
