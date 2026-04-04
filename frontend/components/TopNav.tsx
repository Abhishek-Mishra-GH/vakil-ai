"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const HEADER_MAP = {
  "/dashboard": { eyebrow: "Active Case Registry", title: "Docket View" },
  "/xray": { eyebrow: "Archival Protocol", title: "X-Ray" },
  "/contradictions": { eyebrow: "Conflict Analysis", title: "Contradictions" },
  "/hearing-brief": { eyebrow: "Hearing Command", title: "Hearing Brief" },
  "/moot-court": { eyebrow: "Adversarial Simulation", title: "Moot Court" },
} as const;

function resolveHeader(pathname: string) {
  const match = Object.entries(HEADER_MAP).find(([prefix]) =>
    pathname.startsWith(prefix),
  );
  return match?.[1] || { eyebrow: "", title: "VakilAI" };
}

export default function TopNav() {
  const pathname = usePathname() || "";
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Don't show TopNav on landing page - it has its own LandingNav
  if (mounted && pathname === "/") {
    return null;
  }

  const header = resolveHeader(pathname);

  return (
    <header className="top-nav-wrap">
      <div className="top-nav">
        <div className="top-nav-title-block">
          {/* <span className="top-nav-eyebrow">{header.eyebrow}</span>
          <h1 className="top-nav-title">{header.title}</h1> */}
        </div>

        <div
          id="topnav-portal-target"
          style={{
            flex: 1,
            margin: "0 24px",
            display: "flex",
            alignItems: "center",
          }}
        />

        {/* <div className="top-nav-tools">
          <a href="/login" className="btn btn-secondary">
            Login
          </a>
        </div> */}
      </div>
    </header>
  );
}
