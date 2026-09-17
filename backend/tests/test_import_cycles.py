"""导入方向回归:整卷导入不得与能力层形成循环导入。

`paper_import_service` 依赖 `composition_service`,后者依赖 `app.capabilities.errors`,
而 `app.capabilities.__init__` 又要注册 `paper_imports` —— 顶层直连就会成环。
成环只在"以服务模块为首个入口"时暴露(打包后的导入顺序、脚本、worker),
先导入 app.main 的测试反而看不到,故这里显式用子进程从裸入口导入。
"""
import subprocess
import sys

BACKEND_ENTRYPOINTS = [
    "import app.services.paper_import_service",
    "import app.api.v1.endpoints.upload",
    "import app.capabilities",
]


def _import_in_fresh_interpreter(statement: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", statement],
        capture_output=True,
        text=True,
    )


def test_modules_import_standalone_without_circular_import():
    for statement in BACKEND_ENTRYPOINTS:
        result = _import_in_fresh_interpreter(statement)
        assert result.returncode == 0, f"{statement} failed:\n{result.stderr}"
        assert "circular import" not in result.stderr
