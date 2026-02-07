# rReader

RSS reader client for CLI (Command Line Interface), spinned off from [rterm](https://github.com/rainygirl/rterm).

Available in **Python** and **Rust**.

rReader는 한국어 RSS 피드를 지원합니다.

rReaderは日本語RSSフィードをサポートしています。

rReader该库支持中文RSS。

## Screenshot

![screenshot](https://user-images.githubusercontent.com/1021138/149663475-fa39c500-1c61-4d4c-93a2-d836b898edf8.gif)

## Project Structure

```
rreader/
├── rreader-python/    # Python implementation
│   ├── pyproject.toml
│   └── src/rreader/
└── rreader-rust/      # Rust implementation
    ├── Cargo.toml
    └── src/
```

## Installation

### Python Version

Requires Python 3.8+

```bash
# Install from PyPI
pip install rreader

# Run
rr
```

### Rust Version

Requires Rust 1.70+

```bash
cd rreader-rust
cargo install --path .

# Run
rreader
```

## Build from Source

### Python

```bash
git clone https://github.com/rainygirl/rreader
cd rreader/rreader-python

# Install in development mode
pip install -e .

# Or build distribution packages
pip install build
python -m build

# The built packages will be in dist/
# - rreader-x.x.x.tar.gz (source distribution)
# - rreader-x.x.x-py3-none-any.whl (wheel)
```

#### Cross-compile for i386 (32-bit)

Uses [PyInstaller](https://pyinstaller.org/) inside an Alpine Linux (musl) Docker container to produce a standalone i386 binary with no glibc dependency.

Requires [Docker](https://www.docker.com/).

```bash
cd rreader-python

# Build static binary for i386
./build-i386.sh

# Binary location: rreader-i386
```

### Rust

```bash
git clone https://github.com/rainygirl/rreader
cd rreader/rreader-rust

# Build release binary
cargo build --release

# Binary location: target/release/rreader
```

#### Cross-compile for i386 (32-bit)

Use [cross](https://github.com/cross-rs/cross) to build a statically linked i386 binary. This works on macOS and Linux, and produces a binary compatible with old glibc versions.

Requires [Docker](https://www.docker.com/).

```bash
# Install cross
cargo install cross --git https://github.com/cross-rs/cross

# Build static binary for i386
cd rreader-rust
cross build --release --target i686-unknown-linux-musl

# Binary location: target/i686-unknown-linux-musl/release/rreader
```

## RSS Feeds

You can add/modify RSS feeds in `~/.rreader/feeds.json`

Example:
```json
{
    "news": {
        "title": "Top News",
        "feeds": {
            "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
            "CNN": "http://rss.cnn.com/rss/edition_world.rss"
        }
    },
    "tech": {
        "title": "Tech",
        "feeds": {
            "Hacker News": "https://news.ycombinator.com/rss",
            "TechCrunch": "http://feeds.feedburner.com/TechCrunch/"
        },
        "show_author": true
    }
}
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `h`, `?` | Help |
| `↑`, `↓`, `j`, `k` | Navigate list |
| `PgUp`, `PgDn` | Fast scroll |
| `Enter`, `o` | Open link in browser |
| `Tab`, `Shift+Tab` | Switch category |
| `1`-`4` | Jump to category |
| `r` | Refresh |
| `g`, `G` | Go to top/bottom |
| `q`, `Esc`, `Ctrl+C` | Quit |

## Development

### Python

```bash
cd rreader-python

# Install with dev dependencies
pip install -e ".[dev]"

# Format code
black src/

# Lint
ruff check src/

# Run tests
pytest
```

### Rust

```bash
cd rreader-rust

# Run in debug mode
cargo run

# Run tests
cargo test

# Check code
cargo clippy
```

## Contributing

Feel free to fork & contribute!

## License

rReader is released under the MIT license.

## Credits

* [Lee JunHaeng aka rainygirl](https://rainygirl.com/)
