"""Smoke test for the CLI protocol used by the Workbench."""

import json
import subprocess
import sys


def test_poc_cli_emits_ndjson_result():
    completed = subprocess.run(
        [sys.executable, "-m", "fairmorph_engine.cli", "poc", "--records", "2"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    events = [json.loads(line) for line in completed.stdout.splitlines()]
    assert any(event.get("event") == "progress" for event in events)
    assert any(
        event.get("event") == "result"
        and event.get("status") == "success"
        and event.get("data", {}).get("processed_records") == 2
        for event in events
    )
