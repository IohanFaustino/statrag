from pathlib import Path

SKILLS = Path("src/services/chat/agents/extension_skills")


def test_three_skills_with_frontmatter():
    for name in ("curate-structure", "gap-augment", "judge-coverage"):
        p = SKILLS / name / "SKILL.md"
        assert p.exists(), f"missing {p}"
        text = p.read_text()
        assert text.startswith("---")
        assert "name:" in text and "description:" in text
