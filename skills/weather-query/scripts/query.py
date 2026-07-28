"""Weather Query CLI — 薄壳，调用 weather_lib

这个文件存在的唯一理由是给 agent / 用户一个稳定的入口。
所有逻辑都在 weather_lib.py 里。
"""
import os
import sys


def _setup_console_encoding():
    """自愈控制台编码，让 `python query.py 北京` 在任何 shell 下都不乱码。

    背景：cmd.exe 默认 GBK (cp936)，直接 print 中文会显示为 `???`。
    PowerShell 5.1+ / Git Bash / WSL 通常默认 UTF-8 没事。

    处理顺序（先低开销后高开销）：
    1. 如果 PYTHONIOENCODING 已设（或 stdout 已是 UTF-8）→ 不动
    2. 如果父 shell 是 cmd.exe（Windows + 缺 POSIX 标记）→ chcp 65001 + reconfigure
    3. reconfigure stdout/stderr 为 UTF-8 + errors="replace"，防编码异常 crash
    """
    # 1) 用户/包装已显式配置 → 尊重
    if os.environ.get("PYTHONIOENCODING"):
        return

    out = getattr(sys.stdout, "encoding", None)
    if out and out.lower().replace("-", "") in ("utf8", "utf16", "utf16le", "utf16be"):
        return  # 已经是 UTF 系编码

    # 2) Windows cmd.exe 检测：父 shell 标识都不是 PowerShell/Git-Bash/WSL/Bash
    if os.name == "nt":
        shell_markers = (
            os.environ.get("PSModulePath"),        # PowerShell
            os.environ.get("BASH"),                # Git Bash / WSL
            os.environ.get("WT_SESSION"),          # Windows Terminal
            os.environ.get("TERM_PROGRAM"),
        )
        is_friendly_shell = any(shell_markers) or "bash" in (os.environ.get("SHELL") or "").lower()
        if not is_friendly_shell:
            # 极可能是 cmd.exe 缺省 → 切到 UTF-8 codepage
            try:
                os.system("chcp 65001 >nul 2>&1")
            except Exception:
                pass

    # 3) 兜底：强制 stdout/stderr UTF-8，errors="replace" 防单字符解码失败崩溃
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


# 必须在 import weather_lib 之前调用（print 路径都要 UTF-8）
_setup_console_encoding()

# scripts/ 目录自包含：让 `python scripts/query.py 北京` 也能找到同目录的 weather_lib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import weather_lib as wl  # noqa: E402


def main():
    sys.exit(wl.main())


if __name__ == "__main__":
    main()