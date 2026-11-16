"""Guard the shared Pages theme override against color-only links (#835)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shared_pages_head_underlines_content_and_footer_links():
    """Primer includes head-custom after its CSS on every generated page."""
    head = (ROOT / "docs/_includes/head-custom.html").read_text()
    style = re.search(r"<style>(.*?)</style>", head, re.DOTALL)
    assert style is not None
    rule = re.search(r"([^{}]+)\{([^{}]+)\}", style.group(1))
    assert rule is not None
    selectors, declarations = rule.groups()
    assert {s.strip() for s in selectors.split(",")} == {
        ".markdown-body a",
        ".footer a",
    }
    assert re.search(r"text-decoration\s*:\s*underline\s*;", declarations)
    # Do not suppress the browser/theme's visible keyboard-focus treatment.
    assert "outline" not in declarations
    assert "!important" not in declarations
