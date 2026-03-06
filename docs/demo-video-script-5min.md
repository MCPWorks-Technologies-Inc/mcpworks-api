# MCPWorks Demo Video Script — Narrated Explainer + Live Demo

**Target:** 5–6 minutes | Landing page / social / YouTube
**Tone:** Confident, concise, technical but accessible
**Setup:** VS Code (dark theme, 16px font), Claude Code panel open, browser for console

---

## PRE-RECORDING CHECKLIST

- [ ] Production API healthy: `https://api.mcpworks.io/v1/health`
- [ ] Demo account ready with namespace `demo` (or create fresh on camera)
- [ ] `.mcp.json` prepared but NOT yet in project (we add it live)
- [ ] Claude Code connected and working
- [ ] Browser tab open to `https://api.mcpworks.io/console` (logged out)
- [ ] Second browser tab: `https://www.mcpworks.io` (pricing page)
- [ ] Terminal clean, no sensitive info visible
- [ ] Screen recording at 1920x1080, 30fps
- [ ] Mic check done, room quiet

---

## SCENE 1 — THE HOOK (0:00 – 0:40)

### SCREEN
Empty VS Code editor. Cursor blinking in Claude Code panel.

### READING
> Every AI coding assistant — Claude, Copilot, Cursor — they can write code.
> But they can't *run* it somewhere useful.
>
> Want your AI to call an API? Parse a CSV? Send a Slack message?
> You're looking at a Docker setup, a deployment pipeline, environment variables,
> and an afternoon you'll never get back.
>
> MCPWorks fixes this. One config file. Ten seconds. Your AI assistant gets
> a secure code sandbox it can create functions in, execute them, and iterate —
> all through conversation.
>
> Let me show you.

### ACTIONS
- Camera stays on the empty editor during narration
- On "Let me show you" — hands move to keyboard

---

## SCENE 2 — SETUP: ONE FILE (0:40 – 1:20)

### SCREEN
VS Code file explorer → create `.mcp.json` in project root.

### READING
> Step one: add MCPWorks to your project.
> I create a `.mcp.json` file — this is the standard MCP configuration
> that tells your AI assistant where its tools live.
>
> Two servers. One for *creating* functions — that's the management endpoint.
> One for *running* them — that's the execution endpoint.
> Each gets a namespace — think of it as your workspace.
>
> The API key authenticates everything.
> That's it. That's the entire setup.

### ACTIONS
Type or paste into `.mcp.json`:
```json
{
  "mcpServers": {
    "mcpworks-create": {
      "type": "http",
      "url": "https://demo.create.mcpworks.io/mcp",
      "headers": {
        "Authorization": "Bearer mw_demo_xxxxxxxx"
      }
    },
    "mcpworks-run": {
      "type": "http",
      "url": "https://demo.run.mcpworks.io/mcp",
      "headers": {
        "Authorization": "Bearer mw_demo_xxxxxxxx"
      }
    }
  }
}
```
- Save the file
- Pause briefly to let the viewer read the structure

---

## SCENE 3 — CREATE A FUNCTION (1:20 – 2:30)

### SCREEN
Claude Code panel, active conversation.

### READING
> Now I talk to Claude normally.
> I'll ask it to build me a word count function.

*(pause while typing)*

> Claude sees the MCPWorks tools — `make_service`, `make_function`,
> `list_packages` — thirteen management tools in total.
>
> Watch what happens. It creates a service called "utils",
> then writes a Python function and deploys it — all through the MCP protocol.
>
> No Dockerfile. No CI pipeline. No deploy command.
> Claude wrote it, Claude deployed it, and it's live.

### ACTIONS
Type into Claude Code:
```
Create a function called "word-count" in my utils service.
It should take text and return word count, character count,
and average word length.
```

**Show Claude's response** — it will call:
1. `make_service` → creates `utils`
2. `make_function` → creates `word-count` with generated Python code

Let the tool calls complete naturally. Don't rush — let the viewer see each MCP tool call appear and resolve.

---

## SCENE 4 — EXECUTE IT (2:30 – 3:20)

### READING
> Now let's run it.

*(pause while typing)*

> I just asked Claude to use the function.
> It calls `execute` on the run endpoint — the code runs in a secure
> nsjail sandbox with memory limits, process limits, and a strict seccomp policy.
>
> Results come back inline. Word count: 8. Character count: 57.
> Average word length: 6.1. Executed in about a hundred milliseconds.
>
> This is the core loop: describe, create, run, iterate.
> All inside your conversation. No context switching.

### ACTIONS
Type into Claude Code:
```
Run word-count with the text "MCPWorks makes serverless functions easy for AI assistants"
```

**Show the result:**
```json
{
  "word_count": 8,
  "char_count": 57,
  "avg_word_length": 6.1
}
```

Highlight or circle the execution time if visible in the response.

---

## SCENE 5 — SOMETHING REAL: CSV ANALYSIS (3:20 – 4:20)

### READING
> That was simple. Let's do something real.
>
> Sixty-plus Python packages are pre-installed in the sandbox —
> pandas, numpy, scikit-learn, httpx, even the OpenAI and Anthropic SDKs.
>
> I'll ask Claude to build a CSV analyzer using pandas.

*(pause while Claude creates the function)*

> Now I'll feed it some data.

*(pause for execution)*

> Row count, column types, summary statistics, missing values —
> all computed in the sandbox and returned as structured JSON.
>
> This took one conversation turn. No Jupyter notebook.
> No local Python environment. No "pip install pandas."

### ACTIONS
Type into Claude Code:
```
Create a function called "analyze-csv" in utils that takes CSV text,
parses it with pandas, and returns row count, column names with types,
and summary statistics for numeric columns.
```

Wait for `make_function` to complete.

Then type:
```
Run analyze-csv with this CSV:
name,age,salary
Alice,30,75000
Bob,25,62000
Carol,35,88000
David,28,71000
```

Show the structured JSON result with stats.

---

## SCENE 6 — ENV PASSTHROUGH: SECRETS STAY LOCAL (4:20 – 5:00)

### READING
> What about API keys? If your function calls OpenAI or Stripe,
> it needs credentials.
>
> MCPWorks never stores your secrets. Instead, you pass them
> in a header — base64-encoded, injected into the sandbox
> at execution time, wiped immediately after.
>
> Your keys live in your local environment. They exist on the server
> only for the duration of the function call. Nothing persists.
>
> Functions declare which env vars they need.
> The `_env_status` tool shows you what's present and what's missing
> before you run anything.

### ACTIONS
Show the `.mcp.json` with the `X-MCPWorks-Env` header added:
```json
"headers": {
  "Authorization": "Bearer mw_demo_xxxxxxxx",
  "X-MCPWorks-Env": "base64:eyJPUEVOQUlfQVBJX0tFWSI6InNrLXRlc3QifQ=="
}
```

Optionally show `_env_status` tool output in Claude Code:
```
OPENAI_API_KEY: present
```

---

## SCENE 7 — THE CONSOLE (5:00 – 5:40)

### SCREEN
Switch to browser → `https://api.mcpworks.io/console`

### READING
> Everything you build is also visible in the web console.
>
> Here's the dashboard — execution count, billing period,
> your current tier.
>
> API keys — create scoped keys, revoke them, copy them.
>
> Namespaces, services, functions — all browsable.
> And this button generates your `.mcp.json` config
> automatically. One click, paste it into your project, done.
>
> The console is for humans. The MCP endpoint is for AI.
> Same platform, two interfaces.

### ACTIONS
1. Log in (or show already logged-in state)
2. Point to the usage stats bar (executions used / limit)
3. Show the API keys section — click "Create API Key"
4. Navigate to the namespace → service → function list
5. Click the "Copy MCP Config" button
6. Hover briefly on each section, don't rush

---

## SCENE 8 — CLOSE: PRICING + CTA (5:40 – 6:10)

### SCREEN
Browser → `https://www.mcpworks.io/pricing` or overlay graphic.

### READING
> MCPWorks is free to start. A hundred executions a month,
> no credit card.
>
> Builder tier is twenty-nine dollars — twenty-five hundred executions.
> Pro is one-forty-nine for twenty-five thousand.
> And enterprise starts at four-ninety-nine with dedicated support.
>
> One config file. Sixty packages. Secure sandbox execution.
> Functions your AI assistant can create and run in conversation.
>
> Go to mcpworks.io, sign up, and give your AI tools it can actually use.

### ACTIONS
- Show pricing table
- End card: **mcpworks.io** logo centered, tagline below:
  **"Code Sandbox for AI Assistants"**
- Subtitle: `1,000 free executions/month — no credit card`

---

## POST-PRODUCTION NOTES

### Pacing
- Scenes 1-2 (setup): deliberate, let it breathe — viewers are orienting
- Scenes 3-5 (live demo): slightly faster energy — this is the "wow" section
- Scenes 6-7 (features): informational, steady pace
- Scene 8 (close): slow down, confident, direct

### Text Overlays
Add lower-third labels during the live demo:
- `make_service → creates "utils"` (Scene 3)
- `make_function → deploys "word-count" v1` (Scene 3)
- `execute → nsjail sandbox, ~100ms` (Scene 4)
- `60+ Python packages pre-installed` (Scene 5)
- `Secrets: injected at runtime, never stored` (Scene 6)

### Cuts to Make
- Trim Claude's "thinking" pauses longer than 3 seconds
- Cut typing corrections (re-record clean takes if needed)
- Speed up any loading spinners at 2x

### Music
- Lo-fi ambient or light electronic — low volume, no lyrics
- Fade in during Scene 1, fade out during Scene 8

### Export
- **YouTube/Landing page:** MP4, 1080p, 30fps, H.264
- **Social clips:** Cut Scenes 3-4 as a standalone 60s clip (the "create + execute" loop)
- **README GIF:** Scene 3-4 only, 720p, 15fps, under 10MB
