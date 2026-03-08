import type { Metadata } from "next";

import "@/app/globals.css";

export const metadata: Metadata = {
  title: "HackOMania 2026 | PAB Triage Dashboard",
  description: "AI-assisted triage dashboard for prerecorded Personal Alert Button alerts."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-skywash text-ink">{children}</body>
    </html>
  );
}
