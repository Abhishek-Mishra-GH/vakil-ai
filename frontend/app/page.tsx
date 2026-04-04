"use client";

import Link from "next/link";
import LandingNav from "@/components/LandingNav";

export default function HomePage() {
  return (
    <div className="landing-shell-light">
      <LandingNav />
      <main className="landing-main-light">
        {/* Hero Section */}
        <section className="hero-light">
          <div className="hero-light-content">
            <div className="hero-light-badge">
              ⚖️ Litigation Intelligence for Indian Advocates
            </div>
            <h1 className="hero-light-title">
              Build Stronger Cases,
              <br />
              <span className="gradient-text-light">Win in Court.</span>
            </h1>
            <p className="hero-light-subtitle">
              Experience the future of legal preparation. Analyze contracts
              clause-by-clause, detect contradictions in seconds, prepare
              hearing briefs with intelligence, and succeed in moot court. All
              grounded in your case files.
            </p>
            <div className="hero-light-actions">
              <Link href="/dashboard" className="btn btn-landing-primary">
                Launch Dashboard
              </Link>
              <Link href="/hearing-brief" className="btn btn-landing-secondary">
                Try Hearing Brief
              </Link>
            </div>
          </div>
          <div className="hero-light-features">
            <div className="hero-feature-card">
              <div className="feature-icon">🔍</div>
              <div className="feature-title">X-Ray Analysis</div>
              <div className="feature-desc">
                Clause-level insights from contract documents
              </div>
            </div>
            <div className="hero-feature-card">
              <div className="feature-icon">⚠️</div>
              <div className="feature-title">Contradiction Detection</div>
              <div className="feature-desc">
                Identify conflicts across your entire case
              </div>
            </div>
            <div className="hero-feature-card">
              <div className="feature-icon">📋</div>
              <div className="feature-title">Hearing Briefs</div>
              <div className="feature-desc">
                AI-powered briefs ready for court
              </div>
            </div>
            <div className="hero-feature-card">
              <div className="feature-icon">🎯</div>
              <div className="feature-title">Moot Court Practice</div>
              <div className="feature-desc">
                Simulate hearings and refine arguments
              </div>
            </div>
          </div>
        </section>

        {/* Features Section */}
        <section className="features-light" id="features">
          <div className="section-header-light">
            <h2>Powerful Features for Modern Advocates</h2>
            <p>Everything you need to prepare, argue, and win</p>
          </div>
          <div className="features-grid-light">
            <div className="feature-item-light">
              <div className="feature-item-number">1</div>
              <h3>Case-First Workflow</h3>
              <p>
                Upload your documents and immediately get actionable insights.
                Our AI understands complex legal documents and extracts what
                matters for your case.
              </p>
            </div>
            <div className="feature-item-light">
              <div className="feature-item-number">2</div>
              <h3>Intelligent Clause Analysis</h3>
              <p>
                Deep dive into every clause. Understand obligations,
                liabilities, and implications without missing critical details.
              </p>
            </div>
            <div className="feature-item-light">
              <div className="feature-item-number">3</div>
              <h3>Contradiction Detector</h3>
              <p>
                Automatically identify contradictions and inconsistencies across
                multiple documents. Build stronger arguments backed by evidence.
              </p>
            </div>
            <div className="feature-item-light">
              <div className="feature-item-number">4</div>
              <h3>Hearing-Ready Briefs</h3>
              <p>
                Generate comprehensive hearing briefs with key arguments,
                supporting clauses, and precedents. Walk into court prepared.
              </p>
            </div>
            <div className="feature-item-light">
              <div className="feature-item-number">5</div>
              <h3>Moot Court Simulator</h3>
              <p>
                Practice against adversarial questions. Refine your responses
                and build confidence before the actual hearing.
              </p>
            </div>
            <div className="feature-item-light">
              <div className="feature-item-number">6</div>
              <h3>Multi-Language Support</h3>
              <p>
                Work with documents in multiple languages. VakilAI handles
                translation and analysis seamlessly.
              </p>
            </div>
          </div>
        </section>

        {/* Why Section */}
        <section className="why-light" id="why">
          <div className="why-container">
            <div className="why-content">
              <h2>Why Advocates Choose VakilAI</h2>
              <div className="why-points">
                <div className="why-point">
                  <div className="why-point-icon">✓</div>
                  <div>
                    <h4>Built for Indian Courts</h4>
                    <p>
                      Designed specifically for the Indian legal system and
                      court procedures.
                    </p>
                  </div>
                </div>
                <div className="why-point">
                  <div className="why-point-icon">✓</div>
                  <div>
                    <h4>Time-Saving Analysis</h4>
                    <p>
                      What takes hours to review manually takes minutes with AI
                      assistance.
                    </p>
                  </div>
                </div>
                <div className="why-point">
                  <div className="why-point-icon">✓</div>
                  <div>
                    <h4>Better Case Outcomes</h4>
                    <p>
                      Advocates using VakilAI are prepared for every angle and
                      scenario.
                    </p>
                  </div>
                </div>
                <div className="why-point">
                  <div className="why-point-icon">✓</div>
                  <div>
                    <h4>Confidential & Secure</h4>
                    <p>
                      Your case files and legal strategies are encrypted and
                      protected.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Stats Section */}
        {/* <section className="stats-light">
          <div className="stats-grid-light">
            <div className="stat-box-light">
              <div className="stat-number">10K+</div>
              <div className="stat-label">Cases Analyzed</div>
            </div>
            <div className="stat-box-light">
              <div className="stat-number">95%</div>
              <div className="stat-label">Success Rate</div>
            </div>
            <div className="stat-box-light">
              <div className="stat-number">500+</div>
              <div className="stat-label">Active Advocates</div>
            </div>
            <div className="stat-box-light">
              <div className="stat-number">24/7</div>
              <div className="stat-label">AI Support</div>
            </div>
          </div>
        </section> */}

        {/* CTA Section */}
        <section className="cta-light">
          <div className="cta-content-light">
            <h2>Ready to Transform Your Legal Practice?</h2>
            <p>Join hundreds of advocates who are winning cases with VakilAI</p>
            <Link
              href="/dashboard"
              className="btn btn-landing-primary btn-large"
            >
              Start Your Free Trial
            </Link>
          </div>
        </section>

        {/* Footer */}
        <footer className="footer-light">
          <div className="footer-content">
            <div className="footer-brand">
              <h3>VakilAI</h3>
              <p>Litigation Intelligence for Indian Advocates</p>
            </div>
            <div className="footer-links">
              <div className="footer-column">
                <h4>Product</h4>
                <ul>
                  <li>
                    <a href="#features">Features</a>
                  </li>
                  <li>
                    <a href="/dashboard">Dashboard</a>
                  </li>
                </ul>
              </div>
              <div className="footer-column">
                <h4>Legal</h4>
                <ul>
                  <li>
                    <a href="#privacy">Privacy Policy</a>
                  </li>
                  <li>
                    <a href="#terms">Terms of Service</a>
                  </li>
                </ul>
              </div>
              <div className="footer-column">
                <h4>Support</h4>
                <ul>
                  <li>
                    <a href="#contact">Contact</a>
                  </li>
                  <li>
                    <a href="#faq">Documentation</a>
                  </li>
                </ul>
              </div>
            </div>
          </div>
          <div className="footer-bottom">
            <p>&copy; 2024 VakilAI. All rights reserved.</p>
          </div>
        </footer>
      </main>
    </div>
  );
}
