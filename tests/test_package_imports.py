from __future__ import annotations

import subprocess
import sys


def test_secret_helper_import_does_not_load_control_api_dependencies():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import orin_control.secrets; "
            "assert 'orin_control.app' not in sys.modules; "
            "assert 'fastapi' not in sys.modules",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
