"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/xray", label: "X-Ray Reader" },
  { href: "/contradictions", label: "Contradictions" },
  { href: "/moot-court", label: "Moot Court" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <Link href="/">
          <h1>VakilAI</h1>
        </Link>
        <p>Litigation Preparation Workspace</p>
      </div>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <Link key={item.href} href={item.href} className={`nav-link ${pathname?.startsWith(item.href) ? "active" : ""}`}>
            {item.label}
          </Link>
        ))}
      </nav>
      <div className="sidebar-footer">
        <p style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>Built for Indian advocates</p>
      </div>
    </aside>
  );
}

