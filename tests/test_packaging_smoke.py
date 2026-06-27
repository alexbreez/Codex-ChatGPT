from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.getenv("RUN_PACKAGING_SMOKE") != "1", reason="Set RUN_PACKAGING_SMOKE=1 to create a clean venv and run editable-install smoke test")
def test_editable_install_console_script_smoke(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    bin_dir = "Scripts" if os.name == "nt" else "bin"
    python = venv / bin_dir / "python"
    metrika_leads = venv / bin_dir / ("metrika-leads.exe" if os.name == "nt" else "metrika-leads")
    subprocess.run([str(python), "-m", "pip", "install", "-e", "."], check=True)
    subprocess.run([str(metrika_leads), "--help"], check=True)
    subprocess.run([str(python), "-m", "metrika_lead_pipeline.cli", "--help"], check=True)
