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
├── rreader-rust/      # Rust 구현
│   ├── Cargo.toml
│   └── src/
└── rreader-web/       # 정적 HTML 생성기
    ├── generate.py
    └── feeds.json
```

## rreader-web

RSS 피드를 수집하고 Gemini API로 제목을 한국어로 번역한 뒤, 정적 HTML 페이지를 생성하는 웹 버전입니다. [news.coroke.net](https://news.coroke.net)에서 실제로 운영 중입니다.

### 특징

- **카드 뷰 / 목록 뷰** 전환 지원
- **소스별 그룹핑**: 카드 뷰에서 출처별로 최신 기사를 묶어 표시
- **썸네일 자동 수집**: RSS 피드 및 og:image 크롤링
- **번역 캐시**: 기사 URL 기준으로 번역 결과를 캐싱하여 API 호출 최소화
- **크론 연동**: 매시간 자동 실행에 최적화

### 실행 방법

```bash
cd rreader-web

# 의존성 설치
pip install feedparser google-genai

# Gemini API 키 설정 (번역 기능 사용 시)
echo '{"GEMINI_API_KEY": "your-key-here"}' > ~/.rreader_gemini_config.json

# 실행
python generate.py

# 생성된 파일 확인
open output/index.html
```

크론 등록 예시 (매시간 실행):

```
0 * * * * cd /path/to/rreader-web && python generate.py
```

### RSS 피드 설정

`feeds.json` 파일에서 카테고리와 피드를 설정합니다:

```json
{
    "tech": {
        "title": "Tech",
        "feeds": {
            "Hacker News": "https://news.ycombinator.com/rss",
            "TechCrunch": "https://techcrunch.com/feed/"
        }
    },
    "news": {
        "title": "Top News",
        "feeds": {
            "BBC": "http://feeds.bbci.co.uk/news/rss.xml",
            "CNN": "http://rss.cnn.com/rss/cnn_topstories.rss"
        }
    }
}
```

### 주의사항

- `generate.py` 내에 **Google Analytics(GA4)** 및 **Google AdSense** 코드가 포함되어 있습니다. 이는 [news.coroke.net](https://news.coroke.net) 전용 코드입니다. **재활용 시 반드시 해당 코드를 삭제하거나 본인의 코드로 교체하세요.** 해당 위치는 코드 내 주석(`<!-- news.coroke.net용 코드이니 재활용시 삭제하세요 -->`)으로 표시되어 있습니다.
- Gemini API 키가 없으면 번역 없이 원문 제목으로 생성됩니다.
- og:image 수집 시 외부 요청이 발생하므로 네트워크 환경에 따라 시간이 걸릴 수 있습니다.

## 설치

### Python 버전

Python 3.10 이상 필요

```bash
git clone https://github.com/rainygirl/rreader
cd rreader/rreader-python

# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -e .

# 실행
python src/rreader/run.py
```

Gemini 번역 기능을 사용하려면 추가 의존성을 설치합니다:

```bash
pip install -e ".[gemini]"
```

### Rust 버전

Rust 1.70 이상 필요

```bash
cd rreader-rust
cargo install --path .

# 실행
rreader
```

## 배포 패키지 빌드

### Python

```bash
cd rreader-python

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
