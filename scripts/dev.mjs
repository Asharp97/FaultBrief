import { createServer } from "node:net";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { environment, pnpm, root, start, startUv, stop } from "./lib.mjs";

const args = process.argv.slice(2);
const smoke = args.includes("--smoke");
const children = [];
const generatedFiles = [];
let stopping = false;

function captureGeneratedFiles() {
  for (const filename of ["next-env.d.ts", "tsconfig.json"]) {
    const path = join(root, "frontend", filename);
    if (existsSync(path)) generatedFiles.push({ path, content: readFileSync(path) });
  }
}

function restoreGeneratedFiles() {
  for (const { path, content } of generatedFiles) {
    if (existsSync(path) && readFileSync(path, "utf8").includes(".next-smoke/")) {
      writeFileSync(path, content);
    }
  }
}

function requestedPort(flag, fallback) {
  const index = args.indexOf(flag);
  if (index === -1) return fallback;
  const raw = args[index + 1];
  const value = Number(raw);
  if (!raw || !/^\d+$/.test(raw) || !Number.isInteger(value) || value < 1024 || value > 65535) {
    throw new Error(`${flag} requires a port between 1024 and 65535.`);
  }
  return value;
}

async function availablePort(preferred) {
  return await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(preferred, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : null;
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

async function shutdown(code = 0) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  await Promise.all(children.map(stop));
  restoreGeneratedFiles();
}

function watch(child, name) {
  children.push(child);
  child.once("error", (error) => {
    if (!stopping) {
      console.error(`${name} could not start: ${error.message}`);
      void shutdown(1);
    }
  });
  child.once("exit", (code) => {
    if (!stopping) {
      console.error(`${name} stopped unexpectedly (exit ${code ?? "signal"}).`);
      void shutdown(1);
    }
  });
}

async function ready(url, expectedService, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline && !stopping) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1500) });
      if (response.ok) {
        if (expectedService) {
          const body = await response.json();
          if (body.status === "ok" && body.service === expectedService) return;
        } else {
          const html = await response.text();
          if (html.includes("FaultBrief") && html.includes("Follow the evidence")) return;
        }
      }
    } catch {
      /* Startup can briefly refuse connections. */
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Service did not become ready: ${url}`);
}

process.once("SIGINT", () => void shutdown());
process.once("SIGTERM", () => void shutdown());

try {
  const ports = {
    frontend: await availablePort(smoke ? 0 : requestedPort("--frontend-port", 3000)),
    api: await availablePort(smoke ? 0 : requestedPort("--api-port", 8000)),
    demo: await availablePort(smoke ? 0 : requestedPort("--demo-port", 8001)),
  };
  if (new Set(Object.values(ports)).size !== 3) throw new Error("Services require distinct ports.");
  console.log(`Frontend: http://localhost:${ports.frontend}`);
  console.log(`API: http://127.0.0.1:${ports.api}/health`);
  console.log(`Demo: http://127.0.0.1:${ports.demo}/health`);
  if (smoke) captureGeneratedFiles();
  watch(
    start(
      pnpm,
      ["--dir", "frontend", "dev", "--hostname", "127.0.0.1", "--port", String(ports.frontend)],
      smoke ? { env: { ...environment(), FAULTBRIEF_SMOKE: "1" } } : {},
    ),
    "Frontend",
  );
  watch(
    startUv([
      "run",
      "--project",
      "backend",
      "--locked",
      "uvicorn",
      "--app-dir",
      join(root, "backend"),
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(ports.api),
    ]),
    "API",
  );
  watch(
    startUv([
      "run",
      "--project",
      "backend",
      "--locked",
      "uvicorn",
      "--app-dir",
      join(root, "demo"),
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(ports.demo),
    ]),
    "Demo",
  );
  if (smoke) {
    await Promise.all([
      ready(`http://127.0.0.1:${ports.frontend}`),
      ready(`http://127.0.0.1:${ports.api}/health`, "faultbrief-api"),
      ready(`http://127.0.0.1:${ports.demo}/health`, "faultbrief-demo"),
    ]);
    console.log("Startup smoke check passed for frontend, API, and demo.");
    await shutdown();
  }
} catch (error) {
  console.error(
    error.code === "EADDRINUSE"
      ? "A requested port is occupied. Choose other ports; existing applications were not stopped."
      : error.message,
  );
  await shutdown(1);
}
