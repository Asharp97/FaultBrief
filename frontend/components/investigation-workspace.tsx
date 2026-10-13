"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

type Customer = { id: string; name: string; external_id: string };
type Investigation = {
  id: string;
  customer_id: string;
  question: string;
  state: "queued" | "running" | "completed" | "inconclusive" | "failed";
};
type Evidence = {
  id: string;
  title: string;
  source_ref: string;
  source_version: string | null;
  excerpt_redacted: string;
  observed_at: string;
};
type Report = {
  id: string;
  summary: string;
  root_cause: string | null;
  observed_facts: string[];
  next_steps: string[];
  confidence: number;
  limitations: string[];
  suggested_team: string | null;
  explanation_source: "rules" | "model" | "rules_fallback";
  citations: { evidence_id: string; quote: string | null }[];
};
type Check = { id: string; tool_name: string; state: string };

async function read(response: Response) {
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string" ? body.detail : "The request could not be completed.",
    );
  return body;
}
const referencePattern =
  "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";

export function InvestigationWorkspace({ workspace }: { workspace: { id: string; name: string } }) {
  const base = `/api/faultbrief/workspaces/${workspace.id}`;
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [items, setItems] = useState<Investigation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [checks, setChecks] = useState<Check[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [caseRefresh, setCaseRefresh] = useState(0);
  const pollingDeadline = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const [affected, cases] = await Promise.all([
          fetch(`${base}/customers?limit=100`, { signal: controller.signal }).then(read),
          fetch(`${base}/investigations?limit=50`, { signal: controller.signal }).then(read),
        ]);
        setCustomers(affected.items);
        setItems(cases.items);
      } catch (error) {
        if (!controller.signal.aborted)
          setMessage(error instanceof Error ? error.message : "Could not load investigations.");
      }
    }
    void load();
    return () => controller.abort();
  }, [base, refresh]);

  const choose = useCallback((id: string) => {
    setSelected(id);
    setCaseRefresh((value) => value + 1);
    setInvestigation(null);
    setReport(null);
    setEvidence([]);
    setChecks([]);
    setMessage("");
    pollingDeadline.current = Date.now() + 120000;
  }, []);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const current: Investigation = await read(
          await fetch(`${base}/investigations/${selected}`, { signal: controller.signal }),
        );
        setInvestigation(current);
        setItems((rows) => rows.map((row) => (row.id === current.id ? current : row)));
        if (current.state === "queued" || current.state === "running") {
          if (Date.now() < pollingDeadline.current) timer = setTimeout(() => void load(), 1500);
          else
            setMessage(
              "This investigation is taking longer than expected. Select it again to check progress.",
            );
          return;
        }
        const [records, calls] = await Promise.all([
          fetch(`${base}/investigations/${selected}/evidence?limit=100`, {
            signal: controller.signal,
          }).then(read),
          fetch(`${base}/investigations/${selected}/tool-calls?limit=100`, {
            signal: controller.signal,
          }).then(read),
        ]);
        setEvidence(records.items);
        setChecks(calls.items);
        if (current.state !== "failed") {
          setReport(
            await read(
              await fetch(`${base}/investigations/${selected}/report`, {
                signal: controller.signal,
              }),
            ),
          );
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setReport(null);
          setEvidence([]);
          setChecks([]);
          setMessage(error instanceof Error ? error.message : "Could not read this investigation.");
        }
      }
    }
    void load();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [base, selected, caseRefresh]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setBusy(true);
    setMessage("");
    try {
      const context: Record<string, string> = {};
      for (const field of ["member_id", "request_id", "job_id"]) {
        const value = String(fields.get(field) || "").trim();
        if (value) context[field] = value;
      }
      const item: Investigation = await read(
        await fetch(`${base}/investigations`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            customer_id: fields.get("customer_id"),
            question: fields.get("question"),
            context,
          }),
        }),
      );
      setItems((current) => [item, ...current]);
      choose(item.id);
      form.reset();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not submit the ticket.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="account-card investigation-section"
      aria-label={`Investigations for ${workspace.name}`}
    >
      <p className="account-eyebrow">Support investigation</p>
      <h2>Investigations: {workspace.name}</h2>
      <p className="account-muted">
        Choose the affected customer and describe the issue. Review the collected evidence before
        acting on a finding.
      </p>
      {message && (
        <p className="account-notice" role="status">
          {message}
        </p>
      )}
      <div className="investigation-grid">
        <div>
          <h3>Submit a ticket</h3>
          {customers.length ? (
            <form className="account-form" onSubmit={submit}>
              <label>
                Affected customer
                <select name="customer_id" required>
                  {customers.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                What went wrong?
                <textarea
                  name="question"
                  required
                  minLength={10}
                  maxLength={4000}
                  placeholder="Revenue exports fail for one account."
                />
              </label>
              <details className="reference-fields">
                <summary>Add request references (optional)</summary>
                <p className="account-muted">
                  References help match the affected user and the exact failing request.
                </p>
                <label>
                  Affected user reference
                  <input name="member_id" pattern={referencePattern} />
                </label>
                <label>
                  Request reference
                  <input name="request_id" pattern={referencePattern} />
                </label>
                <label>
                  Export job reference
                  <input name="job_id" pattern={referencePattern} />
                </label>
              </details>
              <button className="button button-teal" disabled={busy}>
                {busy ? "Submitting…" : "Investigate ticket"}
              </button>
            </form>
          ) : (
            <p className="account-muted">
              No affected customers yet. Ask your workspace administrator to connect the customer
              you want to investigate.
            </p>
          )}
          <div className="investigation-list-heading">
            <h3>Recent investigations</h3>
            <button
              className="button button-outline button-small"
              onClick={() => setRefresh((value) => value + 1)}
            >
              Refresh list
            </button>
          </div>
          <ul className="workspace-list">
            {items.map((item) => (
              <li key={item.id}>
                <button
                  className="investigation-choice"
                  aria-pressed={selected === item.id}
                  onClick={() => choose(item.id)}
                >
                  <span className="case-status">{item.state}</span>
                  <strong>{item.question}</strong>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="investigation-result" aria-live="polite">
          {!selected && (
            <p className="account-muted">
              Select an investigation to review its finding and evidence.
            </p>
          )}
          {selected && !investigation && <p>Loading investigation…</p>}
          {investigation && (
            <>
              <p className="account-eyebrow">{investigation.state}</p>
              <p className="account-muted">{investigation.question}</p>
            </>
          )}
          {investigation?.state === "queued" && (
            <p>Waiting for the investigator to collect evidence.</p>
          )}
          {investigation?.state === "running" && (
            <p>Collecting diagnostic records and preparing a finding…</p>
          )}
          {investigation?.state === "failed" && (
            <p>
              This investigation could not finish. Check workspace access and ask your administrator
              to review the service.
            </p>
          )}
          {report && (
            <article aria-label="Investigation report">
              <h3>{report.root_cause || "No root cause established"}</h3>
              <p>{report.summary}</p>
              <p className="account-muted">
                {report.explanation_source === "model"
                  ? "AI explanation"
                  : report.explanation_source === "rules_fallback"
                    ? "Baseline finding · AI explanation unavailable"
                    : "Evidence-based baseline"}{" "}
                · Assessment confidence: {Math.round(report.confidence * 100)}%
              </p>
              <h4>Observed facts</h4>
              <ul>
                {report.observed_facts.map((fact, index) => (
                  <li key={index}>{fact}</li>
                ))}
              </ul>
              {report.limitations.length > 0 && (
                <>
                  <h4>Uncertainty and limitations</h4>
                  <ul>
                    {report.limitations.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                </>
              )}
              <h4>Suggested next steps</h4>
              <ol>
                {report.next_steps.map((step, index) => (
                  <li key={index}>{step}</li>
                ))}
              </ol>
              {report.suggested_team && (
                <p>
                  <strong>Suggested handoff:</strong> {report.suggested_team}
                </p>
              )}
              <h4>Supporting evidence</h4>
              <ul>
                {report.citations.map((citation, index) => (
                  <li key={citation.evidence_id}>
                    <a className="account-link" href={`#evidence-${citation.evidence_id}`}>
                      [{index + 1}]{" "}
                      {evidence.find((item) => item.id === citation.evidence_id)?.title ||
                        "Evidence record"}
                    </a>
                    {citation.quote && <blockquote>{citation.quote}</blockquote>}
                  </li>
                ))}
              </ul>
            </article>
          )}
          {checks.length > 0 && (
            <details>
              <summary>Diagnostic checks</summary>
              <ul>
                {checks.map((check) => (
                  <li key={check.id}>
                    {check.tool_name}: {check.state}
                  </li>
                ))}
              </ul>
            </details>
          )}
          {evidence.length > 0 && (
            <details open className="evidence-list">
              <summary>Collected evidence ({evidence.length})</summary>
              {evidence.map((item) => (
                <article key={item.id} id={`evidence-${item.id}`}>
                  <h4>{item.title}</h4>
                  <code>
                    {item.source_ref}
                    {item.source_version ? ` · version ${item.source_version}` : ""}
                  </code>
                  <p className="account-muted">
                    Observed {new Date(item.observed_at).toLocaleString()}
                  </p>
                  <pre>{item.excerpt_redacted}</pre>
                </article>
              ))}
            </details>
          )}
        </div>
      </div>
    </section>
  );
}
