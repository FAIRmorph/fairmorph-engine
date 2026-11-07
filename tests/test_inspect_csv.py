"""CLI integration tests for inspecting real CSV sources."""

import hashlib
import json
import subprocess
import sys


def invoke_csv(*args):
    return subprocess.run(
        [sys.executable, "-m", "fairmorph_engine.cli", "inspect-csv", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_inspect_csv_reports_columns_count_hash_and_output(tmp_path):
    source = tmp_path / "observations.csv"
    source.write_text(
        "scientificName,eventDate\nAcropora,2026-01-01\nPorites,2026-01-02\n",
        encoding="utf-8",
    )
    output = tmp_path / "summary.json"
    completed = invoke_csv(source, "--output", output)
    assert completed.returncode == 0, completed.stderr
    events = [json.loads(line) for line in completed.stdout.splitlines()]
    assert events[0]["event"] == "progress"
    result = events[-1]
    assert result["event"] == "result"
    assert result["status"] == "success"
    assert result["data"]["columns"] == ["scientificName", "eventDate"]
    assert result["data"]["processed_records"] == 2
    assert result["data"]["dataset_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["data"]["output_file"] == str(output.resolve())
    assert json.loads(output.read_text(encoding="utf-8"))["processed_records"] == 2


def test_inspect_csv_handles_utf8_bom_and_empty_body(tmp_path):
    source = tmp_path / "empty.csv"
    source.write_bytes(bytes([0xEF, 0xBB, 0xBF]) + b"scientificName,eventDate\\n")
    completed = invoke_csv(source)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.splitlines()[-1])
    assert result["data"]["columns"] == ["scientificName", "eventDate"]
    assert result["data"]["processed_records"] == 0


def test_inspect_csv_rejects_malformed_rows(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("a,b\n1\n", encoding="utf-8")
    completed = invoke_csv(source)
    assert completed.returncode != 0
    result = json.loads(completed.stdout.splitlines()[-1])
    assert result["event"] == "result"
    assert result["status"] == "error"
    assert "fields" in result["message"]


def test_inspect_csv_rejects_duplicate_columns(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("a,a\n1,2\n", encoding="utf-8")
    completed = invoke_csv(source)
    assert completed.returncode != 0
    assert json.loads(completed.stdout.splitlines()[-1])["status"] == "error"


def test_inspect_csv_does_not_overwrite_source(tmp_path):
    source = tmp_path / "source.csv"
    data = b"a,b\n1,2\n"
    source.write_bytes(data)
    completed = invoke_csv(source, "--output", source)
    assert completed.returncode != 0
    assert source.read_bytes() == data
