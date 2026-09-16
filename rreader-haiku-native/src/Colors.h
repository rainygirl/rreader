// Colors.h -- design constants ported 1:1 from rreader-web/generate.py's
// inline <style> block, so the native app matches the web design exactly.
// Keep any value here in sync with generate.py if the web design changes.
#ifndef NEWS_COROKE_COLORS_H
#define NEWS_COROKE_COLORS_H

#include <GraphicsDefs.h>

namespace NewsColors {

// ACCENT = "#ec8c6f" (header background, active tab, link hover accents)
static const rgb_color kAccent = {0xec, 0x8c, 0x6f, 255};
// A touch darker, used for pressed/active states where the flat accent
// alone wouldn't read as "pressed" on a solid accent background.
static const rgb_color kAccentDark = {0xd9, 0x74, 0x55, 255};

// body background: #f4f5f7
static const rgb_color kPageBackground = {0xf4, 0xf5, 0xf7, 255};
// body color: #222
static const rgb_color kBodyText = {0x22, 0x22, 0x22, 255};

// .group-card background/border
static const rgb_color kCardBackground = {0xff, 0xff, 0xff, 255};
static const rgb_color kCardBorder = {0xe8, 0xe8, 0xe8, 255};
static const rgb_color kCardBorderHover = {0xd5, 0xd5, 0xd5, 255};

// .group-source / .group-top-title color: #1a1a1a
static const rgb_color kTitleText = {0x1a, 0x1a, 0x1a, 255};
// .group-sub color: #444
static const rgb_color kSubText = {0x44, 0x44, 0x44, 255};
// .group-date / .group-favicon-adjacent muted text: #bbb
static const rgb_color kMutedText = {0xbb, 0xbb, 0xbb, 255};
// .group-sub top border: #f2f2f2
static const rgb_color kDivider = {0xf2, 0xf2, 0xf2, 255};
// .group-top:hover / .group-sub:hover background: #fdf6f4
static const rgb_color kHoverBackground = {0xfd, 0xf6, 0xf4, 255};

// header text on the accent background
static const rgb_color kHeaderText = {0xff, 0xff, 0xff, 255};
static const rgb_color kHeaderTextDim = {0xff, 0xff, 0xff, 191}; // rgba(255,255,255,0.75)

} // namespace NewsColors

// ── Layout metrics (all from generate.py's CSS) ──────────────────────────
namespace NewsMetrics {

const float kHeaderHeight = 54.0f;
const float kTabBarPaddingH = 16.0f;

// Card grid: gap 20px vertical / 12px horizontal, container padding 12/16/24.
// Cards are fixed-width and the number of columns is however many fit --
// this is the desktop 3-column width (1200px max content width, 16px side
// padding, 12px gaps, 3 columns) generalized as a fixed card width so the
// grid can reflow to 2/3/4+ columns on a native window of any size.
const float kCardWidth = 360.0f;
const float kGridGapH = 12.0f;
const float kGridGapV = 20.0f;
const float kGridPaddingH = 16.0f;
const float kGridPaddingTop = 12.0f;
const float kGridPaddingBottom = 24.0f;

const float kCardCornerRadius = 10.0f;
const float kCardHeaderPaddingH = 14.0f;
const float kCardHeaderPaddingTop = 12.0f;
const float kCardHeaderPaddingBottom = 10.0f;
const float kFaviconSize = 16.0f;
const float kThumbSize = 68.0f;
const float kCardBottomPadding = 10.0f;

} // namespace NewsMetrics

#endif // NEWS_COROKE_COLORS_H
