import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_experiment(
    data_path,
    config_path,
    command,
    output_path,
):
    data_path = Path(data_path).resolve()
    config_path = Path(config_path).resolve()
    output_path = Path(output_path)

    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )

    payload = {
        "schema_version": 1,
        "experiment_time": datetime.now(timezone.utc).isoformat(),
        "data_file": str(data_path),
        "data_sha256": sha256(data_path),
        "config_file": str(config_path),
        "config_sha256": sha256(config_path),
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    return payload
