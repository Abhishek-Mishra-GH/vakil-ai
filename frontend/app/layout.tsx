import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VakilAI — Litigation Prep Workspace",
  description:
    "AI-powered legal prep for Indian advocates: case management, x-ray document review, contradiction detection, hearing briefs, and moot court practice.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
