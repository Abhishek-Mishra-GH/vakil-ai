"use client";

import Link from "next/link";

export default function LandingNav() {
  return (
    <nav className="landing-nav">
      <div className="landing-nav-container">
        <Link href="/" className="landing-brand">
          <span className="landing-brand-main">VakilAI</span>
          <span className="landing-brand-sub">Litigation Intelligence</span>
        </Link>

        <div className="landing-nav-links">
          <a href="#features" className="landing-nav-link">
            Features
          </a>
          <a href="#why" className="landing-nav-link">
            Why VakilAI
          </a>
          <a href="#faq" className="landing-nav-link">
            FAQ
          </a>
        </div>

        <div className="landing-nav-actions">
          <Link href="/dashboard" className="btn btn-landing-primary">
            Get Started
          </Link>
        </div>
      </div>
    </nav>
  );
}
