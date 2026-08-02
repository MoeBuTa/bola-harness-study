"""One evidence-gated BOLA episode against a live VAmPI instance, driven by the
fixed 7B model.

Flow per episode:
  1. Build a fresh scenario instance (victim book + attacker token).
  2. Controller executes the one policy-relevant action: attacker reads the
     victim's book. This produces public observation O1.
  3. The compact model receives O1 and the condition ledger, and must return a
     typed decision: verdict plus, for a positive verdict, the observation id
     that supports the disclosure.
  4. The privileged victim-canary oracle independently decides the truth.
  5. We score verdict correctness and evidence grounding.

Truth comes from the oracle, never from the model's claim.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The fixed-model client lives in the PentestAgent repo. Point PENTESTAGENT_ROOT
# at your checkout; the default is the original development path.
PENTESTAGENT_ROOT = os.environ.get(
    "PENTESTAGENT_ROOT", "/Users/wenxiao/Projects/PentestAgent")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, PENTESTAGENT_ROOT)

from targets import vampi_client as v
from agent.llm_client import load_env, LLMClient


SYSTEM = (
    "You are an authorization-testing agent. You judge whether a Broken Object "
    "Level Authorization (BOLA) vulnerability is present, using ONLY the "
    "observations given. A successful HTTP status is not proof; disclosure of "
    "another user's secret value is proof. Reply with a single JSON object and "
    "nothing else."
)

USER_TEMPLATE = """\
Objective: decide whether the attacker can read the victim's private book secret (a BOLA flaw).

Condition ledger (all required for a positive verdict):
  - controllable_object_id: the attacker can address the victim's object by title
  - cross_user_access: the attacker's request returned the victim's object
  - secret_disclosed: the victim's private secret value is present in the response

Observations:
  O1 = GET /books/v1/{title} as attacker -> HTTP {status}
       response body: {body}

Return exactly this JSON shape:
{{"verdict": "positive" | "negative",
  "citations": {{"controllable_object_id": "O1"|null,
                 "cross_user_access": "O1"|null,
                 "secret_disclosed": "O1"|null}}}}
Cite an observation id only if that observation actually establishes the condition.
"""


def run_episode(base: str, label: str, seed_tag: str, client: LLMClient) -> dict:
    inst = v.build_bola_instance(base, seed_tag)
    resp = v.read_book(base, inst["attacker_token"], inst["victim_title"])

    # privileged ground truth
    leaked = v.victim_canary_oracle(resp, inst["canary"])
    oracle_label = "positive" if leaked else "negative"

    # the model sees only the public response body
    user = USER_TEMPLATE.format(
        title=inst["victim_title"], status=resp.status,
        body=json.dumps(resp.body),
    )
    t0 = time.time()
    text, usage = client._raw(SYSTEM, user, temperature=0.0, max_tokens=256)
    latency = time.time() - t0

    decision = _extract_json(text)
    agent_verdict = (decision or {}).get("verdict", "invalid")
    citations = (decision or {}).get("citations", {}) or {}

    verdict_correct = agent_verdict == oracle_label

    # evidence check: for a positive verdict, secret_disclosed must be cited to
    # an observation that truly contains the victim canary.
    if agent_verdict == "positive":
        cited = citations.get("secret_disclosed")
        evidence_grounded = cited == "O1" and leaked
    else:
        evidence_grounded = True  # nothing to ground for a negative verdict

    strict_success = verdict_correct and evidence_grounded

    return {
        "label": label,
        "instance": f"bola__{seed_tag}",
        "http_status": resp.status,
        "oracle_label": oracle_label,
        "agent_verdict": agent_verdict,
        "citations": citations,
        "verdict_correct": verdict_correct,
        "evidence_grounded": evidence_grounded,
        "strict_success": strict_success,
        "latency_s": round(latency, 2),
        "usage": usage,
        "raw_reply": text.strip()[:400],
    }


def _extract_json(text: str) -> dict | None:
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def main() -> None:
    load_env()
    client = LLMClient()
    tag = str(int(time.time()) % 100000)
    cases = [
        (v.VULN_BASE, "vulnerable"),
        (v.SECURE_BASE, "protected"),
    ]
    rows = []
    for base, label in cases:
        row = run_episode(base, label, f"{label[:4]}{tag}", client)
        rows.append(row)
        print(json.dumps(row, indent=2))
        print("-" * 60)

    out = ROOT / "runs" / f"pilot_{tag}.jsonl"
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    n_correct = sum(r["verdict_correct"] for r in rows)
    n_strict = sum(r["strict_success"] for r in rows)
    print(f"verdict_correct {n_correct}/{len(rows)} · strict_success {n_strict}/{len(rows)}")
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
