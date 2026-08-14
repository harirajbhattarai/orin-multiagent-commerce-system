from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    ROOT / "tools" / "compliance_check.py",
    ROOT / "tools" / "shopify_publisher" / "compliance_check.py",
)


@pytest.mark.parametrize("script", SCRIPTS)
def test_safe_negative_public_road_guidance_passes_with_warning(
    script: Path,
    tmp_path: Path,
) -> None:
    article = tmp_path / "article.html"
    article.write_text(
        """
        <div class="hs-faq-item">
          <div class="hs-faq-q">Where can I ride a hoverboard in the UK?</div>
          <div class="hs-faq-a">
            <p>
              Hoverboards are intended for use on private land with the
              owner's permission. They are not approved for use on public
              roads or pavements in the UK.
            </p>
          </div>
        </div>
        """,
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(script), str(article)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "STATUS: PASS WITH WARNINGS" in result.stdout
    assert "STATUS: FAIL" not in result.stdout


@pytest.mark.parametrize("script", SCRIPTS)
def test_public_road_permission_claim_remains_blocked(
    script: Path,
    tmp_path: Path,
) -> None:
    article = tmp_path / "article.html"
    article.write_text(
        "<p>You can ride on public roads when traffic is quiet.</p>",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(script), str(article)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "STATUS: FAIL" in result.stdout


@pytest.mark.parametrize("script", SCRIPTS)
def test_safe_negative_sentence_is_not_tainted_by_later_permission_language(
    script: Path,
    tmp_path: Path,
) -> None:
    article = tmp_path / "article.html"
    article.write_text(
        """
        <p>
          Use the hoverboard on suitable private land with the landowner's
          permission, and not on UK public roads or pavements. If you are
          unsure where you can ride, check the current UK rules.
        </p>
        """,
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(script), str(article)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "STATUS: PASS WITH WARNINGS" in result.stdout
    assert "STATUS: FAIL" not in result.stdout


def test_hcs_faq_safe_negative_context_is_recognized(tmp_path: Path) -> None:
    article = tmp_path / "hcs-article.html"
    article.write_text(
        """
        <section class="hcs-faq">
          <div class="hcs-faq-item">
            <h3>Where can an electric scooter be used?</h3>
            <p>Use it only on suitable private land with the landowner's permission,
            not on public roads or pavements.</p>
          </div>
        </section>
        """,
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPTS[1]), str(article)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "STATUS: PASS WITH WARNINGS" in result.stdout
