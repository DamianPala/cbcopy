"""Tests for cbcopy CLI.

All clipboard tools and platform detection are mocked.
No actual clipboard interaction happens during tests.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from cbcopy.cli import (
    _copy_to_clipboard,
    _detect_platform,
    _diagnostics,
    _read_input,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(text=None, file=None, diagnostics=False):
    """Build a fake argparse.Namespace."""
    ns = MagicMock()
    ns.text = text or []
    ns.file = file
    ns.diagnostics = diagnostics
    return ns


def _mock_env(env: dict[str, str]):
    """Patch os.environ to contain only *env* keys (plus defaults)."""
    clean = {k: v for k, v in env.items() if v is not None}
    return patch.dict("os.environ", clean, clear=True)


def _mock_which(available: dict[str, str | None]):
    """Mock shutil.which to return paths for available tools."""

    def _which(name: str) -> str | None:
        return available.get(name)

    return patch("cbcopy.cli.shutil.which", side_effect=_which)


def _mock_run(returncode: int = 0, stderr: bytes = b""):
    """Mock subprocess.run to return a fake CompletedProcess."""
    result = subprocess.CompletedProcess(args=[], returncode=returncode, stderr=stderr)
    return patch("cbcopy.cli.subprocess.run", return_value=result)


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


class TestDetectPlatform:
    def test_windows_native(self):
        with patch("cbcopy.cli.sys") as mock_sys:
            mock_sys.platform = "win32"
            with _mock_env({}):
                assert _detect_platform() == "windows"

    def test_wsl(self):
        with patch("cbcopy.cli.sys") as mock_sys:
            mock_sys.platform = "linux"
            with _mock_env({"WSL_DISTRO_NAME": "Ubuntu"}):
                assert _detect_platform() == "wsl"

    def test_wsl_before_wayland(self):
        """WSL must win even when WAYLAND_DISPLAY is set (WSLg)."""
        with patch("cbcopy.cli.sys") as mock_sys:
            mock_sys.platform = "linux"
            with _mock_env({"WSL_DISTRO_NAME": "Ubuntu", "WAYLAND_DISPLAY": "wayland-0"}):
                assert _detect_platform() == "wsl"

    def test_wayland(self):
        with patch("cbcopy.cli.sys") as mock_sys:
            mock_sys.platform = "linux"
            with _mock_env({"WAYLAND_DISPLAY": "wayland-0"}):
                assert _detect_platform() == "wayland"

    def test_x11(self):
        with patch("cbcopy.cli.sys") as mock_sys:
            mock_sys.platform = "linux"
            with _mock_env({"DISPLAY": ":0"}):
                assert _detect_platform() == "x11"

    def test_darwin(self):
        with patch("cbcopy.cli.sys") as mock_sys:
            mock_sys.platform = "darwin"
            with _mock_env({}):
                assert _detect_platform() == "darwin"

    def test_unknown(self):
        with patch("cbcopy.cli.sys") as mock_sys:
            mock_sys.platform = "linux"
            with _mock_env({}):
                assert _detect_platform() == "unknown"


# ---------------------------------------------------------------------------
# Clipboard copy
# ---------------------------------------------------------------------------


class TestCopyToClipboard:
    def test_windows_clip_exe(self):
        with (
            patch("cbcopy.cli._detect_platform", return_value="windows"),
            _mock_which({"clip.exe": "/mnt/c/Windows/system32/clip.exe"}),
            _mock_run() as mock_run,
        ):
            rc = _copy_to_clipboard("hello")
            assert rc == 0
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[0][0] == ["/mnt/c/Windows/system32/clip.exe"]
            assert call_args[1]["input"] == "hello".encode("utf-16-le")

    def test_wsl_clip_exe_utf16le(self):
        with (
            patch("cbcopy.cli._detect_platform", return_value="wsl"),
            _mock_which({"clip.exe": "/mnt/c/Windows/system32/clip.exe"}),
            _mock_run() as mock_run,
        ):
            rc = _copy_to_clipboard("cześć 🎉")
            assert rc == 0
            call_args = mock_run.call_args
            assert call_args[1]["input"] == "cześć 🎉".encode("utf-16-le")

    def test_wayland_wl_copy(self):
        with (
            patch("cbcopy.cli._detect_platform", return_value="wayland"),
            _mock_which({"wl-copy": "/usr/bin/wl-copy"}),
            _mock_run() as mock_run,
        ):
            rc = _copy_to_clipboard("hello")
            assert rc == 0
            call_args = mock_run.call_args
            assert call_args[0][0] == ["/usr/bin/wl-copy"]
            assert call_args[1]["stderr"] == subprocess.DEVNULL

    def test_x11_xclip(self):
        with (
            patch("cbcopy.cli._detect_platform", return_value="x11"),
            _mock_which({"xclip": "/usr/bin/xclip"}),
            _mock_run() as mock_run,
        ):
            rc = _copy_to_clipboard("hello")
            assert rc == 0
            call_args = mock_run.call_args
            assert call_args[0][0] == ["/usr/bin/xclip", "-selection", "clipboard"]

    def test_x11_xsel_fallback(self):
        with (
            patch("cbcopy.cli._detect_platform", return_value="x11"),
            _mock_which({"xsel": "/usr/bin/xsel"}),
            _mock_run() as mock_run,
        ):
            rc = _copy_to_clipboard("hello")
            assert rc == 0
            call_args = mock_run.call_args
            assert call_args[0][0] == ["/usr/bin/xsel", "--clipboard", "--input"]

    def test_darwin_pbcopy(self):
        with (
            patch("cbcopy.cli._detect_platform", return_value="darwin"),
            _mock_which({"pbcopy": "/usr/bin/pbcopy"}),
            _mock_run() as mock_run,
        ):
            rc = _copy_to_clipboard("hello")
            assert rc == 0
            call_args = mock_run.call_args
            assert call_args[0][0] == ["/usr/bin/pbcopy"]

    def test_no_tool_found(self, capsys):
        with (
            patch("cbcopy.cli._detect_platform", return_value="unknown"),
        ):
            rc = _copy_to_clipboard("hello")
            assert rc == 1
            captured = capsys.readouterr()
            assert "no clipboard tool found" in captured.err

    def test_tool_fails_with_stderr(self, capsys):
        with (
            patch("cbcopy.cli._detect_platform", return_value="x11"),
            _mock_which({"xclip": "/usr/bin/xclip"}),
            _mock_run(returncode=1, stderr=b"permission denied"),
        ):
            rc = _copy_to_clipboard("hello")
            assert rc == 1
            captured = capsys.readouterr()
            assert "xclip failed" in captured.err
            assert "permission denied" in captured.err

    def test_empty_string(self):
        with (
            patch("cbcopy.cli._detect_platform", return_value="wayland"),
            _mock_which({"wl-copy": "/usr/bin/wl-copy"}),
            _mock_run() as mock_run,
        ):
            rc = _copy_to_clipboard("")
            assert rc == 0
            call_args = mock_run.call_args
            assert call_args[1]["input"] == b""


# ---------------------------------------------------------------------------
# Input handling
# ---------------------------------------------------------------------------


class TestReadInput:
    def test_file_input(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("file content", encoding="utf-8")
        args = _make_args(file=str(f))
        assert _read_input(args) == "file content"

    def test_file_not_found(self, capsys):
        args = _make_args(file="/nonexistent/path.txt")
        result = _read_input(args)
        assert result is None
        captured = capsys.readouterr()
        assert "file not found" in captured.err

    def test_positional_arg(self):
        args = _make_args(text=["hello", "world"])
        assert _read_input(args) == "hello world"

    def test_stdin_pipe(self):
        args = _make_args()
        with patch("cbcopy.cli.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = "piped text"
            assert _read_input(args) == "piped text"

    def test_tty_no_input(self):
        args = _make_args()
        with patch("cbcopy.cli.sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            result = _read_input(args)
            assert result is None

    def test_file_wins_over_positional(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("from file", encoding="utf-8")
        args = _make_args(text=["from", "arg"], file=str(f))
        assert _read_input(args) == "from file"


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


class TestDiagnostics:
    def test_diagnostics_output(self, capsys):
        with (
            patch("cbcopy.cli._detect_platform", return_value="wayland"),
            _mock_env({"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}),
            _mock_which({"wl-copy": "/usr/bin/wl-copy", "xclip": "/usr/bin/xclip"}),
        ):
            _diagnostics()
            captured = capsys.readouterr()
            assert "platform: wayland" in captured.out
            assert "wl-copy: /usr/bin/wl-copy (selected)" in captured.out
            assert "xclip: /usr/bin/xclip" in captured.out
            assert "pbcopy: not found" in captured.out


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestMainCLI:
    def test_diagnostics_flag(self, capsys):
        with (
            patch("cbcopy.cli.sys.argv", ["cbcopy", "--diagnostics"]),
            patch("cbcopy.cli._detect_platform", return_value="wayland"),
            _mock_env({"WAYLAND_DISPLAY": "wayland-0"}),
            _mock_which({"wl-copy": "/usr/bin/wl-copy"}),
            pytest.raises(SystemExit, match="0"),
        ):
            main()

    def test_no_input_on_tty(self, capsys):
        with (
            patch("cbcopy.cli.sys.argv", ["cbcopy"]),
            patch("cbcopy.cli.sys.stdin") as mock_stdin,
            pytest.raises(SystemExit, match="1"),
        ):
            mock_stdin.isatty.return_value = True
            main()

    def test_positional_arg_copy(self):
        with (
            patch("cbcopy.cli.sys.argv", ["cbcopy", "hello"]),
            patch("cbcopy.cli._copy_to_clipboard", return_value=0) as mock_copy,
            pytest.raises(SystemExit, match="0"),
        ):
            main()
        mock_copy.assert_called_once_with("hello")
