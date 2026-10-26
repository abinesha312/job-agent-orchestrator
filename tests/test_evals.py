from job_agent.checks import DATASET_SIZE, evaluate, faithfulness
from job_agent.cli import main
from job_agent.evalrun import load_pairs, run_dataset


def test_golden_set_passes_offline():
    pairs = load_pairs()
    assert len(pairs) == DATASET_SIZE == 20
    rows = run_dataset()
    failed = [f"{row['id']}: {row['failures']}" for row in rows if not row["passed"]]
    assert not failed, failed


def test_cli_exits_zero():
    assert main([]) == 0


def test_ungrounded_resume_is_blocked():
    original = (
        "Jordan Q. Sample\nAustin | jordan.sample@example.com\n\n"
        "SUMMARY\nSoftware engineer who uses Python.\n\n"
        "EXPERIENCE\nSoftware Engineer, Fictional Labs LLC, 2021 - Present\n"
        "• Built Python services.\n\n"
        "SKILLS\nPython, Docker\n"
    )
    invented = original.replace("Python services", "Rust services at Google") + "\nSKILLS\nRust, COBOL\n"
    report = evaluate(
        original=original,
        tailored=invented,
        jd="Must have: Python, Docker.\n",
        retrieved_chunks=["Python services", "Python, Docker"],
        must_have=["Python", "Docker"],
        version_count=1,
    )
    assert report.blocked
    assert "faithfulness" in report.failures
    score, _ = faithfulness(original, invented)
    assert score == 0.0
