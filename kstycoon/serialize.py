"""Generic (de)serialisation for the dataclass model.

State is persisted as plain JSON so saves are portable and human-inspectable
(the eventual web UI will read/write the same format). Reconstruction is driven
by the dataclasses' own type hints, so the model can grow without touching this
module.
"""

from __future__ import annotations

import dataclasses
import json
import typing
from typing import Any

from . import model as m


def _from_obj(tp: Any, obj: Any) -> Any:
    if obj is None:
        return None
    origin = typing.get_origin(tp)

    # Optional[X] / Union -> first non-None arg
    if origin is typing.Union:
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        return _from_obj(args[0], obj)

    if dataclasses.is_dataclass(tp):
        hints = typing.get_type_hints(tp)
        kwargs = {}
        for f in dataclasses.fields(tp):
            if f.name in obj:
                kwargs[f.name] = _from_obj(hints[f.name], obj[f.name])
        return tp(**kwargs)

    if origin in (list, tuple):
        (arg,) = typing.get_args(tp) or (Any,)
        return [_from_obj(arg, x) for x in obj]

    if origin is dict:
        _, vt = typing.get_args(tp) or (str, Any)
        return {k: _from_obj(vt, v) for k, v in obj.items()}

    return obj


def to_dict(state: m.GameState) -> dict:
    return dataclasses.asdict(state)


def from_dict(data: dict) -> m.GameState:
    return _from_obj(m.GameState, data)


def save(state: m.GameState, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(to_dict(state), fh, indent=2, ensure_ascii=False)


def load(path: str) -> m.GameState:
    with open(path, encoding="utf-8") as fh:
        return from_dict(json.load(fh))
