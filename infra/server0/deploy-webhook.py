#!/usr/bin/env python3
"""Lightweight GitHub webhook receiver for pull-based deploys.

Listens on port 9000 for GitHub webhook POST requests.
Verifies HMAC-SHA256 signature, then runs the deploy script.

No dependencies beyond stdlib.
"""

import hashlib
import hmac
import http.server
import json
import os
import subprocess
import sys
import threading

WEBHOOK_SECRET = os.environ["DEPLOY_WEBHOOK_SECRET"]
DEPLOY_SCRIPT = os.environ.get("DEPLOY_SCRIPT", "/opt/mcpworks/deploy.sh")
LISTEN_PORT = int(os.environ.get("DEPLOY_LISTEN_PORT", "9000"))
REPO_FULL_NAME = os.environ.get("DEPLOY_REPO", "mcpworks/mcpworks-api")
DEPLOY_BRANCH = os.environ.get("DEPLOY_BRANCH", "refs/heads/main")


def verify_signature(payload: bytes, signature: str) -> bool:
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def run_deploy():
    try:
        result = subprocess.run(
            [DEPLOY_SCRIPT],
            capture_output=True, text=True, timeout=600
        )
        print(f"[deploy] exit={result.returncode}")
        if result.stdout:
            print(f"[deploy] stdout: {result.stdout[-500:]}")
        if result.stderr:
            print(f"[deploy] stderr: {result.stderr[-500:]}")
    except Exception as e:
        print(f"[deploy] error: {e}")


class WebhookHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/deploy":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(content_length)

        sig = self.headers.get("X-Hub-Signature-256", "")
        if not verify_signature(payload, sig):
            print("[webhook] invalid signature")
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"invalid signature")
            return

        event = self.headers.get("X-GitHub-Event", "")

        if event == "ping":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"pong")
            return

        if event == "push":
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                return

            ref = data.get("ref", "")
            repo = data.get("repository", {}).get("full_name", "")

            if ref != DEPLOY_BRANCH or repo != REPO_FULL_NAME:
                print(f"[webhook] skipping ref={ref} repo={repo}")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"skipped")
                return

            print(f"[webhook] deploy triggered by push to {ref}")
            self.send_response(202)
            self.end_headers()
            self.wfile.write(b"deploying")

            threading.Thread(target=run_deploy, daemon=True).start()
            return

        if event == "workflow_run":
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                return

            action = data.get("action", "")
            conclusion = data.get("workflow_run", {}).get("conclusion", "")
            workflow = data.get("workflow_run", {}).get("name", "")
            branch = data.get("workflow_run", {}).get("head_branch", "")

            if action == "completed" and conclusion == "success" and workflow == "CI" and branch == "main":
                print(f"[webhook] deploy triggered by CI success on main")
                self.send_response(202)
                self.end_headers()
                self.wfile.write(b"deploying")
                threading.Thread(target=run_deploy, daemon=True).start()
                return

            print(f"[webhook] skipping workflow_run action={action} conclusion={conclusion} workflow={workflow}")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"skipped")
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ignored")

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        print(f"[webhook] {args[0]}")


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", LISTEN_PORT), WebhookHandler)
    print(f"[webhook] listening on :{LISTEN_PORT} for {REPO_FULL_NAME} {DEPLOY_BRANCH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
