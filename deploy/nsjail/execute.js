#!/usr/bin/env node
"use strict";

/**
 * MCPWorks Sandbox Execution Wrapper (Node.js).
 *
 * Runs INSIDE the nsjail sandbox. Reads /sandbox/input.json,
 * executes /sandbox/user_code.js (pre-transpiled from TypeScript),
 * writes structured output to /sandbox/output.json.
 *
 * Supports four result patterns (matching Python execute.py):
 *   1. export default function main(input) — default export
 *   2. export default function handler(input, context) — with context
 *   3. module.exports.main / module.exports.handler — CommonJS
 *   4. module.exports.result / module.exports.output — assignment
 */

const fs = require("fs");
const path = require("path");

const SANDBOX_DIR = "/sandbox";
const INPUT_PATH = path.join(SANDBOX_DIR, "input.json");
const OUTPUT_PATH = path.join(SANDBOX_DIR, "output.json");
const CODE_PATH = path.join(SANDBOX_DIR, "user_code.js");
const ENV_PATH = path.join(SANDBOX_DIR, ".sandbox_env.json");
const CONTEXT_PATH = path.join(SANDBOX_DIR, "context.json");
const TOKEN_PATH = path.join(SANDBOX_DIR, ".exec_token");
const CALL_LOG_PATH = path.join(SANDBOX_DIR, ".call_log");

const MAX_STDOUT = 64 * 1024;
const MAX_STDERR = 64 * 1024;
const MAX_OUTPUT = 1024 * 1024;

function truncate(text, max, label) {
  if (!text || text.length <= max) return text || "";
  return text.slice(0, max) + `\n\n... [${label} truncated at ${max} bytes]`;
}

function writeOutput(obj) {
  try {
    let serialized = JSON.stringify(obj, (_key, v) =>
      typeof v === "bigint" ? v.toString() : v
    );
    if (serialized.length > MAX_OUTPUT) {
      obj = {
        success: false,
        result: null,
        stdout: truncate(obj.stdout || "", MAX_STDOUT, "stdout"),
        stderr: truncate(obj.stderr || "", MAX_STDERR, "stderr"),
        error: `Output too large (${serialized.length} bytes, limit ${MAX_OUTPUT})`,
        error_type: "OutputSizeError",
        call_log: [],
      };
      serialized = JSON.stringify(obj);
    }
    fs.writeFileSync(OUTPUT_PATH, serialized);
  } catch (e) {
    process.stderr.write(`Failed to write output: ${e.message}\n`);
  }
}

function safeRead(filePath) {
  try {
    return fs.readFileSync(filePath, "utf-8");
  } catch {
    return null;
  }
}

async function main() {
  // Delete execution token (ORDER-003)
  try {
    fs.unlinkSync(TOKEN_PATH);
  } catch {}

  // Self-destruct wrapper (F-36 equivalent)
  try {
    fs.unlinkSync(path.join(SANDBOX_DIR, ".e.js"));
  } catch {}

  // Load env vars from file, delete file, inject into process.env
  const envRaw = safeRead(ENV_PATH);
  if (envRaw) {
    try {
      const envData = JSON.parse(envRaw);
      fs.unlinkSync(ENV_PATH);
      if (envData && typeof envData === "object") {
        Object.assign(process.env, envData);
      }
    } catch {}
  }

  // Read input
  let inputData = {};
  const inputRaw = safeRead(INPUT_PATH);
  if (inputRaw) {
    try {
      inputData = JSON.parse(inputRaw);
    } catch {}
  }

  // Read context (agent state, metadata)
  let contextData = {};
  const contextRaw = safeRead(CONTEXT_PATH);
  if (contextRaw) {
    try {
      contextData = JSON.parse(contextRaw);
    } catch {}
  }

  // Capture stdout/stderr
  let capturedStdout = "";
  let capturedStderr = "";
  const origStdoutWrite = process.stdout.write.bind(process.stdout);
  const origStderrWrite = process.stderr.write.bind(process.stderr);
  process.stdout.write = (chunk) => {
    capturedStdout += String(chunk);
    return true;
  };
  process.stderr.write = (chunk) => {
    capturedStderr += String(chunk);
    return true;
  };

  let result = null;
  let error = null;
  let errorType = null;
  let success = true;

  try {
    const userModule = require(CODE_PATH);

    // Detect entry point (priority order matching spec):
    // 1. default export that is a function
    // 2. named export: main or handler
    // 3. named export: result or output (value, not function)
    let entryFn = null;

    if (userModule.__esModule && typeof userModule.default === "function") {
      entryFn = userModule.default;
    } else if (typeof userModule.default === "function") {
      entryFn = userModule.default;
    } else if (typeof userModule.main === "function") {
      entryFn = userModule.main;
    } else if (typeof userModule.handler === "function") {
      entryFn = userModule.handler;
    }

    if (entryFn) {
      const fnResult = entryFn(inputData, contextData);
      result = fnResult instanceof Promise ? await fnResult : fnResult;
    } else if (userModule.result !== undefined) {
      result = userModule.result;
    } else if (userModule.output !== undefined) {
      result = userModule.output;
    } else if (
      userModule.default !== undefined &&
      typeof userModule.default !== "function"
    ) {
      result = userModule.default;
    }

    // Await if result is a Promise (e.g. module.exports.result = asyncFn())
    if (result instanceof Promise) {
      result = await result;
    }
  } catch (e) {
    success = false;
    error = e.message || String(e);
    errorType = e.constructor ? e.constructor.name : "Error";
    capturedStderr += (e.stack || String(e)) + "\n";
  } finally {
    process.stdout.write = origStdoutWrite;
    process.stderr.write = origStderrWrite;
  }

  // Read call log (billing, same as Python FINDING-04)
  let callLog = [];
  const callLogRaw = safeRead(CALL_LOG_PATH);
  if (callLogRaw) {
    callLog = callLogRaw.split("\n").filter(Boolean);
  }

  writeOutput({
    success,
    result,
    stdout: truncate(capturedStdout, MAX_STDOUT, "stdout"),
    stderr: truncate(capturedStderr, MAX_STDERR, "stderr"),
    error,
    error_type: errorType,
    call_log: callLog,
  });
}

main().catch((e) => {
  writeOutput({
    success: false,
    result: null,
    stdout: "",
    stderr: (e.stack || String(e)) + "\n",
    error: e.message || String(e),
    error_type: "FatalError",
    call_log: [],
  });
  process.exit(1);
});
