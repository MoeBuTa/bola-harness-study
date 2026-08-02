# bola-harness-study

Infrastructure for a harness comparison study: how much inference-time
structure a fixed compact uncensored LLM needs before its BOLA findings rest on
the evidence it actually collected.

The setting runs on an **unmodified third-party target** (VAmPI), with a
privileged oracle that decides truth by reading stored target state. This
repository holds the evaluation setting and a working pilot. The harness
variants under comparison are the student deliverable.

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
study/
  run_episode.py       one live episode per instance, scored by the oracle
  adversarial_probes.py six response profiles the live target cannot emit
runs/                  saved jsonl (git-ignored)
```

## Run

```bash
docker compose -f targets/docker-compose.yml up -d          # start both instances
python3 targets/vampi_client.py                             # oracle self-check
python3 study/run_episode.py                                # live 7B episode, vuln + secure
python3 study/adversarial_probes.py                         # 7B vs six profiles
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

**Matched pair, scored by the privileged canary oracle.** The target itself
produces the ground truth:

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
| misleading-200 | negative | negative | 200 with `secret: null`, judged on evidence |
| **oracle-confounder (reflected)** | negative | **positive** | **canary echoed from the request, so the model was misled** |

The single miss is the finding: the fixed model follows the presence of the
canary string while its provenance stays unchecked. This is exactly the
`verdict_correct` versus `strict_success` gap the study measures, and it appears
on the first live run. A substring oracle scores this episode as a hit, while
the provenance oracle scores it correctly.

## What the pilot establishes

- The study runs against a real, unmodified, third-party target.
- Ground truth comes from a privileged oracle reading stored target state,
  independently of anything the model asserts.
- The matched vulnerable and secure pair supplies clean positive and negative
  cases directly, and the secure default also supplies protected-concealed.
- Reflected input, the profile that misleads the model, is expressed as an
  authored *response body*, which keeps the setting small.

## Where the study design lives

The research design, metrics, and student work plan are in the project guide at
`PentestAgent/demo/student-project.html`.
