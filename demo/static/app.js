const $ = (id) => document.getElementById(id);
let appKey = "",
  operatorKey = "",
  current = null,
  members = [],
  report = null,
  activeRun = null;
function notice(message) {
  $("notice").textContent = message;
}
function node(tag, text, className) {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}
async function api(path, options = {}, operator = false) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + (operator ? operatorKey : appKey),
      ...options.headers,
    },
  });
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      `HTTP ${response.status}: ${body.detail || "Request failed"}${body.request_id ? " · request " + body.request_id : ""}`,
    );
  return body;
}
async function customers(selectId) {
  const data = await api("/v1/customers?limit=100");
  if (selectId && !data.items.some((item) => item.id === selectId))
    data.items.push(await api(`/v1/customers/${selectId}`));
  $("customer").replaceChildren(node("option", "Choose a customer"));
  $("customer").firstChild.value = "";
  for (const item of data.items) {
    const option = node("option", item.name);
    option.value = item.id;
    $("customer").append(option);
  }
  if (selectId) {
    $("customer").value = selectId;
    await selectCustomer();
  } else if (!data.items.length)
    notice("No accounts yet. Use the lab operator controls below to create one.");
}
function memberChanged() {
  const member = members.find((item) => item.id === $("member").value);
  $("permissions").textContent = member ? member.role + " · " + member.permissions.join(", ") : "";
}
async function selectCustomer() {
  current = $("customer").value;
  report = null;
  $("export").disabled = true;
  if (!current) return;
  const [config, roster, reports] = await Promise.all([
    api(`/v1/customers/${current}`),
    api(`/v1/customers/${current}/members`),
    api(`/v1/customers/${current}/reports`),
  ]);
  $("config").textContent =
    `Customer ${config.id}\nExports ${config.exports_enabled ? "enabled" : "disabled"} · config v${config.config_version}`;
  members = roster.items;
  $("member").replaceChildren(
    ...members.map((member) => {
      const option = node("option", member.name + " — " + member.role);
      option.value = member.id;
      return option;
    }),
  );
  memberChanged();
  report = reports.items[0];
  $("report").replaceChildren();
  if (report) {
    $("report").append(node("h3", report.title));
    const table = document.createElement("table");
    const header = document.createElement("tr");
    header.append(node("th", "Month"), node("th", "Revenue USD"));
    table.append(header);
    for (const row of report.rows) {
      const tr = document.createElement("tr");
      tr.append(node("td", row.month), node("td", row.revenue_usd.toLocaleString()));
      table.append(tr);
    }
    $("report").append(table);
    $("export").disabled = false;
  }
  await refresh();
}
async function download(job) {
  const response = await fetch(
    `/v1/customers/${current}/jobs/${job.id}/download?member_id=${$("member").value}`,
    { headers: { Authorization: "Bearer " + appKey } },
  );
  if (!response.ok) {
    const error = await response.json();
    throw new Error(`HTTP ${response.status}: ${error.detail}`);
  }
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "revenue-export.csv";
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function refresh() {
  if (!current) return;
  const [jobs, logs] = await Promise.all([
    api(`/v1/customers/${current}/jobs`),
    api(`/v1/customers/${current}/logs`),
  ]);
  $("jobs").replaceChildren();
  for (const job of jobs.items) {
    const row = document.createElement("div");
    row.append(
      node("span", job.state, job.state === "failed" ? "error" : "state"),
      node(
        "p",
        `${job.id} · request ${job.request_id}${job.error_code ? " · " + job.error_code : ""}`,
      ),
    );
    if (job.state === "completed") {
      const button = node("button", "Download CSV", "secondary");
      button.addEventListener("click", () => download(job).catch((e) => notice(e.message)));
      row.append(button);
    }
    $("jobs").append(row);
  }
  if (!jobs.items.length)
    $("jobs").textContent = "No jobs: inspect request logs to see whether creation was rejected.";
  $("coverage").textContent =
    `Log coverage: ${logs.coverage}. ${logs.coverage === "partial" ? "Some downstream evidence is unavailable; a single root cause may not be provable." : "Available records for this customer."}`;
  $("logs").replaceChildren(
    ...logs.items.map((log) => {
      const row = document.createElement("div");
      row.append(
        node("strong", `${log.event} · HTTP ${log.status_code}`),
        node("p", log.message_redacted),
        node("span", `${log.observed_at} · ${log.request_id}`),
      );
      return row;
    }),
  );
}
$("access-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  appKey = $("app-key").value;
  try {
    await customers();
    notice("Connected. Choose a customer or create a lab scenario.");
  } catch (e) {
    notice(e.message);
  }
});
$("customer").addEventListener("change", () => selectCustomer().catch((e) => notice(e.message)));
$("member").addEventListener("change", memberChanged);
$("refresh").addEventListener("click", () => refresh().catch((e) => notice(e.message)));
$("export").addEventListener("click", async () => {
  $("export").disabled = true;
  try {
    const job = await api(`/v1/customers/${current}/exports`, {
      method: "POST",
      body: JSON.stringify({ member_id: $("member").value, report_id: report.id }),
    });
    $("request").textContent = `Accepted request ${job.request_id}. Refresh to observe processing.`;
    notice("Export accepted.");
  } catch (e) {
    notice(e.message);
  } finally {
    $("export").disabled = false;
    await refresh().catch((e) => notice(e.message));
  }
});
$("operator-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  operatorKey = $("operator-key").value;
  try {
    const data = await api("/lab/scenarios", {}, true);
    $("scenario").replaceChildren(
      ...data.items.map((name) => {
        const option = node("option", name.replaceAll("_", " "));
        option.value = name;
        return option;
      }),
    );
    $("scenario-form").hidden = false;
    notice("Operator controls unlocked for this page only.");
  } catch (e) {
    notice(e.message);
  }
});
function showRun(run) {
  activeRun = run;
  $("run").textContent =
    `Run ${run.run_id} · generation ${run.generation} · customer ${run.customer_id} · probe HTTP ${run.probe.status_code}`;
  $("reset").hidden = false;
}
$("scenario-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const run = await api(
      "/lab/runs",
      { method: "POST", body: JSON.stringify({ scenario: $("scenario").value }) },
      true,
    );
    showRun(run);
    if (appKey) await customers(run.customer_id);
    notice(`Scenario created. Probe returned HTTP ${run.probe.status_code}.`);
  } catch (e) {
    notice(e.message);
  }
});
$("reset").addEventListener("click", async () => {
  if (!activeRun) return;
  try {
    const run = await api(
      `/lab/runs/${activeRun.run_id}/reset`,
      { method: "POST", body: "{}" },
      true,
    );
    showRun(run);
    if (appKey) await customers(run.customer_id);
    notice(
      "Run reset: permissions and exports restored; old lab jobs/logs replaced with a healthy probe.",
    );
  } catch (e) {
    notice(e.message);
  }
});
