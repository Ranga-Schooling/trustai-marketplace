"""Integration dependency lineage between application and evaluation contracts."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
CONTRACT_PATHS = (
    ROOT / "docs/testing/ai-evaluation/capstone-live-validation.v2.json",
    ROOT / "docs/testing/ai-evaluation/capstone-live-validation.v3.json",
    ROOT / "docs/testing/ai-evaluation/capstone-gemini-text-validation.v4.json",
)


def test_application_dependencies_preserve_frozen_transport_and_visual_pins():
    requirements = (BACKEND / "requirements.txt").read_bytes()
    contract_hashes = {
        json.loads(path.read_text())["transport_binding"]["requirements_sha256"]
        for path in CONTRACT_PATHS
    }
    assert contract_hashes == {hashlib.sha256(requirements).hexdigest()}

    application_lines = (
        BACKEND / "requirements-application.txt"
    ).read_text().splitlines()
    assert application_lines == [
        "-r requirements.txt",
        "Pillow==12.3.0",
        "python-multipart==0.0.32",
    ]

    assert (BACKEND / "requirements-dev.txt").read_text().splitlines()[0] == (
        "-r requirements-application.txt"
    )
    dockerfile = (BACKEND / "Dockerfile").read_text()
    assert "COPY requirements.txt requirements-application.txt ./" in dockerfile
    assert "pip install --no-cache-dir -r requirements-application.txt" in dockerfile
