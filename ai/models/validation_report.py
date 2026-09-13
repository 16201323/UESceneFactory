"""v0.4 校验报告模型 — QualityGuardAgent 的输出，记录校验/修复后的场景 JSON 及校验历史。

QualityGuardAgent（三阶段管线的第 3 阶段）接收 JSONBuilderAgent 产出的 SceneJSON，
执行字段校验 + 资产路径校验，若发现错误则 LLM 修复并重试（最多 3 轮），
最终输出 ValidationReport，其中 scene 字段即为通过校验的场景 JSON。

repair_history 记录每轮校验的 errors/warnings 快照，便于追溯修复过程。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationReport(BaseModel):
    """校验报告 — QualityGuardAgent 的输出模型。

    Attributes:
        scene: 校验/修复通过后的场景 JSON（dict 格式，可直接传 build_scene.py 消费）。
        is_valid: 最终是否通过校验（True=可交付，False=仍有错误但已达修复上限）。
        errors: 最终残留的错误列表（空列表表示无错误）。
        warnings: 警告列表（不影响 is_valid，仅提示）。
        repair_rounds: 实际执行的修复轮数（0=一次通过，1~3=修复次数）。
        repair_history: 每轮校验记录，格式 [{round, errors, warnings}, ...]。
    """
    scene: dict                                              # 校验/修复后的场景 JSON
    is_valid: bool                                           # 最终是否通过校验
    errors: list[str] = Field(default_factory=list)          # 错误列表（空=无错误）
    warnings: list[str] = Field(default_factory=list)        # 警告列表（不影响 is_valid）
    repair_rounds: int = 0                                  # 修复轮数（0=一次通过）
    repair_history: list[dict] = Field(default_factory=list)  # 每轮校验记录
