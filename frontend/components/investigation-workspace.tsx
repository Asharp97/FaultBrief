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
type Job = {
  phase: string;
  completed_steps: number;
  attempts: number;
  max_attempts: number;
  available_at: string;
  last_error_code: string | null;
  investigation_mode: "baseline" | "model_selected";
  stop_reason: string | null;
  model_call_count: number;
  reserved_model_cost_usd: string;
};
type ModelCall = {
  id: string;
  sequence: number;
  purpose: string;
  state: string;
  reserved_cost_usd: string;
  error_code: string | null;
};

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

export function InvestigationWorkspace({
  workspace,
  userId,
  showDemoSetup,
}: {
  workspace: { id: string; name: string };
  userId: string;
  showDemoSetup: boolean;
}) {
  const base = `/api/faultbrief/workspaces/${workspace.id}`;
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [owner, setOwner] = useState(false);
  const [items, setItems] = useState<Investigation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [checks, setChecks] = useState<Check[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [modelCalls, setModelCalls] = useState<ModelCall[]>([]);
  const submission = useRef<{ payload: string; id: string } | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [caseRefresh, setCaseRefresh] = useState(0);
  const pollingDeadline = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const [affected, cases, members] = await Promise.all([
          fetch(`${base}/customers?limit=100`, { signal: controller.signal }).then(read),
          fetch(`${base}/investigations?limit=50`, { signal: controller.signal }).then(read),
          fetch(`${base}/memberships?limit=100`, { signal: controller.signal }).then(read),
        ]);
        setCustomers(affected.items);
        setOwner(
          members.items.some(
            (member: { user_id: string; active: boolean; role: string }) =>
              member.user_id === userId && member.active && member.role === "owner",
          ),
        );
        setItems(cases.items);
      } catch (error) {
        if (!controller.signal.aborted)
          setMessage(error instanceof Error ? error.message : "Could not load investigations.");
      }
    }
    void load();
    return () => controller.abort();
  }, [base, refresh, userId]);

  const choose = useCallback((id: string) => {
    setSelected(id);
    setCaseRefresh((value) => value + 1);
    setInvestigation(null);
    setReport(null);
    setEvidence([]);
    setChecks([]);
    setJob(null);
    setModelCalls([]);
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
        const jobs = await fetch(`${base}/investigations/${selected}/jobs`, {
          signal: controller.signal,
        }).then(read);
        setJob(jobs.items[0] || null);
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
        const [records, calls, models] = await Promise.all([
          fetch(`${base}/investigations/${selected}/evidence?limit=100`, {
            signal: controller.signal,
          }).then(read),
          fetch(`${base}/investigations/${selected}/tool-calls?limit=100`, {
            signal: controller.signal,
          }).then(read),
          fetch(`${base}/investigations/${selected}/model-calls?limit=100`, {
            signal: controller.signal,
          }).then(read),
        ]);
        setEvidence(records.items);
        setChecks(calls.items);
        setModelCalls(models.items);
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
      const payload = {
        customer_id: fields.get("customer_id"),
        question: fields.get("question"),
        context,
      };
      const signature = JSON.stringify(payload);
      if (submission.current?.payload !== signature)
        submission.current = { payload: signature, id: crypto.randomUUID() };
      const item: Investigation = await read(
        await fetch(`${base}/investigations`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...payload, submission_id: submission.current.id }),
        }),
      );
      submission.current = null;
      setItems((current) => [item, ...current.filter((row) => row.id !== item.id)]);
      choose(item.id);
      form.reset();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not submit the ticket.");
    } finally {
      setBusy(false);
    }
  }

  const setupCommand = `pnpm run demo:connect -- --workspace-id ${workspace.id} --owner-user-id ${userId}`;

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
            <div className="customer-onboarding" aria-label="Set up your first investigation">
              <h4>Connect an affected customer first</h4>
              <p className="account-muted">
                Your team is ready. An affected customer is an account in the app you investigate,
                separate from your FaultBrief teammates. Connect an account to give the investigator
                records to check.
              </p>
              {showDemoSetup && owner ? (
                <details open>
                  <summary>Try a local Ledger sample</summary>
                  <ol>
                    <li>
                      Configure the local demo once: <code>pnpm run demo:configure</code>, then{" "}
                      <code>node scripts/configure-diagnostics.mjs</code>.
                    </li>
                    <li>
                      Start the services and investigator without model calls:{" "}
                      <code>pnpm run dev --worker --baseline</code>.
                    </li>
                    <li>
                      In another terminal at the repository root, run this command to create and
                      connect a sample account:
                    </li>
                  </ol>
                  <pre className="setup-command">{setupCommand}</pre>
                  <button
                    className="button button-outline button-small"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(setupCommand);
                        setMessage(
                          "Demo setup command copied. Run it in a second terminal, then refresh customers.",
                        );
                      } catch {
                        setMessage("Select and copy the demo setup command above.");
                      }
                    }}
                  >
                    Copy demo setup command
                  </button>
                  <p className="account-muted">
                    After it prints “connected”, refresh customers, select the sample account, and
                    enter “Why did this customer's revenue export fail?” No model tuning is needed.
                  </p>
                </details>
              ) : (
                <p className="account-muted">
                  Ask the workspace owner to approve a customer diagnostic connection.
                </p>
              )}
            </div>
          )}
          <button
            className="button button-outline button-small"
            onClick={() => setRefresh((value) => value + 1)}
          >
            Refresh customers
          </button>
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
          {job && (
            <p className="account-muted" aria-label="Investigation progress">
              {job.phase.replaceAll("_", " ")} · {job.completed_steps} checks finished · attempt{" "}
              {job.attempts}/{job.max_attempts}
              {job.phase === "retry_wait" && (
                <> · retry after {new Date(job.available_at).toLocaleTimeString()}</>
              )}
              {job.last_error_code && <> · {job.last_error_code.replaceAll("_", " ")}</>}
            </p>
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
          {job?.investigation_mode === "model_selected" && (
            <p className="account-muted" aria-label="Investigation routing">
              Model selected checks · {job.model_call_count} model requests · reserved estimate $
              {job.reserved_model_cost_usd}
              {job.stop_reason && <> · {job.stop_reason.replaceAll("_", " ")}</>}
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
          {modelCalls.length > 0 && (
            <details>
              <summary>Model request audit ({modelCalls.length})</summary>
              <ul>
                {modelCalls.map((call) => (
                  <li key={call.id}>
                    {call.sequence}. {call.purpose}: {call.state} · reserved estimate $
                    {call.reserved_cost_usd}
                    {call.error_code && <> · {call.error_code.replaceAll("_", " ")}</>}
                  </li>
                ))}
              </ul>
            </details>
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
