"""Tests for AVOI branding files."""

import os
import sys
import tempfile

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def test_banner_prints():
    """Banner should print without errors."""
    from avoi.branding.banner import print_banner
    import io
    from contextlib import redirect_stdout

    f = io.StringIO()
    with redirect_stdout(f):
        print_banner("1.0.0")
    output = f.getvalue()
    assert "Autonomous AI Agent Platform" in output, f"Banner should contain tagline, got: {output}"
    assert "1.0.0" in output, f"Banner should contain version, got: {output}"


def test_soul_md_exists():
    """SOUL.md should exist in branding directory."""
    soul_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "branding", "SOUL.md"
    )
    assert os.path.exists(soul_path), f"SOUL.md not found at {soul_path}"
    with open(soul_path) as f:
        content = f.read()
    assert "AVOI" in content, "SOUL.md should mention AVOI"


def test_rebrand_works_on_sample():
    """Rebrand script should replace strings in a sample file."""
    from avoi.scripts.rebrand import rebrand_file

    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("# Welcome to AVOI Agent\nBuilt by AVOI AI\n")
        tmp_path = f.name

    try:
        count = rebrand_file(tmp_path)
        with open(tmp_path) as f:
            content = f.read()
        assert "AVOI Agent" in content, f"Should contain AVOI Agent, got: {content}"
        assert "AVOI AI" in content, f"Should contain AVOI AI, got: {content}"
        assert count > 0, "Should have made at least one replacement"
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    test_banner_prints()
    print("✓ test_banner_prints")

    test_soul_md_exists()
    print("✓ test_soul_md_exists")

    test_rebrand_works_on_sample()
    print("✓ test_rebrand_works_on_sample")

    print("\nAll branding tests passed!")
