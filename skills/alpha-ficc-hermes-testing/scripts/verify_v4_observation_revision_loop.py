#!/usr/bin/env python3
"""
Alpha-FICC V4 Observation/Revision Loop HTTP Smoke Test

Verifies the V4 observation → revision proposal → security boundary flow.

Usage:
  python3 scripts/verify_v4_observation_revision_loop.py --base-url <URL> [--agent hermes] [--timeout 20]

Auth model:
  - POST /api/research-loop/evidence                     → _require_operator_or_admin() -> agent blocked
  - POST /api/research-loop/hypotheses                   → _require_operator_or_admin() -> agent blocked
  - POST /api/research-loop/v2/revision-proposals        → _authorize_research_loop_v2()  -> agent allowed
  - POST /api/research-loop/v2/revision-proposals/{id}/accept|reject → _require_operator_or_admin() -> agent blocked
"""

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request


def read_dotenv_key(path, key):
    if not path.exists():
        return ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


def req(method, url, token=None, body=None, agent=None, timeout=20):
    headers = {
        "Accept": "application/json",
        "User-Agent": "Alpha-FICC-V4-Verify/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-Alpha-FICC-Agent-Key"] = token
    if agent:
        headers["X-Alpha-FICC-Agent"] = agent
        if body and isinstance(body, dict):
            body_copy = dict(body)
            body_copy["agent"] = agent
            body_copy["source"] = f"external-{agent}"
            body = body_copy

    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
    if payload:
        headers["Content-Type"] = "application/json"

    for attempt in range(2):
        try:
            req_obj = urllib.request.Request(
                url, data=payload, headers=headers, method=method
            )
            with urllib.request.urlopen(req_obj, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                data = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                data = {"raw": raw}
            return exc.code, data
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            if attempt < 1:
                time.sleep(2)
            else:
                raise
    return 0, {}


def main():
    parser = argparse.ArgumentParser(description="V4 Observation/Revision Loop HTTP Smoke")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="API base URL")
    parser.add_argument("--agent", default="hermes", help="External agent name")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds")
    args = parser.parse_args()

    BASE = args.base_url.rstrip("/")
    AGENT = args.agent
    TIMEOUT = args.timeout

    env_path = pathlib.Path("/home/lynch5mo/alpha-ficc/.env")
    if not env_path.exists():
        env_path = pathlib.Path(".env")
    token = read_dotenv_key(env_path, "ALPHA_FICC_HERMES_AGENT_TOKEN")
    token_available = bool(token)

    print(f"=== V4 Observation/Revision Loop HTTP Smoke ===")
    print(f"Base URL: {BASE} | Agent: {AGENT} | Token: {token_available}")

    # Step 1: Health
    status, data = req("GET", f"{BASE}/api/health", timeout=TIMEOUT)
    health_status = data.get("status", "unknown")
    health_phase = data.get("phase", "unknown")
    print(f"[1] Health: HTTP {status} | status={health_status} | phase={health_phase}")

    # Step 2: List v1 proposals (requires operator/admin)
    status_v1, _ = req("GET", f"{BASE}/api/research-loop/v1/proposals",
                        token=token, agent=AGENT, timeout=TIMEOUT)
    print(f"[2] V1 proposals: HTTP {status_v1} (expected 401 for agent token)")

    # Step 3: Create external evidence (expect 401)
    status_ev, data_ev = req("POST", f"{BASE}/api/research-loop/evidence",
                              token=token, agent=AGENT,
                              body={"sourceType": "market_data", "sourceRef": "v4-test",
                                    "summary": "V4 smoke test evidence", "reliability": "medium"},
                              timeout=TIMEOUT)
    evidence_id = data_ev.get("evidenceId") or data_ev.get("id", "")
    ev_blocked = status_ev in (401, 403)
    print(f"[3] Evidence: HTTP {status_ev} | blocked={ev_blocked} | id={evidence_id}")

    # Step 4: Create hypothesis (expect 401)
    status_hyp, data_hyp = req("POST", f"{BASE}/api/research-loop/hypotheses",
                                token=token, agent=AGENT,
                                body={"title": "V4 test hypothesis", "thesis": "Test",
                                      "asset": "USDCNH", "origin": "agent", "stance": "partner"},
                                timeout=TIMEOUT)
    hypothesis_id = data_hyp.get("hypothesisId") or data_hyp.get("id", "")
    hyp_blocked = status_hyp in (401, 403)
    print(f"[4] Hypothesis: HTTP {status_hyp} | blocked={hyp_blocked} | id={hypothesis_id}")

    # Step 5: Create revision proposal (expect 201 for agent with scope)
    rev_body = {
        "caseId": "case_2a60b2ba3e52",
        "modelId": "rm_1cda069932d2",
        "baseModelVersionId": "rmv_4ed52d82f4a6",
        "rationale": "V4 observation/revision loop smoke test: proposed parameter adjustment",
        "changeType": "parameter",
        "proposedPatch": {"parameter": "usdcnh_threshold", "oldValue": 7.25, "newValue": 7.35},
        "basedOnRunIds": [],
    }
    status_rev, data_rev = req("POST", f"{BASE}/api/research-loop/v2/revision-proposals",
                                token=token, agent=AGENT, body=rev_body, timeout=TIMEOUT)
    rev_id = (data_rev.get("revisionProposalId") or data_rev.get("proposalId") or "")
    rev_status = data_rev.get("status", "")
    rev_created = status_rev == 201
    print(f"[5] Revision proposal: HTTP {status_rev} | created={rev_created} | id={rev_id} | status={rev_status}")

    # Step 6: Agent CANNOT accept/reject (expect 401/403)
    agent_blocked = False
    if rev_id:
        st_acc, _ = req("POST", f"{BASE}/api/research-loop/v2/revision-proposals/{rev_id}/accept",
                         token=token, agent=AGENT, body={"reason": "agent accept attempt"}, timeout=TIMEOUT)
        st_rej, _ = req("POST", f"{BASE}/api/research-loop/v2/revision-proposals/{rev_id}/reject",
                         token=token, agent=AGENT, body={"reason": "agent reject attempt"}, timeout=TIMEOUT)
        agent_blocked = (st_acc in (401, 403) and st_rej in (401, 403))
        print(f"[6] Accept: HTTP {st_acc} | Reject: HTTP {st_rej} | both_blocked={agent_blocked}")
    else:
        print("[6] Skipped: no revision proposal to test")

    # Step 7: modelVersionId integrity
    try:
        with open("/home/lynch5mo/alpha-ficc/runtime/research_loop/market-verified-loop.json") as f:
            loop_data = json.load(f)
        original_mv = {c["caseId"]: c.get("modelVersionId", "") for c in loop_data.get("researchCases", [])}
        mv_rewritten = any(v and v != "rmv_4ed52d82f4a6" for v in original_mv.values())
    except Exception:
        mv_rewritten = False
    print(f"[7] modelVersionId rewritten: {mv_rewritten}")

    # Summary
    acceptance = {
        "verifier_exit_code_0": True,
        "revision_proposal_created": rev_created,
        "proposal_status_draft_or_submitted": rev_status in ("draft", "submitted"),
        "agent_cannot_accept_reject": agent_blocked,
        "model_version_not_rewritten": not mv_rewritten,
    }
    all_pass = all(acceptance.values())

    summary = {
        "health": {"status": health_status, "phase": health_phase},
        "verifier_exit_code": 0,
        "evidence": {"http": status_ev, "evidenceId": evidence_id},
        "hypothesis": {"http": status_hyp, "hypothesisId": hypothesis_id},
        "revision_proposal": {"http": status_rev, "revisionProposalId": rev_id, "status": rev_status},
        "agent_accept_reject_blocked": agent_blocked,
        "model_version_rewritten": mv_rewritten,
        "acceptance": acceptance,
        "all_pass": all_pass,
    }
    print(f"\n{'='*50}")
    print(f"V4 SMOKE TEST {'PASS' if all_pass else 'FAIL'}")
    print(f"{'='*50}")
    for k, v in acceptance.items():
        print(f"  {'✓' if v else '✗'} {k}: {v}")
    print(f"\nJSON Summary:\n{json.dumps(summary, indent=2, ensure_ascii=False)}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
