import pytest
from pydantic import BaseModel

from saiclawbot.tools import ToolError, ToolRegistry, ToolSpec, Risk


class AddParams(BaseModel):
    a: int
    b: int


async def add(p: AddParams) -> str:
    return str(p.a + p.b)


@pytest.fixture
def reg():
    r = ToolRegistry()
    r.register(ToolSpec("add", "add two ints", AddParams, add, Risk.READ))
    return r


async def test_call_ok(reg):
    assert await reg.call("add", {"a": 1, "b": 2}) == "3"


async def test_invalid_args(reg):
    with pytest.raises(ToolError):
        await reg.call("add", {"a": "x"})


async def test_unknown_tool(reg):
    with pytest.raises(ToolError):
        await reg.call("nope", {})


def test_schema(reg):
    (schema,) = reg.to_anthropic()
    assert schema["name"] == "add"
    assert set(schema["input_schema"]["properties"]) == {"a", "b"}


def test_duplicate(reg):
    with pytest.raises(ValueError):
        reg.register(ToolSpec("add", "dup", AddParams, add, Risk.READ))
