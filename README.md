# cbcopy

Universal clipboard write CLI for AI agents. Cross-platform: Linux Wayland/X11, macOS, Windows, WSL.

Zero Python dependencies (stdlib only). Delegates to system clipboard tools with correct detection order and encoding.

## Setup (local development)

```
uv sync
```

## Usage

```bash
# Copy text from argument
cbcopy "hello world"

# Pipe from stdin
echo "hello" | cbcopy

# Copy file contents
cbcopy --file notes.txt

# Show detected platform and available tools
cbcopy --diagnostics
```

Silent on success (exit 0). Clear error on stderr (exit 1).

## Install globally

```bash
uv tool install .
```

After install, run directly:

```bash
cbcopy "hello world"
```

## Platform support

| Platform | Detection | Tool | Encoding |
|----------|-----------|------|----------|
| Windows | `sys.platform == "win32"` | clip.exe | UTF-16LE |
| WSL | `WSL_DISTRO_NAME` env | clip.exe | UTF-16LE |
| Linux Wayland | `WAYLAND_DISPLAY` env | wl-copy | UTF-8 |
| Linux X11 | `DISPLAY` env | xclip / xsel | UTF-8 |
| macOS | `sys.platform == "darwin"` | pbcopy | UTF-8 |

Detection order matters: WSL is checked before Wayland because WSLg sets `WAYLAND_DISPLAY`.

## Tests

```
uv run pytest
```
