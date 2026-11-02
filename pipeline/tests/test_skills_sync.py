from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]


def test_skills_module_is_identical_in_backend_and_pipeline():
    """extract/skills.py is a copy of backend/services/skills.py — edit one, copy it to the other."""
    backend = PIPELINE.parent / "backend" / "services" / "skills.py"
    assert (PIPELINE / "extract" / "skills.py").read_bytes() == backend.read_bytes()
