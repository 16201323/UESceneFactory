"""v0.4 ValidationReport 模型单元测试。

ValidationReport 是 QualityGuardAgent 的输出，记录校验/修复后的场景 JSON 及校验历史。
"""
import pytest
from ai.models.validation_report import ValidationReport


def test_minimal():
    """ValidationReport 最小构造 — 仅 scene 和 is_valid 必填。"""
    report = ValidationReport(scene={"scene": {"name": "test"}}, is_valid=True)
    assert report.scene == {"scene": {"name": "test"}}
    assert report.is_valid is True


def test_defaults():
    """默认值 — errors/warnings/repair_history 为空列表，repair_rounds 为 0。"""
    report = ValidationReport(scene={}, is_valid=True)
    assert report.errors == []
    assert report.warnings == []
    assert report.repair_rounds == 0
    assert report.repair_history == []


def test_with_errors():
    """带错误列表的构造。"""
    report = ValidationReport(
        scene={},
        is_valid=False,
        errors=["scene 缺少 target_level", "landscape weight 超出范围"],
    )
    assert report.is_valid is False
    assert len(report.errors) == 2
    assert "target_level" in report.errors[0]


def test_with_repair_history():
    """带修复历史的构造 — 每轮校验记录。"""
    history = [
        {"round": 1, "errors": ["错误1"], "warnings": []},
        {"round": 2, "errors": [], "warnings": ["警告1"]},
    ]
    report = ValidationReport(
        scene={"scene": {"name": "fixed"}},
        is_valid=True,
        repair_rounds=2,
        repair_history=history,
    )
    assert report.repair_rounds == 2
    assert len(report.repair_history) == 2
    assert report.repair_history[0]["round"] == 1
    assert report.repair_history[1]["errors"] == []


def test_model_dump():
    """model_dump() 产出正确字典。"""
    report = ValidationReport(
        scene={"scene": {"name": "test"}},
        is_valid=True,
        errors=[],
        warnings=["轻微警告"],
        repair_rounds=1,
    )
    d = report.model_dump()
    assert d["is_valid"] is True
    assert d["errors"] == []
    assert d["warnings"] == ["轻微警告"]
    assert d["repair_rounds"] == 1
    assert d["scene"] == {"scene": {"name": "test"}}
