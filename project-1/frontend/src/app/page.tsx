"use client";

import { API_BASE } from "../lib/api";

import { useEffect, useState } from "react";
import Link from "next/link";
import DefenseDashboard from "../components/defense-dashboard";

import { Analysis, FuturePrediction, PredictionDetails, metric } from "../components/research-analysis";

type BackendStatus = {
  system: string;
  message: string;
  status: string;
};

type Incident = {
  incident_id: string;
  title: string;
  severity: "low" | "medium" | "high" | "critical";
  status: "active" | "investigating" | "contained" | "closed";
  detected_at: string;
  affected_host: string;
  affected_user: string | null;
  current_tactic: string;
  current_technique_id: string;
  current_technique_name: string;
  evidence_count: number;
  simulated: boolean;
};

export default function Home() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analysisError, setAnalysisError] = useState("");
  const outcome = analysis?.latest_assessment?.response_analysis;
  const retention = outcome?.candidates.find(c => c.action === outcome.recommended_action)?.evidence_retention_score;
  const evidenceItems = (analysis?.evidence ?? []).filter(e => e.forensic_utility != null).map(e => ({ name: e.evidence_id + " " + e.object, utility: Number((e.forensic_utility! * 100).toFixed(1)), state: e.warnings.length ? "warning" : "stable" }));
  const preventionActions = (outcome?.candidates ?? []).map(c => ({ action: c.action, risk: Number((c.residual_attack_risk * 100).toFixed(1)), evidenceLoss: Number((c.normalized_evidence_loss * 100).toFixed(1)), impact: (c.business_impact * 100).toFixed(1) + "%" }));

  /* =======================================================
     BACKEND STATUS STATE
  ======================================================= */

  const [backendStatus, setBackendStatus] =
    useState<BackendStatus | null>(null);

  const [backendError, setBackendError] =
    useState(false);

  /* =======================================================
     INCIDENT STATE
  ======================================================= */

  const [incident, setIncident] =
    useState<Incident | null>(null);

  useEffect(() => {
    if (!incident?.incident_id) return;
    const controller = new AbortController();
    fetch(`${API_BASE}/api/workflow/${incident.incident_id}/analysis`, { signal: controller.signal })
      .then(async r => { if (!r.ok) throw new Error("Incident analysis unavailable"); return r.json(); })
      .then(setAnalysis).catch(e => { if (!controller.signal.aborted) setAnalysisError(String(e)); });
    return () => controller.abort();
  }, [incident?.incident_id]);

  /* =======================================================
     LOAD BACKEND + INCIDENT DATA
  ======================================================= */

  useEffect(() => {
    const loadFrameworkData = async () => {
      /* -----------------------------------------
         Check FastAPI backend status
      ----------------------------------------- */

      try {
        const statusResponse = await fetch(
          `${API_BASE}/api/status`,
          {
            cache: "no-store",
          }
        );

        if (!statusResponse.ok) {
          throw new Error("Backend unavailable");
        }

        const statusData: BackendStatus =
          await statusResponse.json();

        setBackendStatus(statusData);
        setBackendError(false);
      } catch {
        setBackendStatus(null);
        setBackendError(true);
      }

      /* -----------------------------------------
         Load current incident
      ----------------------------------------- */

      try {
        const incidentResponse = await fetch(
          `${API_BASE}/api/incidents`,
          {
            cache: "no-store",
          }
        );

        if (!incidentResponse.ok) {
          throw new Error("Incident API unavailable");
        }

        const incidentData: Incident[] =
          await incidentResponse.json();

        if (incidentData.length > 0) {
          setIncident(incidentData[0]);
        } else {
          setIncident(null);
        }
      } catch {
        setIncident(null);
      }
    };

    loadFrameworkData();
  }, []);

  /* =======================================================
     FRAMEWORK STATUS TEXT
  ======================================================= */

  const frameworkStatus =
    backendError
      ? "BACKEND OFFLINE"
      : backendStatus?.status === "online"
        ? "FRAMEWORK ONLINE"
        : "CONNECTING...";

  return (
    <main className="command-deck">

      {/* ===================================================
          LEFT NAVIGATION
      =================================================== */}



      {/* ===================================================
          MAIN WORKSPACE
      =================================================== */}

      <section className="workspace">

        {/* =================================================
            PAGE HEADER
        ================================================= */}

        <header className="topbar">

          <div>
            <p className="eyebrow">
              INTELLIGENT CYBERATTACK PREDICTION
              &amp; PREVENTION
            </p>

            <h1>
              Cyber Defense Intelligence Center
            </h1>
          </div>

          <div className="topbar-right">

            <div className="simulation-badge">
              {incident
                ? incident.simulated
                  ? "SIMULATED ENVIRONMENT"
                  : "LIVE ENVIRONMENT"
                : "LOADING INCIDENT"}
            </div>

            <div
              className="system-status"
              aria-live="polite"
            >
              <span className="pulse-dot" />
              {frameworkStatus}
            </div>

          </div>
        </header>

        {/* =================================================
            ACTIVE INCIDENT SUMMARY
        ================================================= */}

        <DefenseDashboard />
        <h2>Research demonstration</h2>
        <p className="research-note">The following INC-00001 workflow uses simulated fixture evidence and synthetic research models. Current defense records are shown above.</p>

        <section className="incident-strip">

          <div className="incident-identity">

            <div className="severity-orb" />

            <div>
              <span className="incident-label">
                RESEARCH INCIDENT
              </span>

              <strong>
                {incident?.incident_id ?? "—"}
              </strong>
            </div>

          </div>

          <div className="incident-metric">
            <span>
              Current tactic
            </span>

            <strong>
              {incident?.current_tactic ?? "—"}
            </strong>
          </div>

          <div className="incident-metric">
            <span>
              Current ATT&amp;CK assessment
            </span>

            <strong>
              {analysis?.future_prediction.current_technique ?? "—"} · Status: {analysis?.future_prediction.current_mapping_status ?? "NOT AVAILABLE"}
            </strong>
          </div>

          <div className="incident-metric">
            <span>
              Host
            </span>

            <strong>
              {incident?.affected_host ?? "—"}
            </strong>
          </div>

          <div className="incident-metric">
            <span>
              Evidence retention
            </span>

            <strong className="retention">
              {metric(retention)}
            </strong>
          </div>

        </section>

        {/* =================================================
            INTELLIGENCE GRID
        ================================================= */}

        <section className="intelligence-grid">

          {/* ===============================================
              01 - ATTACK PREDICTION
          =============================================== */}

          <article className="deck-panel future-panel">

            <div className="panel-heading">

              <div>
                <span className="panel-index">
                  01
                </span>

                <h2>
                  Future Attack Prediction
                </h2>
              </div>

              <span className="small-status">
                PREDICTION ENGINE
              </span>

            </div>

            <div className="future-origin">

              <span>
                CURRENT ATT&amp;CK ASSESSMENT
              </span>

              <strong>
                {analysis?.future_prediction.current_technique ?? "—"}
              </strong>

              <small>
                {analysis?.future_prediction.current_technique_name ?? "Loading..."} · Status: {analysis?.future_prediction.current_mapping_status ?? "NOT AVAILABLE"}
              </small>

            </div>

            <div className="future-lines">
              {analysis ? <><FuturePrediction prediction={analysis.future_prediction} /><details><summary>Dataset Demonstration Scenario - Synthetic next-stage prediction</summary><PredictionDetails prediction={analysis.synthetic_prediction} /></details></> : <p>{analysisError || "Loading model inference?"}</p>}
            </div>

            <div className="uncertainty-meter">

              <div>
                <span>
                  Future technique uncertainty
                </span>

                <strong>
                  {analysis?.future_prediction.uncertainty == null ? "NOT MEASURED" : metric(analysis.future_prediction.uncertainty)}
                </strong>
              </div>

              <div className="meter-track">
                <div className="meter-value uncertainty-value" style={{ width: analysis?.future_prediction.uncertainty == null ? "0%" : metric(analysis.future_prediction.uncertainty) }} />
              </div>

            </div>

          </article>

          {/* ===============================================
              02 - TEMPORAL ATTACK GRAPH
          =============================================== */}

          <article className="deck-panel graph-panel">

            <div className="panel-heading">

              <div>
                <span className="panel-index">
                  02
                </span>

                <h2>
                  Temporal Attack Map
                </h2>
              </div>

              <span className="small-status">
                SIMULATED STATE
              </span>

            </div>

            <div className="attack-map observed-map">
              {(analysis?.evidence ?? []).map(e => <div className="observed-edge" key={e.evidence_id}><small>OBSERVED ? {e.evidence_id} ? {e.timestamp.slice(11)}</small><strong>{e.subject} ? {e.action} ? {e.object}</strong></div>)}
              <Link href="/graph">Explore temporal graph ?</Link>
            </div>

            <div className="graph-caption">

              <span>
                {analysis?.graph.nodes.length ?? 0} entities
              </span>

              <span>
                {analysis?.graph.edges.length ?? 0} relationships
              </span>

              <span>
                {incident?.evidence_count ?? 0} evidence events
              </span>

            </div>

          </article>

          {/* ===============================================
              03 - DIGITAL EVIDENCE ANALYSIS
          =============================================== */}

          <article className="deck-panel twin-panel">

            <div className="panel-heading">

              <div>
                <span className="panel-index">
                  03
                </span>

                <h2>
                  Digital Evidence Intelligence
                </h2>
              </div>

              <span className="small-status">
                EVIDENCE ANALYSIS
              </span>

            </div>

            <div className="twin-score">

              <div className="score-ring">
                <span>
                  {retention == null ? "N/A" : (retention * 100).toFixed(1)}
                </span>

                <small>
                  ERS
                </small>
              </div>

              <div>

                <span className="score-label">
                  Evidence retention
                </span>

                <strong>
                  {retention == null ? "Run a prevention assessment" : "Predicted ERS from saved assessment"}
                </strong>

              </div>

            </div>

            <div className="evidence-list">

              {evidenceItems.map(
                (item) => (
                  <div
                    className="evidence-row"
                    key={item.name}
                  >

                    <div
                      className={
                        `evidence-state ${item.state}`
                      }
                    />

                    <div className="evidence-name">

                      <strong>
                        {item.name}
                      </strong>

                      <span>
                        Forensic utility (heuristic)
                      </span>

                    </div>

                    <div className="evidence-meter">

                      <div
                        className="evidence-meter-value"
                        style={{
                          width:
                            `${item.utility}%`,
                        }}
                      />

                    </div>

                    <b>
                      {item.utility}
                    </b>

                  </div>
                )
              )}

            </div>

          </article>

        </section>

        {/* =================================================
            04 - DIGITAL EVIDENCE TIMELINE
        ================================================= */}

        <section className="timeline-panel">

          <div className="timeline-header">

            <div>

              <span className="panel-index">
                04
              </span>

              <h2>
                Attack Chronology
              </h2>

            </div>

            <span className="small-status">
              DIGITAL EVIDENCE TIMELINE
            </span>

          </div>

          <div className="timeline">
            {(analysis?.evidence ?? []).map(e => <div className="timeline-event complete" key={e.evidence_id}><span className="time">{e.timestamp.slice(11)}</span><div className="timeline-point" /><strong>{e.action}</strong><small>OBSERVED ? {e.evidence_id}</small></div>)}
            <p className="research-note">OBSERVED chronology only. Future model outputs and the synthetic demonstration are shown separately in Future Attack Prediction.</p>
          </div>

        </section>

        {/* =================================================
            05 - INTELLIGENT PREVENTION DECISION
        ================================================= */}

        <section className="response-lab">

          <div className="response-header">

            <div>

              <span className="panel-index">
                05
              </span>

              <h2>
                Intelligent Prevention Decision Laboratory
              </h2>

              <p>
                Compare predicted attack-risk reduction,
                forensic evidence loss, and operational impact
                before selecting a prevention action.
              </p>

            </div>

            <div className="optimizer-state">

              <span>
                DECISION PROFILE
              </span>

              <strong>
                Balanced
              </strong>

            </div>

          </div>

          <p className="research-note">{outcome ? outcome.objective_formula : "No saved response assessment. Open Prevention to calculate response estimates."}</p>
          <div className="response-table">

            <div className="response-table-head">

              <span>
                Prevention action
              </span>

              <span>
                Residual risk
              </span>

              <span>
                Evidence loss
              </span>

              <span>
                Business impact
              </span>

            </div>

            {preventionActions.map(
              (response, index) => (
                <div
                  className={
                    `response-row ${
                      index === 0
                        ? "recommended"
                        : ""
                    }`
                  }
                  key={response.action}
                >

                  <div className="response-name">

                    {index === 0 && (
                      <span className="recommended-tag">
                        RECOMMENDED
                      </span>
                    )}

                    <strong>
                      {response.action}
                    </strong>

                  </div>

                  <div className="metric-bar">

                    <div className="metric-track">

                      <div
                        className="metric-value risk-value"
                        style={{
                          width:
                            `${response.risk}%`,
                        }}
                      />

                    </div>

                    <b>
                      {response.risk}%
                    </b>

                  </div>

                  <div className="metric-bar">

                    <div className="metric-track">

                      <div
                        className="metric-value loss-value"
                        style={{
                          width:
                            `${response.evidenceLoss}%`,
                        }}
                      />

                    </div>

                    <b>
                      {response.evidenceLoss}%
                    </b>

                  </div>

                  <span
                    className={
                      `impact impact-${response.impact.toLowerCase()}`
                    }
                  >
                    {response.impact}
                  </span>

                </div>
              )
            )}

          </div>

          {/* ===============================================
              EVIDENCE-AWARE PREVENTION
          =============================================== */}

          <div className="preservation-footer">

            <div className="pearl-block">

              <span>
                EVIDENCE PRESERVATION PLAN
              </span>

              <strong>
                Capture process state → capture network
                state → hash evidence → execute prevention
                action
              </strong>

            </div>

            <Link href="/prevention" className="contain-button">

              <span>
                PRESERVE
              </span>

              <b>
                +
              </b>

              <span>
                PREVENT
              </span>

            </Link>

          </div>

        </section>

        {/* =================================================
            FOOTER
        ================================================= */}

        <footer className="deck-footer">

          <span>
            INTELLIGENT CYBERATTACK PREDICTION
            &amp; PREVENTION RESEARCH PROTOTYPE
          </span>

          <span>
            Fixture evidence; predictions use synthetic-label models. No host actions executed.
          </span>

        </footer>

      </section>

    </main>
  );
}
