"""工作台"存活"端到端 smoke。

注意：本测试不直接对子进程发起 HTTP 请求。理由：

- uvicorn 在 Windows 上使用 asyncio ProactorEventLoop，
  对 ``accept()`` 会出现已知的 ``WinError 64`` 抖动，导致服务器活着但
  偶发 accept 失败，使 HTTP 路径短时不可达。
- HTTP 路径的真实 e2e 由 :class:`tests.integration.test_backend_api_app.BackendApiAppTest`
  使用 ``fastapi.testclient.TestClient`` 在同一进程内验证，避免 Windows 抖动。
- 本测试只验证：

  1. :mod:`scripts.run_workbench_backend` 与 ``uvicorn backend.apps.api.main:app``
     能成功 ``Popen``；
  2. 子进程绑到选定端口后在 5 秒内仍存活（``poll() is None``）；
  3. 优雅终止后退出码非 0。
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC_ROOT = REPO_ROOT / "backend" / "src"

for candidate in (REPO_ROOT, BACKEND_SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


def _free_port() -> int:
    """让 OS 内核分配一个空闲端口，避免与本机其它 uvicorn 进程冲突。"""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _terminate_subprocess(proc: subprocess.Popen) -> None:
    """跨平台优雅终止 subprocess 后兜底 kill。"""

    try:
        if sys.platform == "win32":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGINT)
        proc.wait(timeout=5)
    except (subprocess.TimeoutExpired, ValueError):
        proc.kill()


class WorkbenchEndToEndTest(unittest.TestCase):
    def test_backend_subprocess_stays_alive_then_exits_cleanly(self) -> None:
        port = _free_port()

        env = os.environ.copy()
        py_path = env.get("PYTHONPATH", "")
        paths = [str(REPO_ROOT), str(BACKEND_SRC_ROOT)]
        if py_path:
            paths.append(py_path)
        env["PYTHONPATH"] = os.pathsep.join(paths)

        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.apps.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ]
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            # 给 uvicorn 一点时间绑定端口（不会发起 HTTP 请求，避免 Windows 抖动）。
            time.sleep(3.0)
            self.assertIsNone(
                proc.poll(),
                f"uvicorn 子进程在 3 秒内意外退出，returncode={proc.returncode}",
            )
        finally:
            _terminate_subprocess(proc)

        self.assertIsNotNone(proc.returncode, "uvicorn 子进程未被优雅终止")

    def test_run_workbench_backend_script_can_be_invoked(self) -> None:
        """``scripts/run_workbench_backend.py`` 至少能在子进程里 ``--help`` 风格启动。"""

        env = os.environ.copy()
        py_path = env.get("PYTHONPATH", "")
        paths = [str(REPO_ROOT), str(BACKEND_SRC_ROOT)]
        if py_path:
            paths.append(py_path)
        env["PYTHONPATH"] = os.pathsep.join(paths)

        script_path = REPO_ROOT / "scripts" / "run_workbench_backend.py"
        self.assertTrue(script_path.is_file(), f"缺少启动脚本：{script_path}")

        # 直接 ``python scripts/run_workbench_backend.py --help``：
        # argparse 在 --help 时 sys.exit(0)，不应留下 listen 进程。
        proc = subprocess.Popen(
            [sys.executable, str(script_path), "--help"],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            self.fail(f"启动脚本 --help 超时未返回；stderr={stderr.decode(errors='replace')[-300:]}")

        self.assertEqual(
            proc.returncode,
            0,
            f"启动脚本 --help 退出码非 0；stderr={stderr.decode(errors='replace')[-400:]}",
        )
        self.assertIn(b"workbench backend launcher", stdout.lower() + stderr.lower())


if __name__ == "__main__":
    unittest.main()
