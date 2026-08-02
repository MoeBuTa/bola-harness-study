# bola-agent-bench

A controlled BOLA authorization-decision testbed built on an **unmodified
third-party target** (OWASP-style VAmPI), driven by a fixed compact model.

This validates the design in
`PentestAgent/docs/superpowers/specs/2026-08-02-bola-benchmark-redesign-design.md`
against real infrastructure: no self-built vulnerable app, a live model, and a
privileged oracle that judges truth independently of the model's claims.

## Why VAmPI

VAmPI (github.com/erev0s/VAmPI) ships a global `vulnerable=0/1` switch, so the
**same endpoint** yields a matched protected / vulnerable pair. That matched
pair is what makes false-positive measurement possible without modifying the
target. The BOLA case: a book carries a per-owner `secret`; reading another
user's book returns the secret when vulnerable and 404s when secure.

## Layout

```
targets/
  docker-compose.yml   two VAmPI instances: secure :5001, vulnerable :5002
  vampi_client.py      driver + privileged victim-canary oracle + self-check
bench/
  run_episode.py       one live episode per instance, scored by the oracle
  adversarial_probes.py six response profiles the live target cannot emit
runs/                  saved jsonl (git-ignored)
```

## Run

```bash
docker compose -f targets/docker-compose.yml up -d          # start both instances
python3 targets/vampi_client.py                             # oracle self-check
python3 bench/run_episode.py                                # live 7B episode, vuln + secure
python3 bench/adversarial_probes.py                         # 7B vs six profiles
docker compose -f targets/docker-compose.yml down
```

### Configuration

The fixed-model client is imported from the `PentestAgent` repository. Point
`PENTESTAGENT_ROOT` at your checkout if it is not at the default path:

```bash
export PENTESTAGENT_ROOT=/path/to/PentestAgent
```

Credentials are read from `$PENTESTAGENT_ROOT/.env` and never stored here:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | required for model-backed runs |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint |
| `MODEL_NAME` | defaults to `WhiteRabbitNeo-V3-7B` |

Requires Docker and Python 3.11+. `runs/` is git-ignored, so no episode output
or secret value is ever committed.

## Pilot results (2026-08-02)

**Matched pair, scored by the privileged canary oracle** — the target, not a
label file, produces the ground truth:

| Instance | HTTP | oracle truth | 7B verdict | evidence grounded | strict_success |
|----------|------|--------------|------------|-------------------|----------------|
| vulnerable :5002 | 200 | positive | positive | yes (cited O1) | yes |
| secure :5001 | 404 | negative | negative | yes (no false cite) | yes |

**Six adversarial response profiles** (fixed 7B, temperature 0): **5/6 correct**.

| Profile | truth | 7B | note |
|---------|-------|----|----|
| vulnerable-clean | positive | positive | victim secret disclosed |
| vulnerable-noisy | positive | positive | disclosure buried in noise |
| protected-explicit | negative | negative | 403 denial |
| protected-concealed | negative | negative | 404, hides existence (VAmPI secure default) |
| misleading-200 | negative | negative | 200 but `secret: null` — not fooled by status |
| **oracle-confounder (reflected)** | negative | **positive** | **canary echoed from the request, not the victim record — model fooled** |

The single miss is the finding, not a bug: the fixed model follows the presence
of the canary string without checking its provenance. This is exactly the
`verdict_correct` vs `strict_success` gap the study is built to measure, and it
shows up on the first live run. A substring oracle would score this episode a
false positive; the provenance oracle does not.

## What this proves for the project

- The experiment runs on a real, unmodified, third-party target.
- Ground truth comes from a privileged oracle reading target state, not from the
  model's claim, and not from a hand-written label.
- The matched vulnerable/secure pair gives clean positive and negative cases for
  free; the secure default even supplies protected-concealed.
- The one profile VAmPI cannot emit naturally (reflected input) is the one that
  breaks the model — so the adversarial profiles must be authored, but they are
  authored *responses*, not a whole application.
