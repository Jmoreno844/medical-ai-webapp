from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


try:
    import langgraph.prebuilt as _langgraph_prebuilt  # type: ignore
except Exception:
    _langgraph_prebuilt = ModuleType("langgraph.prebuilt")
    sys.modules["langgraph.prebuilt"] = _langgraph_prebuilt


if not hasattr(_langgraph_prebuilt, "ToolRuntime"):
    class _CompatToolRuntime(SimpleNamespace):
        pass

    _langgraph_prebuilt.ToolRuntime = _CompatToolRuntime


if not hasattr(_langgraph_prebuilt, "ToolNode"):
    class _CompatToolNode:
        def __init__(self, tools, handle_tool_errors=None):
            self.tools = tools
            self.handle_tool_errors = handle_tool_errors

        def __call__(self, *_args, **_kwargs):  # pragma: no cover - compat shim only
            raise RuntimeError(
                "Compat ToolNode shim no ejecuta tools. "
                "Instala una version de langgraph con ToolNode para tests de grafo completos."
            )

    _langgraph_prebuilt.ToolNode = _CompatToolNode
