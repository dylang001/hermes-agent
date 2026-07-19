"""CI gate for the offline memory-reliability benchmark harness."""

from pathlib import Path
import importlib.util


def _load_harness():
    path = Path(__file__).resolve().parents[2] / "audit" / "_memory_reliability_benchmark.py"
    spec = importlib.util.spec_from_file_location("memory_reliability_benchmark", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_memory_reliability_offline_suite_passes():
    mod = _load_harness()
    report = mod.run_all()
    assert report["passed"] is True
    assert report["suite_score"] >= 0.95
    for scenario in report["scenarios"]:
        assert scenario["passed"], scenario
