# ORDER-005: Approved Sandbox Packages

All packages pre-installed in the sandbox are pinned to exact versions in `Dockerfile`.
The CI pipeline runs `pip-audit` on both the API and sandbox packages weekly and on every push.

## Audit Policy

- `pip-audit --strict` runs in CI as **blocking** (no `continue-on-error`).
- Weekly scheduled audit (Monday 9am UTC) catches new CVEs between pushes.
- Any critical/high CVE with no available fix triggers package removal.
- Packages must be re-approved after major version upgrades.

## Package Categories

| Category | Packages | Count |
|----------|----------|-------|
| HTTP & Networking | requests, httpx, urllib3, aiohttp, websockets | 5 |
| Data Formats | pyyaml, orjson, tomli, tomli-w, xmltodict, msgpack | 6 |
| Data Validation | pydantic, attrs, jsonschema | 3 |
| Text & Content | beautifulsoup4, lxml, markdownify, markdown, html2text, chardet, python-slugify, jinja2, regex | 9 |
| Date & Time | python-dateutil, pytz, arrow | 3 |
| Data Science | numpy, pandas, scipy, scikit-learn, sympy, statsmodels | 6 |
| Visualization | matplotlib, pillow | 2 |
| AI & LLM | openai, anthropic, tiktoken, cohere | 4 |
| Cloud & SaaS | boto3, stripe, sendgrid, twilio, google-cloud-storage | 5 |
| File Formats | tabulate, feedparser, openpyxl, xlsxwriter, python-docx, pypdf | 6 |
| Crypto & Security | cryptography, pyjwt, bcrypt | 3 |
| Database Clients | psycopg2-binary, pymongo, redis | 3 |
| Utilities | humanize, tqdm, rich, typing-extensions | 4 |
| **Total** | | **59** |

## Version Pinning

All versions are pinned in `Dockerfile` stage 1 (`sandbox-builder`).
To update a package:

1. Update pin in Dockerfile
2. Run `pip-audit` locally on updated requirements
3. Run sandbox smoketest to verify compatibility
4. Commit and push (CI will validate both audit and smoketest)

## Removal Criteria

Remove a package immediately if:
- Critical CVE with no patch available within 48 hours
- High CVE with no patch available within 7 days
- Package is abandoned (no release in 2+ years)
- Package introduces a supply chain risk (dependency on untrusted packages)
