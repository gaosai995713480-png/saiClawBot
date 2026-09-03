"""工具注册中心。

用 @tool 装饰一个 async 函数，参数用 pydantic BaseModel 描述，
注册中心自动生成喂给 LLM 的 JSON Schema，并在调用前做参数校验。
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Awaitable, Callable, get_type_hints

from pydantic import BaseModel, ValidationError


class Risk(IntEnum):
    READ = 0      # 只读，随意调用
    WRITE = 1     # 有副作用，记录审计
    DANGER = 2    # 危险操作，需要用户二次确认


ToolFn = Callable[[BaseModel], Awaitable[str]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    params: type[BaseModel]
    fn: ToolFn
    risk: Risk

    def to_anthropic(self) -> dict[str, Any]:
        schema = self.params.model_json_schema()
        schema.pop("title", None)
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": schema,
        }


class ToolError(Exception):
    """工具执行失败。消息会原样回喂给 LLM，让它自己决定重试或换方案。"""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def to_anthropic(self) -> list[dict[str, Any]]:
        return [s.to_anthropic() for s in self._tools.values()]

    async def call(self, name: str, raw_input: dict[str, Any]) -> str:
        spec = self._tools.get(name)
        if spec is None:
            raise ToolError(f"unknown tool: {name}")
        try:
            params = spec.params.model_validate(raw_input)
        except ValidationError as e:
            raise ToolError(f"invalid arguments for {name}: {e}") from e
        return await spec.fn(params)


registry = ToolRegistry()


def tool(name: str, description: str, risk: Risk = Risk.READ):
    """把 `async def f(params: SomeModel) -> str` 注册为工具。"""

    def deco(fn: ToolFn) -> ToolFn:
        (param_name,) = inspect.signature(fn).parameters
        # 模块启用了 from __future__ import annotations，注解是字符串，需要解析
        model = get_type_hints(fn).get(param_name)
        if not (inspect.isclass(model) and issubclass(model, BaseModel)):
            raise TypeError(f"{fn.__name__}: parameter must be annotated with a pydantic BaseModel")
        registry.register(ToolSpec(name, description, model, fn, risk))
        return fn

    return deco
