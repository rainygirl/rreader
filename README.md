# rReader

CLI(커맨드 라인 인터페이스)용 RSS 리더 클라이언트. [rterm](https://github.com/rainygirl/rterm)에서 분리된 프로젝트입니다.

**Python**과 **Rust** 두 가지 버전으로 제공됩니다.

한국어, 日本語, 中文 RSS 피드를 지원합니다.

Python 코드는 Gemini API로 영문 RSS를 한국어로 번역합니다.

## 스크린샷

![screenshot](https://user-images.githubusercontent.com/1021138/149663475-fa39c500-1c61-4d4c-93a2-d836b898edf8.gif)

## 프로젝트 구조

```
rreader/
├── rreader-python/    # Python 구현
│   ├── pyproject.toml
│   └── src/rreader/
└── rreader-rust/      # Rust 구현
    ├── Cargo.toml
    └── src/
```

## 설치

### Python 버전

Python 3.8 이상 필요

```bash
# PyPI에서 설치
pip install rreader

# 실행
rr
```

### Rust 버전

Rust 1.70 이상 필요

```bash
cd rreader-rust
cargo install --path .

# 실행
rreader
```

## 소스에서 빌드

### Python

```bash
git clone https://github.com/rainygirl/rreader
cd rreader/rreader-python

# 개발 모드로 설치
pip install -e .

# 또는 배포 패키지 빌드
pip install build
python -m build

# 빌드된 패키지는 dist/ 디렉토리에 생성됩니다
# - rreader-x.x.x.tar.gz (소스 배포판)
# - rreader-x.x.x-py3-none-any.whl (wheel)
```

#### 단일 실행 파일 빌드

```
cd rreader-python

# 바이너리 빌드
./build-standaline.sh

# 바이너리 위치: dist/rreader
```

#### i386 (32비트) 크로스 컴파일

Debian (glibc) Docker 컨테이너 안에서 [PyInstaller](https://pyinstaller.org/)를 사용하여 표준 32비트 Linux 배포판과 호환되는 i386 바이너리를 생성합니다.

[Docker](https://www.docker.com/)가 필요합니다.

```bash
cd rreader-python

# i386용 바이너리 빌드
./build-i386.sh

# 바이너리 위치: rreader-i386
```

### Rust

```bash
git clone https://github.com/rainygirl/rreader
cd rreader/rreader-rust

# 릴리스 바이너리 빌드
cargo build --release

# 바이너리 위치: target/release/rreader
```

#### i386 (32비트) 크로스 컴파일

[cross](https://github.com/cross-rs/cross)를 사용하여 정적 링크된 i386 바이너리를 빌드합니다. macOS와 Linux에서 동작하며, 구버전 glibc와 호환되는 바이너리를 생성합니다.

[Docker](https://www.docker.com/)가 필요합니다.

```bash
# cross 설치
cargo install cross --git https://github.com/cross-rs/cross

# i386용 정적 바이너리 빌드
cd rreader-rust
cross build --release --target i686-unknown-linux-musl

# 바이너리 위치: target/i686-unknown-linux-musl/release/rreader
```

## RSS 피드

`~/.rreader/feeds.json` 파일에서 RSS 피드를 추가하거나 수정할 수 있습니다.

예시:
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

## 단축키

| 키 | 동작 |
|-----|--------|
| `h`, `?` | 도움말 |
| `↑`, `↓`, `j`, `k` | 목록 탐색 |
| `PgUp`, `PgDn` | 빠른 스크롤 |
| `Enter`, `o` | 브라우저에서 링크 열기 |
| `Tab`, `Shift+Tab` | 카테고리 전환 |
| `1`-`4` | 카테고리로 바로 이동 |
| `r` | 새로고침 |
| `g`, `G` | 맨 위/아래로 이동 |
| `q`, `Esc`, `Ctrl+C` | 종료 |

## 개발

### Python

```bash
cd rreader-python

# 개발 의존성과 함께 설치
pip install -e ".[dev]"

# 코드 포맷팅
black src/

# 린트
ruff check src/

# 테스트 실행
pytest
```

### Rust

```bash
cd rreader-rust

# 디버그 모드로 실행
cargo run

# 테스트 실행
cargo test

# 코드 검사
cargo clippy
```

## 기여

자유롭게 포크하고 기여해주세요!

## 라이선스

rReader는 MIT 라이선스로 배포됩니다.

## 크레딧

* [Lee JunHaeng aka rainygirl](https://rainygirl.com/)
