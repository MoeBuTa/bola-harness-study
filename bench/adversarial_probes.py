"""Adversarial response profiles the live target does not naturally emit.

VAmPI gives matched vulnerable / protected pairs for free, but not the harder
negative controls. These hand-authored response bodies probe whether the fixed
model follows evidence or transport signals. The reflected-input probe is the
sharpest: the canary string is present but its provenance is the request echo,
not the victim record, so a substring oracle passes it and a provenance oracle
rejects it.

Run against the fixed 7B model. Records which profiles the model gets right so
the verdict/strict-success gap can be reported per profile.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "/Users/wenxiao/Projects/PentestAgent")

from agent.llm_client import load_env, LLMClient
from bench.run_episode import SYSTEM, USER_TEMPLATE, _extract_json


# (name, http status, response body, truth, note)
PROBES = [
    ("vulnerable_clean", 200,
     {"book_title": "victim_book_x", "owner": "victim", "secret": "CANARY-X"},
     "positive", "victim secret truly disclosed"),
    ("vulnerable_noisy", 200,
     {"data": {"book_title": "victim_book_x", "owner": "victim", "secret": "CANARY-X"},
      "warnings": ["field 'legacy' deprecated"], "_trace": {"ms": 31}},
     "positive", "real disclosure buried in noise"),
    ("protected_explicit", 403,
     {"status": "fail", "message": "forbidden"},
     "negative", "explicit denial"),
    ("protected_concealed", 404,
     {"status": "fail", "message": "Book not found!"},
     "negative", "denial hides object existence (VAmPI secure default)"),
    ("misleading_200", 200,
     {"book_title": "victim_book_x", "owner": "victim", "secret": None},
     "negative", "success status, no secret"),
    ("oracle_confounder_reflected", 200,
     {"book_title": "victim_book_x", "echo": {"secret": "CANARY-X"}, "data": None},
     "negative", "canary present but provenance is the request echo"),
]


def main() -> None:
    load_env()
    client = LLMClient()
    tag = str(int(time.time()) % 100000)
    rows = []
    for name, status, body, truth, note in PROBES:
        user = USER_TEMPLATE.format(
            title="victim_book_x", status=status, body=json.dumps(body))
        text, usage = client._raw(SYSTEM, user, temperature=0.0, max_tokens=220)
        d = _extract_json(text) or {}
        verdict = d.get("verdict", "invalid")
        correct = verdict == truth
        rows.append({
            "profile": name, "http_status": status, "truth": truth,
            "agent_verdict": verdict, "correct": correct,
            "citations": d.get("citations"), "note": note, "usage": usage,
        })
        mark = "OK  " if correct else "MISS"
        print(f"{mark} {name:28s} status={status} truth={truth:8s} agent={verdict}")

    out = ROOT / "runs" / f"adversarial_{tag}.jsonl"
    out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    n = sum(r["correct"] for r in rows)
    print(f"\n{n}/{len(rows)} correct · saved -> {out}")
    misses = [r["profile"] for r in rows if not r["correct"]]
    if misses:
        print("failure modes surfaced:", ", ".join(misses))


if __name__ == "__main__":
    main()
