"""Shadow pin-cap + short-context bypass tests (Context Engineering V2)."""

from agent.context_engineering_v2 import (
    EvidenceClass,
    PinSet,
    PinnedEvidence,
    shadow_apply_pin_caps,
    should_bypass_v2_layers,
)


def _pin(i: int, tokens: int = 1000, *, verify: str = "", name: str = "terminal") -> PinnedEvidence:
    return PinnedEvidence(
        tool_call_id=f"call_{i}",
        tool_name=name,
        evidence_class=(
            EvidenceClass.VERIFY.value if verify else EvidenceClass.MUTATING.value
        ),
        mutation_epoch=1,
        message_index=i,
        chars=tokens * 4,
        tokens_est=tokens,
        path=f"/tmp/f{i}.py" if name == "write_file" else "",
        command=f"cmd {i}",
        verify_outcome=verify,
        pinned_at_api_call=i,
    )


def test_pin_caps_shadow_compacts_without_dropping_verify():
    pins = PinSet(open_epoch=3, pins=[_pin(i, 2000) for i in range(25)])
    pins.pins.append(_pin(99, 500, verify="success", name="terminal"))

    out, checkpoint, audit = shadow_apply_pin_caps(
        pins,
        api_call_index=100,
        caps={
            "shadow_enabled": True,
            "apply_to_dark_store": True,
            "max_pins_per_epoch": 10,
            "max_tokens_per_epoch": 15_000,
            "max_age_api_calls": 50,
            "dedupe_identical_tool_results": True,
            "fail_open_keep_verify": True,
        },
    )

    assert audit["triggered"] is True
    assert audit["applied"] is True
    assert checkpoint is not None
    assert checkpoint.compacted_pin_count >= 1
    assert any(p.verify_outcome == "success" for p in out.pins)
    assert len(out.pins) <= 10
    assert out.pinned_tokens <= 15_000


def test_pin_caps_shadow_only_does_not_mutate_when_apply_false():
    pins = PinSet(open_epoch=1, pins=[_pin(i, 3000) for i in range(12)])
    before = len(pins.pins)
    out, checkpoint, audit = shadow_apply_pin_caps(
        pins,
        api_call_index=20,
        caps={
            "apply_to_dark_store": False,
            "max_pins_per_epoch": 5,
            "max_tokens_per_epoch": 8_000,
        },
    )
    assert audit["triggered"] is True
    assert checkpoint is not None
    assert audit["applied"] is False
    assert len(out.pins) == before


def test_short_context_bypass_threshold(monkeypatch):
    monkeypatch.setattr(
        "agent.context_engineering_v2._load_short_context_bypass_config",
        lambda: {
            "enabled": True,
            "apply": False,
            "legacy_token_threshold": 40_000,
            "require_positive_layered_saving": True,
        },
    )
    bypass, reason = should_bypass_v2_layers(legacy_tokens_est=12_000)
    assert bypass is True
    assert "legacy_tokens" in reason

    bypass2, reason2 = should_bypass_v2_layers(
        legacy_tokens_est=80_000,
        layered_tokens_est=90_000,
        step="inspect",
    )
    assert bypass2 is True
    assert "layered_saving" in reason2

    bypass_mutate, reason_mutate = should_bypass_v2_layers(
        legacy_tokens_est=80_000,
        layered_tokens_est=90_000,
        step="mutate",
    )
    assert bypass_mutate is False
    assert reason_mutate == ""

    bypass3, reason3 = should_bypass_v2_layers(
        legacy_tokens_est=80_000, layered_tokens_est=50_000, step="inspect"
    )
    assert bypass3 is False
    assert reason3 == ""
