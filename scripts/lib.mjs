import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const root = dirname(dirname(fileURLToPath(import.meta.url)));
export const uvVersion = "0.12.23";
export const pnpm = "pnpm";
export const python = process.env.FAULTBRIEF_PYTHON || "python";

export function environment() {
  const modulePath = join(root, ".tools", "uv");
  return {
    ...process.env,
    PYTHONPATH: [modulePath, process.env.PYTHONPATH]
      .filter(Boolean)
      .join(process.platform === "win32" ? ";" : ":"),
    UV_CACHE_DIR: join(root, ".tools", "uv-cache"),
    UV_PYTHON_INSTALL_DIR: join(root, ".tools", "python"),
    NEXT_TELEMETRY_DISABLED: "1",
    PYTHONUNBUFFERED: "1",
  };
}

function processOptions(extra = {}) {
  return { cwd: root, env: environment(), stdio: "inherit", ...extra };
}

function invocation(command, args) {
  if (command !== pnpm) return { command, args };
  const entry = process.env.npm_execpath;
  if (!entry || !existsSync(entry)) {
    throw new Error(
      "Run this script through pnpm run so its package-manager executable can be located.",
    );
  }
  if (/\.[cm]?js$/i.test(entry)) {
    return { command: process.execPath, args: [entry, ...args] };
  }
  if (/\.cmd$/i.test(entry)) {
    throw new Error(
      "Install the Node.js version of pnpm; its JavaScript entry point is required on Windows.",
    );
  }
  return { command: entry, args };
}

export function run(command, args, extra = {}) {
  const executable = invocation(command, args);
  const result = spawnSync(executable.command, executable.args, processOptions(extra));
  if (result.error) throw result.error;
  if (result.status !== 0)
    throw new Error(`${command} failed with exit code ${result.status ?? "unknown"}`);
}

export function runUv(args, extra = {}) {
  if (!existsSync(join(root, ".tools", "uv", "uv"))) {
    throw new Error("Local uv is missing. Run pnpm run setup first.");
  }
  run(python, ["-m", "uv", ...args], extra);
}

export function start(command, args, extra = {}) {
  const executable = invocation(command, args);
  return spawn(executable.command, executable.args, {
    ...processOptions(extra),
    detached: process.platform !== "win32",
  });
}

export function startUv(args) {
  return start(python, ["-m", "uv", ...args]);
}

export async function stop(child) {
  if (!child.pid || child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise((resolve) => child.once("exit", resolve));
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
  }
  await Promise.race([exited, new Promise((resolve) => setTimeout(resolve, 4000))]);
}
