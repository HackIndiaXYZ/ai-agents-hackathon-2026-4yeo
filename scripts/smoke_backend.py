from __future__ import annotations

import argparse
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Argus Awaaz QA backend golden-path smoke check.")
    parser.add_argument("--api-base-url", default="http://localhost:8000/api")
    parser.add_argument("--scenario-id", default="fintech-hinglish-refund-escalation")
    parser.add_argument("--include-adaption", action="store_true")
    args = parser.parse_args()

    api_base_url = args.api_base_url.rstrip("/")
    with httpx.Client(timeout=30) as client:
        health = _request(client, "GET", f"{api_base_url}/health")
        print(f"health: {health['status']}")

        scenario_run = _request(client, "POST", f"{api_base_url}/demo/scenarios/{args.scenario_id}/run")
        session_id = scenario_run["session"]["id"]
        result = scenario_run["result"]
        print(f"scenario: {args.scenario_id}")
        print(f"qa_result: label={result['violation_label']} escalation={result['escalation_required']}")
        if not scenario_run["expected_match"]:
            raise RuntimeError("Scenario result did not match expected QA label or escalation flag")

        correction = _request(
            client,
            "POST",
            f"{api_base_url}/qa/sessions/{session_id}/corrections",
            json={
                "corrected_score": result["final_score"],
                "corrected_violation_label": result["violation_label"],
                "corrected_escalation_required": result["escalation_required"],
                "corrected_coaching_note": result["coaching_note"],
                "reviewer_note": "Smoke check accepted the backend QA result.",
            },
        )
        print(f"correction: {correction['id']} dataset_row={correction['dataset_row_id']}")

        export = _request(client, "POST", f"{api_base_url}/datasets/export", json={"format": "all"})
        print(f"export: rows={export['row_count']} formats={','.join(export['formats'])}")

        if args.include_adaption:
            jsonl_artifact = next(item for item in export["artifacts"] if item["artifact_type"] == "jsonl")
            adaption_run = _request(
                client,
                "POST",
                f"{api_base_url}/adaption/runs",
                json={"artifact_id": jsonl_artifact["id"], "dataset_name": "argus-awaaz-smoke"},
            )
            print(f"adaption: status={adaption_run['status']} dataset={adaption_run['dataset_id']}")

        analytics = _request(client, "GET", f"{api_base_url}/analytics/summary")
        print(
            "analytics: "
            f"sessions={analytics['total_sessions']} "
            f"corrections={analytics['total_corrections']} "
            f"rows={analytics['total_dataset_rows']} "
            f"exports={analytics['total_exports']}"
        )

    return 0


def _request(client: httpx.Client, method: str, url: str, *, json: dict | None = None) -> dict:
    response = client.request(method, url, json=json)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return payload


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"smoke check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
