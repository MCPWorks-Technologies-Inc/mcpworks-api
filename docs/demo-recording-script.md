# Demo Recording Script — 90 Second MCPWorks Demo

**ORDER-018** | February 2026

## Recording Setup

- **Tool**: OBS Studio or Screen Studio (macOS)
- **Resolution**: 1920x1080 (16:9)
- **Terminal**: VS Code with Claude Code extension, dark theme
- **Font size**: 16px minimum (readable in GIF)
- **Export**: MP4 (full quality) + GIF (compressed for README/social)

## Script (90 seconds)

### Scene 1: Add MCPWorks to .mcp.json (0:00 - 0:10)

**Action**: Open `.mcp.json` in editor, paste config block.

```
Show the file being created/edited with the two MCP server entries:
- myns-create (management)
- myns-run (execution)
```

**Narration** (text overlay or voiceover):
> "Add MCPWorks to your project in 10 seconds."

### Scene 2: Ask Claude Code to create a function (0:10 - 0:30)

**Action**: Type in Claude Code:

```
Create a function called 'word-count' in my utils service that takes text
and returns word count, character count, and average word length.
```

**Show**: Claude Code calling `make_service` then `make_function` with generated Python code.

**Narration**:
> "Describe what you want. The AI writes the code and deploys it."

### Scene 3: Function created via MCP tools (0:30 - 0:50)

**Action**: Show the MCP tool calls completing:

```
✓ make_service: utils
✓ make_function: word-count (v1, code_sandbox)
```

**Narration**:
> "Your function is live. No Docker, no CI/CD, no config files."

### Scene 4: Execute the function (0:50 - 1:10)

**Action**: Type in Claude Code:

```
Run word-count with the text "MCPWorks makes serverless functions easy for AI assistants"
```

**Show**: Claude Code calling `execute` and displaying results:

```json
{
  "word_count": 8,
  "char_count": 57,
  "avg_word_length": 6.1
}
```

**Narration**:
> "Execute instantly. Results in your conversation."

### Scene 5: Real output from sandbox (1:10 - 1:30)

**Action**: Show the execution details — sandbox isolation, execution time.

```
Executed in 0.12s | Secure nsjail sandbox | 60+ Python packages available
```

**Narration**:
> "Every execution runs in an isolated sandbox. Your code is secure."

### Scene 6: Show env passthrough (1:30 - 1:50) — Optional bonus

**Action**: Show adding `X-MCPWorks-Env` header to `.mcp.json`:

```
"X-MCPWorks-Env": "base64:eyJPUEVOQUlfQVBJX0tFWSI6InNrLXh4eCJ9"
```

**Action**: Create a function that uses an API key:

```
Create a function 'summarize' with required_env OPENAI_API_KEY
```

**Narration**:
> "Pass your API keys securely. Nothing stored — secrets live only during execution."

**End card**:
> "MCPWorks — Code Sandbox for AI Assistants"
> "mcpworks.io | 100 free executions/month"

## Post-Production

1. Trim dead time (typing pauses, loading)
2. Add text overlays for narration if no voiceover
3. Export MP4 at 1080p, 30fps
4. Export GIF at 720p, 15fps, max 10MB
5. Upload MP4 to YouTube/Loom (unlisted)
6. Add GIF to README and marketing materials

## Pre-Recording Checklist

- [ ] Production API is reachable (https://api.mcpworks.io/v1/health)
- [ ] Test account exists with namespace "myns"
- [ ] `.mcp.json` config works with Claude Code
- [ ] `make_service` + `make_function` + `execute` all work end-to-end
- [ ] Clean terminal (no prior output, no sensitive info visible)
- [ ] Screen recording software tested
