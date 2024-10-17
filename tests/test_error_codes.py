import json
import os
import subprocess
from pathlib import Path

import pytest

from app.api.i18n import ErrorCode


def _test_error_codes(frontend_base_path: Path) -> None:
    backend = {e.removeprefix("backend.error.") for e in ErrorCode}

    frontend_path = frontend_base_path / "src/locales"
    for locale_json in frontend_path.glob("*.json"):
        with locale_json.open() as f:
            frontend = set(json.load(f)["backend"]["error"])

        assert backend <= frontend, f"Backend error code mismatch in locale file {locale_json}"


@pytest.mark.skipif(
    os.getenv("CI_JOB_TOKEN") is not None,
    reason="Only run locally, requires uptodate tsai-frontend repo in right place",
)
def test_error_codes() -> None:
    _test_error_codes(Path(os.getenv("FRONTEND_PATH", "../tsai-frontend")))


@pytest.mark.skipif(os.getenv("CI_JOB_TOKEN") is None, reason="Only run in CI pipeline")
def test_error_codes_ci() -> None:
    # Clone the frontend repo
    frontend_repo_url = f"https://gitlab-ci-token:{os.getenv('CI_JOB_TOKEN')}@gitlab.com/skillbyte/products/textsenseai/tsai-frontend.git"
    frontend_clone_path = Path() / "tsai-frontend"
    subprocess.run(["git", "clone", frontend_repo_url, str(frontend_clone_path)], check=True)  # noqa: S603, S607

    _test_error_codes(frontend_clone_path)
