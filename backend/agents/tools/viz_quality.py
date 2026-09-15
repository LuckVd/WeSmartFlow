"""Validated design and review contracts for generated visualizations."""

import json
import math
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from .viz_registry import list_patterns


class VizQualityError(ValueError):
    """The candidate must not be published."""


class _Model(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class SliderRange(_Model):
    min: float
    max: float
    step: float
    default: float

    @model_validator(mode="after")
    def ordered(self):
        if not all(
            math.isfinite(x) for x in (self.min, self.max, self.step, self.default)
        ):
            raise ValueError("滑块参数必须为有限数值")
        if not self.min < self.max or not 0 < self.step <= self.max - self.min:
            raise ValueError("滑块需要 min < max，且 0 < step <= max-min")
        if not self.min <= self.default <= self.max:
            raise ValueError("滑块默认值必须在范围内")
        return self


class ChoiceSpec(_Model):
    label: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=100)


class ControlSpec(_Model):
    type: Literal["slider", "toggle", "select", "stepper", "timeline", "button"]
    name: str = Field(min_length=1, max_length=80)
    purpose: str = Field(min_length=1, max_length=500)
    expected_change: str = Field(min_length=1, max_length=500)
    range: SliderRange | None = None
    choices: list[ChoiceSpec] | None = None

    @model_validator(mode="after")
    def usable(self):
        if self.type == "slider" and self.range is None:
            raise ValueError("slider 必须给出具体 range：min/max/step/default")
        if self.type == "select" and (
            not self.choices
            or len({c.value for c in self.choices}) != len(self.choices)
            or len(self.choices) < 2
        ):
            raise ValueError("select 必须至少包含两个不同的 choices")
        return self


class CanvasSpec(_Model):
    type: Literal["axis2d", "raw_canvas", "svg_d3", "p5", "three", "plotly", "none"]
    description: str = Field(min_length=1, max_length=1500)


class DisplaySpec(_Model):
    type: Literal["latex", "text", "metric", "progress"]
    name: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=500)


class InteractionCheck(_Model):
    action: str = Field(min_length=1, max_length=500)
    expected: str = Field(min_length=1, max_length=500)


class VizSpec(_Model):
    title: str = Field(min_length=1, max_length=150)
    concept: str = Field(min_length=1, max_length=1500)
    viz_pattern: str
    controls: list[ControlSpec] = Field(min_length=1, max_length=5)
    canvas: CanvasSpec
    display: list[DisplaySpec] = Field(min_length=1, max_length=4)
    initial_state: str = Field(min_length=1, max_length=1000)
    interaction_flow: str = Field(min_length=1, max_length=1500)
    key_insight: str = Field(min_length=1, max_length=1000)
    interaction_checks: list[InteractionCheck] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def known_pattern(self):
        if self.viz_pattern not in set(list_patterns()) | {"other"}:
            raise ValueError("viz_pattern 必须使用已列出的单个模板名称")
        names = [c.name for c in self.controls]
        if len(set(names)) != len(names):
            raise ValueError("控件名称不能重复")
        return self


class VizReview(_Model):
    # Keep the result explicit: improvement suggestions do not block publication.
    blocking_issues: list[str]
    suggestions: list[str]

    @property
    def accepted(self):
        return not self.blocking_issues


def parse_contract(raw: str, model):
    """Only a complete object satisfying the contract can pass; never default to yes."""
    text = (raw or "").strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        value = json.loads(text)
        return model.model_validate(value)
    except (ValueError, TypeError) as exc:
        raise VizQualityError(
            f"{model.__name__} 格式不合格：{str(exc)[:1600]}"
        ) from exc
