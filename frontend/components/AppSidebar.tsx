"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const PRIMARY_ITEMS = [
  { href: "/dashboard", label: "Command Center", glyph: "grid" },
  { href: "/xray", label: "X-Ray Reader", glyph: "folder" },
  { href: "/contradictions", label: "Contradictions", glyph: "scales" },
  { href: "/hearing-brief", label: "Hearing Brief", glyph: "folder" },
  { href: "/moot-court", label: "Moot Court", glyph: "scales" },
] as const;

const SECONDARY_ITEMS = [
  { href: "/dashboard", label: "Settings" },
  { href: "/dashboard", label: "Support" },
] as const;

function Icon({ glyph }: { glyph: (typeof PRIMARY_ITEMS)[number]["glyph"] }) {
  if (glyph === "folder") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M4 7.5h5l1.5 2H20v7.5A1.5 1.5 0 0 1 18.5 18.5h-13A1.5 1.5 0 0 1 4 17V7.5Z" fill="currentColor" />
      </svg>
    );
  }
  if (glyph === "scales") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 4v14M7 7h10M6 18h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M7 7 4 12h6L7 7Zm10 0-3 5h6l-3-5Z" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4" y="4" width="6" height="6" fill="currentColor" />
      <rect x="14" y="4" width="6" height="6" fill="currentColor" />
      <rect x="4" y="14" width="6" height="6" fill="currentColor" />
      <rect x="14" y="14" width="6" height="6" fill="currentColor" />
    </svg>
  );
}

export default function AppSidebar() {
  const pathname = usePathname() || "";
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (collapsed) {
      document.body.classList.add("sidebar-collapsed");
    } else {
      document.body.classList.remove("sidebar-collapsed");
    }
  }, [collapsed]);

  return (
    <aside className={`app-sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="sidebar-brand-block" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Link href="/" className="sidebar-brand" style={{ display: collapsed ? 'none' : 'flex' }}>
          <span className="sidebar-brand-main">VakilAI</span>
          <span className="sidebar-brand-sub">The Archival Protocol</span>
        </Link>
        <button 
          onClick={() => setCollapsed(!collapsed)} 
          style={{ background: 'transparent', border: 'none', color: '#96a0b5', cursor: 'pointer', padding: 4 }}
          title={collapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" style={{ width: 20, height: 20 }}>
            {collapsed ? (
              <path d="M9 5l7 7-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            ) : (
              <path d="M15 5l-7 7 7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            )}
          </svg>
        </button>
      </div>

      <div style={{ padding: "0 10px 10px" }}>
        <div className="sidebar-search" aria-label="Search">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M11 18a7 7 0 1 1 0-14 7 7 0 0 1 0 14Zm9 2-4.2-4.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          <input type="text" readOnly placeholder="Search archives..." />
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Workspace">
        {PRIMARY_ITEMS.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link key={item.label} href={item.href} className={`sidebar-link ${active ? "active" : ""}`}>
              <span className="sidebar-link-icon">
                <Icon glyph={item.glyph} />
              </span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* <div className="sidebar-cta-wrap">
        <Link href="/hearing-brief" className="sidebar-cta">
          Draft New Brief
        </Link>
      </div>

      <div className="sidebar-footer-nav">
        {SECONDARY_ITEMS.map((item) => (
          <Link key={item.label} href={item.href} className="sidebar-footer-link">
            {item.label}
          </Link>
        ))}
      </div> */}
    </aside>
  );
}
