import os

import pytest

from app.onlinecompiler import OnlineCompilerProvider


configured = all(
    os.getenv(name, "").strip()
    for name in ("ONLINECOMPILER_API_KEY", "ONLINECOMPILER_PYTHON_COMPILER", "ONLINECOMPILER_C_COMPILER")
)


@pytest.mark.skipif(not configured, reason="opt-in live OnlineCompiler.io configuration is not present")
def test_live_onlinecompiler_python_smoke() -> None:
    result = OnlineCompilerProvider().execute("mini_python", "print('CodeLens live smoke')")
    assert result.status == "Success"
    assert result.stdout == "CodeLens live smoke\n"
