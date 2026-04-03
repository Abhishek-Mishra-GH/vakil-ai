"use client";

import Link from "next/link";
// import TopNav from "@/components/TopNav";

export default function HomePage() {
  return (
    <div className="landing-shell">
      {/* <TopNav /> */}
      <main className="landing-main">
        <section className="hero">
          <div className="hero-badge">Litigation Intelligence for Indian Advocates</div>
          <h1>
            Build Stronger Hearings
            <br />
            <span className="gradient-text">Before You Enter Court.</span>
          </h1>
          <p className="hero-subtitle">
            One workspace for x-ray clause analysis, contradiction detection, hearing briefs,
            and moot court preparation grounded in your case files.
          </p>
          <div className="hero-actions">
            <Link href="/dashboard" className="btn btn-primary">
              Open Dashboard
            </Link>
            <Link href="/hearing-brief" className="btn btn-secondary">
              View Hearing Brief
            </Link>
          </div>
          <div className="hero-stats">
            <div className="hero-stat">
              <div className="stat-value">Case-first</div>
              <div className="stat-label">Workflow</div>
            </div>
            <div className="hero-stat">
              <div className="stat-value">Clause-level</div>
              <div className="stat-label">Insights</div>
            </div>
            <div className="hero-stat">
              <div className="stat-value">Hearing-ready</div>
              <div className="stat-label">Briefing</div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
