import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type Run = {
  id: string;
  actor: string;
  status: string;
  started_at: number;
  seconds: number;
  request: { runbook: string; target: string };
  findings: { code: string; summary: string; recommendation: string }[];
  evidence: Record<string, unknown>;
  remediation?: { outcome: string; verified: boolean; seconds: number };
};
type Approval = {
  id: string;
  run_id: string;
  requester: string;
  approver: string | null;
  state: string;
  expires: number;
};
type Catalog = { id: string; description: string; targets: string[]; remediation: boolean };
type Event = { seq: number; at: number; actor: string; event: string; subject: string; digest: string };
type Metrics = {
  total_runs: number;
  success_rate: number | null;
  failure_rate: number | null;
  intervention_runs: number;
  automated_seconds: number;
  manual_seconds: number;
  estimated_effort_avoided_seconds: number;
  baseline_runs: number;
  baseline_automated_seconds: number;
  repeatability: number | null;
};
const percent = (value: number | null) => (value === null ? "No data" : `${Math.round(value * 100)}%`);
const short = (value: string) => value.slice(0, 8);
function App() {
  const [token, setToken] = useState("");
  const [draft, setDraft] = useState("");
  const [identity, setIdentity] = useState<{ name: string; roles: string[] } | null>(null);
  const [tab, setTab] = useState("Overview");
  const [runs, setRuns] = useState<Run[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [catalog, setCatalog] = useState<Catalog[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Run | null>(null);
  const [target, setTarget] = useState("fixture");
  const [scenario, setScenario] = useState("failure");
  const [reason, setReason] = useState("");
  const [baseline, setBaseline] = useState("");
  const [baselineSource, setBaselineSource] = useState("");
  async function api<T>(path: string, body?: unknown, credential = token): Promise<T> {
    const response = await fetch(`/api/${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: {
        Authorization: `Bearer ${credential}`,
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
    return data as T;
  }
  async function refresh(credential = token) {
    const [r, a, c, e, m, who] = await Promise.all([
      api<Run[]>("runs", undefined, credential),
      api<Approval[]>("approvals", undefined, credential),
      api<Catalog[]>("catalog", undefined, credential),
      api<Event[]>("audit", undefined, credential),
      api<Metrics>("metrics", undefined, credential),
      api<{ name: string; roles: string[] }>("me", undefined, credential),
    ]);
    setRuns(r);
    setApprovals(a);
    setCatalog(c);
    setEvents(e);
    setMetrics(m);
    setIdentity(who);
  }
  async function action(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operation failed");
    } finally {
      setBusy(false);
    }
  }
  async function diagnose(id: string) {
    await action(async () => {
      const r = await api<Run>("runs", {
        runbook: id,
        target,
        scenario,
        ...(baseline ? { manual_seconds: Number(baseline), baseline_source: baselineSource } : {}),
      });
      setSelected(r);
      await refresh();
      setNotice(`Diagnosis completed: ${r.status}`);
    });
  }
  useEffect(() => {
    if (!token) return;
    const timer = setInterval(() => {
      refresh().catch(() => {});
    }, 10000);
    return () => clearInterval(timer);
  }, [token]);
  const pending = approvals.filter((a) => a.state === "pending").length;
  const activeTab = tab;
  return (
    <div className="shell">
      <aside>
        <a className="brand" href="/">
          <span className="logo">
            O<span>↗</span>
          </span>
          <span>
            OpsPilot<small>RELIABILITY WORKSPACE</small>
          </span>
        </a>
        <div className="workspace">
          <span className="dot" />
          Local operations<span className="tag">LAB</span>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {["Overview", "Automations", "Run history", "Approvals", "Audit trail"].map((name, i) => (
            <button
              key={name}
              aria-label={name}
              className={activeTab === name ? "active" : ""}
              onClick={() => setTab(name)}
            >
              <span className="nav-icon">{["◫", "⚡", "↻", "◇", "≡"][i]}</span>
              {name}
              {name === "Approvals" && pending > 0 && <b>{pending}</b>}
            </button>
          ))}
        </nav>
        <div className="aside-bottom">
          <div className="shield">◇</div>
          <strong>Controlled by design</strong>
          <p>
            Read-only diagnostics.
            <br />
            Independent recovery approval.
          </p>
          <span className="muted">OpsPilot / v0.1.1</span>
        </div>
      </aside>
      <main>
        <header>
          <div className="breadcrumb">
            Workspace <span>/</span> {tab}
          </div>
          <div className="header-right">
            <span className="dot" /> Local API{" "}
            <span className="avatar">{identity ? identity.name.slice(0, 2).toUpperCase() : "OP"}</span>
          </div>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">OPERATIONS INTELLIGENCE</div>
              <h1>{tab === "Overview" ? "Keep operations moving." : tab}</h1>
              <p>
                {tab === "Overview"
                  ? "Diagnose with evidence. Recover with confidence. Measure the work avoided."
                  : "Traceable operations, from the first signal to verified recovery."}
              </p>
            </div>
            <button disabled={!token || busy} className="primary" onClick={() => setTab("Automations")}>
              ＋ Run automation
            </button>
          </div>
          {!identity && (
            <form
              className="login panel"
              onSubmit={(e) => {
                e.preventDefault();
                action(async () => {
                  await refresh(draft);
                  setToken(draft);
                  setDraft("");
                });
              }}
            >
              <div>
                <strong>Connect your operator session</strong>
                <p>Use a local bearer credential. Credentials stay in memory for this session.</p>
              </div>
              <label>
                Bearer credential
                <input
                  type="password"
                  value={draft}
                  autoComplete="off"
                  onChange={(e) => setDraft(e.target.value)}
                  required
                  minLength={32}
                />
              </label>
              <button className="primary" disabled={busy}>
                Connect
              </button>
            </form>
          )}
          {identity && (
            <div className="session">
              <span>
                <span className="dot" /> {identity.name}{" "}
                <span className="muted">· {identity.roles.join(", ")}</span>
              </span>
              <button
                onClick={() => {
                  setToken("");
                  setIdentity(null);
                  setRuns([]);
                  setApprovals([]);
                  setEvents([]);
                  setCatalog([]);
                  setMetrics(null);
                  setSelected(null);
                }}
              >
                Switch identity
              </button>
            </div>
          )}
          {error && (
            <div role="alert" className="alert error">
              {error}
            </div>
          )}
          {notice && (
            <div role="status" className="alert success">
              {notice}
            </div>
          )}
          {tab === "Overview" && (
            <>
              <div className="stats">
                {[
                  [
                    "Diagnostic success",
                    metrics ? percent(metrics.success_rate) : "No data",
                    "Healthy or actionable findings",
                  ],
                  ["Automations available", "10", "Across Linux, delivery, and cloud"],
                  [
                    "Effort avoided",
                    metrics?.baseline_runs
                      ? `${metrics.estimated_effort_avoided_seconds.toFixed(1)}s`
                      : "Unmeasured",
                    "Only runs with a supplied baseline",
                  ],
                  ["Awaiting approval", String(pending), "Independent review required"],
                ].map(([label, value, note]) => (
                  <div className="stat panel" key={label}>
                    <div className="stat-label">
                      {label}
                      <span>↗</span>
                    </div>
                    <strong>{value}</strong>
                    <small>{note}</small>
                  </div>
                ))}
              </div>
              <div className="overview-grid">
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Reliability pulse</h2>
                      <p>Latest 20 diagnostic outcomes</p>
                    </div>
                    <span className="badge neutral">LIVE RECORDS</span>
                  </div>
                  <div className="pulse">
                    {runs.length ? (
                      runs
                        .slice(0, 20)
                        .reverse()
                        .map((r) => (
                          <button
                            title={`${r.request.runbook}: ${r.status}`}
                            key={r.id}
                            onClick={() => setSelected(r)}
                            className={`pulse-bar ${r.status}`}
                          >
                            <span>{r.seconds.toFixed(2)}s</span>
                          </button>
                        ))
                    ) : (
                      <div className="empty">Run an automation to build your reliability history.</div>
                    )}
                  </div>
                  <div className="legend">
                    <span>
                      <i className="green" />
                      Healthy
                    </span>
                    <span>
                      <i className="amber" />
                      Finding
                    </span>
                    <span>
                      <i className="red" />
                      Unavailable / failed
                    </span>
                  </div>
                  <div className="panel-footer">
                    <span>
                      Repeatability <strong>{metrics ? percent(metrics.repeatability) : "No data"}</strong>
                    </span>
                    <span>
                      Intervention required <strong>{metrics?.intervention_runs ?? 0} runs</strong>
                    </span>
                  </div>
                </section>
                <section className="panel recovery">
                  <div className="panel-heading">
                    <div>
                      <h2>Controlled recovery</h2>
                      <p>Disposable service troubleshooting lab</p>
                    </div>
                    <span className="orb">◇</span>
                  </div>
                  <ol>
                    <li>
                      <span>01</span>Detect and collect evidence
                    </li>
                    <li>
                      <span>02</span>Request independent approval
                    </li>
                    <li>
                      <span>03</span>Execute and verify recovery
                    </li>
                  </ol>
                  <button
                    disabled={!token || busy}
                    onClick={() =>
                      action(async () => {
                        await api("lab/inject", {});
                        await refresh();
                        setNotice("Disposable service failure injected. Run the service lab diagnostic.");
                      })
                    }
                  >
                    Inject lab failure <span>↗</span>
                  </button>
                  <small>Changes only the process-owned lab service.</small>
                </section>
              </div>
              <Recent runs={runs.slice(0, 5)} select={setSelected} />
              <div className="measurement panel">
                <div>
                  <h2>Measure the toil, honestly.</h2>
                  <p>Manual baselines are operator-supplied. No team productivity claim is inferred.</p>
                </div>
                <div>
                  <span>MANUAL BASELINE</span>
                  <strong>
                    {metrics?.baseline_runs ? `${metrics.manual_seconds.toFixed(2)}s` : "No baseline"}
                  </strong>
                </div>
                <div>
                  <span>BASELINE-MATCHED AUTOMATION</span>
                  <strong>
                    {metrics?.baseline_runs
                      ? `${metrics.baseline_automated_seconds.toFixed(2)}s`
                      : "No baseline"}
                  </strong>
                </div>
              </div>
            </>
          )}
          {tab === "Automations" && (
            <>
              <div className="toolbar panel">
                <label>
                  Target
                  <select aria-label="Target" value={target} onChange={(e) => setTarget(e.target.value)}>
                    <option value="fixture">Fixture analysis</option>
                    <option value="local">Local system</option>
                    <option value="lab">Disposable service lab</option>
                  </select>
                </label>
                <label>
                  Fixture scenario
                  <select
                    aria-label="Fixture scenario"
                    value={scenario}
                    onChange={(e) => setScenario(e.target.value)}
                  >
                    <option value="failure">Supported failure</option>
                    <option value="healthy">Healthy</option>
                    <option value="unavailable">Unavailable</option>
                  </select>
                </label>
                <label>
                  Manual baseline (seconds)
                  <input
                    aria-label="Manual baseline seconds"
                    type="number"
                    min="0"
                    max="86400"
                    step="0.1"
                    value={baseline}
                    onChange={(e) => setBaseline(e.target.value)}
                  />
                </label>
                <label>
                  Baseline source
                  <input
                    value={baselineSource}
                    onChange={(e) => setBaselineSource(e.target.value)}
                    placeholder="Measured procedure or stated assumption"
                  />
                </label>
                <p>Fixture inputs are simulated. Label baseline assumptions explicitly.</p>
              </div>
              <div className="catalog">
                {catalog.map((c, i) => (
                  <article className="panel book" key={c.id}>
                    <span className="book-number">{String(i + 1).padStart(2, "0")}</span>
                    <span className="badge neutral">READ ONLY</span>
                    <h2>{c.id[0].toUpperCase() + c.id.slice(1)}</h2>
                    <p>{c.description}</p>
                    <div className="book-footer">
                      <small>{c.remediation ? "Lab recovery available" : "Diagnostic evidence"}</small>
                      <button disabled={busy || !c.targets.includes(target)} onClick={() => diagnose(c.id)}>
                        Run →
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}
          {tab === "Run history" && <Recent runs={runs} select={setSelected} />}
          {tab === "Approvals" && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Approval queue</h2>
                  <p>Approvers cannot approve their own requests or execute their decisions.</p>
                </div>
              </div>
              <label className="reason">
                Decision reason
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Explain the decision (at least 8 characters)"
                />
              </label>
              {approvals.length ? (
                approvals.map((a) => (
                  <div className="approval" key={a.id}>
                    <div>
                      <strong>
                        {runs.find((r) => r.id === a.run_id)?.request.runbook === "security"
                          ? "Repair disposable security configuration"
                          : "Recover disposable service"}
                      </strong>
                      <p>
                        {short(a.run_id)} · requested by {a.requester}
                      </p>
                      <small>Expires {new Date(a.expires * 1000).toLocaleTimeString()}</small>
                    </div>
                    <span className={`badge ${a.state}`}>{a.state}</span>
                    {a.state === "pending" && (
                      <>
                        <button
                          disabled={busy || reason.length < 8}
                          onClick={() =>
                            action(async () => {
                              await api(`approvals/${a.id}/decision`, { decision: "reject", reason });
                              await refresh();
                            })
                          }
                        >
                          Reject
                        </button>
                        <button
                          className="primary"
                          disabled={busy || reason.length < 8}
                          onClick={() =>
                            action(async () => {
                              await api(`approvals/${a.id}/decision`, { decision: "approve", reason });
                              await refresh();
                            })
                          }
                        >
                          Approve
                        </button>
                      </>
                    )}
                    {a.state === "approved" && (
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() =>
                          action(async () => {
                            const r = await api<Run>(`approvals/${a.id}/execute`, {});
                            setSelected(r);
                            await refresh();
                          })
                        }
                      >
                        Execute recovery
                      </button>
                    )}
                  </div>
                ))
              ) : (
                <div className="empty">No remediation requests. Diagnose the service lab to begin.</div>
              )}
            </section>
          )}
          {tab === "Audit trail" && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>Audit events</h2>
                  <p>Append-only application events with a SHA-256 hash chain.</p>
                </div>
              </div>
              {events.map((e) => (
                <div className="audit" key={e.seq}>
                  <span className="audit-index">{String(e.seq).padStart(3, "0")}</span>
                  <div>
                    <strong>{e.event.replaceAll("_", " ")}</strong>
                    <p>
                      {e.actor} · {short(e.subject)} · {new Date(e.at * 1000).toLocaleString()}
                    </p>
                  </div>
                  <code title={e.digest}>{e.digest.slice(0, 12)}</code>
                </div>
              ))}
              {!events.length && <div className="empty">No audit events yet.</div>}
            </section>
          )}
          <footer>
            OpsPilot <span>Evidence before action. Approval before change.</span>
            <span>Local lab · v0.1.1</span>
          </footer>
        </div>
      </main>
      {selected && (
        <div className="modal-backdrop">
          <section
            className="modal panel"
            role="dialog"
            aria-modal="true"
            onKeyDown={(e) => {
              if (e.key === "Escape") setSelected(null);
              if (e.key === "Tab") {
                const items = e.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)");
                const first = items[0],
                  last = items[items.length - 1];
                if (e.shiftKey && document.activeElement === first) {
                  e.preventDefault();
                  last?.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                  e.preventDefault();
                  first?.focus();
                }
              }
            }}
            aria-label="Run evidence"
          >
            <div className="panel-heading">
              <div>
                <div className="eyebrow">RUN {short(selected.id)}</div>
                <h2>{selected.request.runbook} evidence</h2>
              </div>
              <button autoFocus aria-label="Close evidence" onClick={() => setSelected(null)}>
                ✕
              </button>
            </div>
            <div className="evidence-meta">
              <span className={`badge ${selected.status}`}>{selected.status}</span>
              <span>{selected.request.target} target</span>
              <span>{selected.seconds.toFixed(3)} seconds</span>
            </div>
            {selected.findings.map((f) => (
              <div className="finding" key={f.code}>
                <strong>{f.summary}</strong>
                <p>{f.recommendation}</p>
              </div>
            ))}
            {selected.remediation && (
              <div className={`alert ${selected.remediation.verified ? "success" : "error"}`}>
                Recovery {selected.remediation.outcome}. Verification: {String(selected.remediation.verified)}
                .
              </div>
            )}
            <h3>Collected evidence</h3>
            <pre>{JSON.stringify(selected.evidence, null, 2)}</pre>
            {selected.status === "finding" && selected.request.target === "lab" && (
              <button
                className="primary"
                disabled={busy}
                onClick={() =>
                  action(async () => {
                    await api(`runs/${selected.id}/approval`, {});
                    await refresh();
                    setSelected(null);
                    setTab("Approvals");
                    setNotice("Recovery requested. An independent approver must review.");
                  })
                }
              >
                Request recovery approval
              </button>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
function Recent({ runs, select }: { runs: Run[]; select: (r: Run) => void }) {
  return (
    <section className="panel recent">
      <div className="panel-heading">
        <div>
          <h2>Execution history</h2>
          <p>Diagnostic outcomes and supporting evidence</p>
        </div>
        <span className="muted">{runs.length} runs</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Automation</th>
              <th>Target</th>
              <th>Status</th>
              <th>Duration</th>
              <th>Started</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.request.runbook}</strong>
                  <small>{short(r.id)}</small>
                </td>
                <td>{r.request.target}</td>
                <td>
                  <span className={`badge ${r.status}`}>{r.status}</span>
                </td>
                <td>{r.seconds.toFixed(3)}s</td>
                <td>{new Date(r.started_at * 1000).toLocaleTimeString()}</td>
                <td>
                  <button aria-label={`View ${r.request.runbook} evidence`} onClick={() => select(r)}>
                    View ↗
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!runs.length && <div className="empty">Your execution history will appear here.</div>}
      </div>
    </section>
  );
}
const root = document.getElementById("root");
if (!root) throw new Error("Missing application root");
createRoot(root).render(<App />);
