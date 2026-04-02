"""Universal clipboard write CLI for AI agents.

Cross-platform: Linux Wayland/X11, macOS, Windows, WSL.
Zero Python dependencies (stdlib only).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cbcopy import __version__

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


def _is_wsl() -> bool:
    """Detect Windows Subsystem for Linux via WSL_DISTRO_NAME env var."""
    return bool(os.environ.get("WSL_DISTRO_NAME"))


def _is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY"))


def _is_x11() -> bool:
    return bool(os.environ.get("DISPLAY"))


def _detect_platform() -> str:
    """Return platform identifier. Detection order is critical.

    WSL MUST be before Wayland because WSLg sets WAYLAND_DISPLAY.
    """
    if sys.platform == "win32":
        return "windows"
    if _is_wsl():
        return "wsl"
    if _is_wayland():
        return "wayland"
    if _is_x11():
        return "x11"
    if sys.platform == "darwin":
        return "darwin"
    return "unknown"


# ---------------------------------------------------------------------------
# Clipboard backends
# ---------------------------------------------------------------------------

_TOOL_NAMES = ("wl-copy", "xclip", "xsel", "pbcopy", "clip.exe")


def _run_clip(
    cmd: list[str],
    text: str,
    *,
    encoding: str = "utf-8",
    devnull_stderr: bool = False,
) -> int:
    """Run a clipboard tool, piping *text* to its stdin.

    Args:
        cmd: Command and arguments.
        text: Text to copy.
        encoding: Encoding for the text payload.
        devnull_stderr: Send stderr to DEVNULL (required for wl-copy
            which forks a daemon and would keep the pipe fd open).

    Returns:
        Process return code (0 = success).
    """
    input_data = text.encode(encoding)
    stderr_target = subprocess.DEVNULL if devnull_stderr else subprocess.PIPE
    tool_name = Path(cmd[0]).name
    try:
        proc = subprocess.run(
            cmd,
            input=input_data,
            stdout=subprocess.DEVNULL,
            stderr=stderr_target,
            timeout=30,
        )
    except FileNotFoundError:
        print(f"error: {tool_name} not found", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"error: failed to run {tool_name}: {e}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print(f"error: {tool_name} timed out after 30s", file=sys.stderr)
        return 1
    if proc.returncode != 0 and proc.stderr:
        detail = proc.stderr.decode(errors="replace").strip()
        print(f"error: {tool_name} failed (exit code {proc.returncode}): {detail}", file=sys.stderr)
        return 1
    if proc.returncode != 0:
        print(f"error: {tool_name} failed (exit code {proc.returncode})", file=sys.stderr)
        return 1
    return 0


def _copy_to_clipboard(text: str) -> int:
    """Copy *text* to the system clipboard.

    Returns 0 on success, 1 on failure (with message on stderr).
    """
    platform = _detect_platform()

    if platform == "windows":
        path = shutil.which("clip.exe")
        if not path:
            print("error: clip.exe not found", file=sys.stderr)
            return 1
        return _run_clip([path], text, encoding="utf-16-le")

    if platform == "wsl":
        path = shutil.which("clip.exe")
        if not path:
            print("error: clip.exe not found in WSL PATH", file=sys.stderr)
            return 1
        return _run_clip([path], text, encoding="utf-16-le")

    if platform == "wayland":
        path = shutil.which("wl-copy")
        if not path:
            print(
                "error: wl-copy not found\n  install wl-clipboard: sudo apt install wl-clipboard",
                file=sys.stderr,
            )
            return 1
        return _run_clip([path], text, devnull_stderr=True)

    if platform == "x11":
        xclip = shutil.which("xclip")
        if xclip:
            return _run_clip([xclip, "-selection", "clipboard"], text)
        xsel = shutil.which("xsel")
        if xsel:
            return _run_clip([xsel, "--clipboard", "--input"], text)
        print(
            "error: no X11 clipboard tool found\n  install one: sudo apt install xclip",
            file=sys.stderr,
        )
        return 1

    if platform == "darwin":
        path = shutil.which("pbcopy")
        if not path:
            print("error: pbcopy not found", file=sys.stderr)
            return 1
        return _run_clip([path], text)

    print(
        "error: no clipboard tool found\n"
        "  Linux Wayland: install wl-clipboard (wl-copy)\n"
        "  Linux X11: install xclip or xsel\n"
        "  macOS: pbcopy should be available by default\n"
        "  Windows/WSL: clip.exe should be available by default",
        file=sys.stderr,
    )
    return 1


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def _selected_tool() -> str | None:
    """Return the tool name that _copy_to_clipboard would actually use."""
    platform = _detect_platform()
    if platform in ("windows", "wsl"):
        return "clip.exe" if shutil.which("clip.exe") else None
    if platform == "wayland":
        return "wl-copy" if shutil.which("wl-copy") else None
    if platform == "x11":
        if shutil.which("xclip"):
            return "xclip"
        if shutil.which("xsel"):
            return "xsel"
        return None
    if platform == "darwin":
        return "pbcopy" if shutil.which("pbcopy") else None
    return None


def _diagnostics() -> None:
    """Print detected platform, env vars, and available tools."""
    platform = _detect_platform()
    active_tool = _selected_tool()
    print(f"platform: {platform}")
    print("env:")
    for var in ("WAYLAND_DISPLAY", "DISPLAY", "WSL_DISTRO_NAME"):
        val = os.environ.get(var)
        print(f"  {var}: {val if val else '(not set)'}")
    print(f"  sys.platform: {sys.platform}")
    print("tools:")

    for tool in _TOOL_NAMES:
        path = shutil.which(tool)
        if path and tool == active_tool:
            print(f"  {tool}: {path} (selected)")
        elif path:
            print(f"  {tool}: {path}")
        else:
            print(f"  {tool}: not found")


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------


def _read_input(args: argparse.Namespace) -> str | None:
    """Read text from --file, positional arg, or stdin. Precedence: --file > arg > stdin."""
    if args.file:
        p = Path(args.file)
        if not p.is_file():
            print(f"error: file not found: {args.file}", file=sys.stderr)
            return None
        try:
            return p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            print(f"error: cannot read {args.file}: {e}", file=sys.stderr)
            return None

    if args.text:
        return " ".join(args.text)

    if not sys.stdin.isatty():
        return sys.stdin.read()

    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cbcopy",
        description="Copy text to the system clipboard. Cross-platform.",
        epilog="Examples:\n"
        '  cbcopy "hello world"\n'
        "  echo hello | cbcopy\n"
        "  cbcopy --file notes.txt\n"
        "  cbcopy --diagnostics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "text",
        nargs="*",
        help="text to copy (multiple args joined with spaces)",
    )
    parser.add_argument(
        "--file",
        metavar="PATH",
        help="read text from file",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="print detected platform, env vars, and available tools",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.diagnostics:
        _diagnostics()
        raise SystemExit(0)

    text = _read_input(args)
    if text is None:
        parser.print_usage(sys.stderr)
        print("error: no input provided (pass text as argument, pipe stdin, or use --file)", file=sys.stderr)
        raise SystemExit(1)

    rc = _copy_to_clipboard(text)
    raise SystemExit(rc)
