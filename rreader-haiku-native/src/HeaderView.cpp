#include "HeaderView.h"

#include <Font.h>
#include <Message.h>
#include <Window.h>

#include "Colors.h"

using namespace NewsColors;
using namespace NewsMetrics;


namespace {
const float kLogoFontSize = 18.0f;
const float kTabFontSize = 14.0f;
const float kTabPaddingH = 14.0f;
const float kTabPaddingV = 6.0f;
const float kTabGap = 2.0f;
const float kLogoTabGap = 24.0f;
} // namespace

HeaderView::HeaderView(BRect frame)
	: BView(frame, "header", B_FOLLOW_LEFT_RIGHT | B_FOLLOW_TOP,
		  B_WILL_DRAW | B_FRAME_EVENTS | B_NAVIGABLE) {
	SetViewColor(kAccent);
}

void HeaderView::SetTabs(const std::vector<BString>& keys, const std::vector<BString>& titles,
	const BString& activeKey) {
	fTabs.clear();
	for (size_t i = 0; i < keys.size(); i++) {
		Tab tab;
		tab.key = keys[i];
		tab.title = (i < titles.size()) ? titles[i] : keys[i];
		fTabs.push_back(tab);
	}
	fActiveKey = activeKey;
	LayoutTabs();
	Invalidate();
}

void HeaderView::SetActiveTab(const BString& key) {
	fActiveKey = key;
	Invalidate();
}

void HeaderView::LayoutTabs() {
	BFont tabFont;
	tabFont.SetSize(kTabFontSize);
	tabFont.SetFace(B_BOLD_FACE);

	BFont logoFont;
	logoFont.SetSize(kLogoFontSize);
	logoFont.SetFace(B_HEAVY_FACE);
	float logoWidth = logoFont.StringWidth("news.coroke.net");

	float x = kTabBarPaddingH + logoWidth + kLogoTabGap;
	float top = 10.0f;
	float bottom = kHeaderHeight - 10.0f;
	for (size_t i = 0; i < fTabs.size(); i++) {
		float w = tabFont.StringWidth(fTabs[i].title.String()) + 2 * kTabPaddingH;
		fTabs[i].rect = BRect(x, top, x + w, bottom);
		x += w + kTabGap;
	}
}

void HeaderView::FrameResized(float width, float height) {
	BView::FrameResized(width, height);
	Invalidate();
}

void HeaderView::Draw(BRect updateRect) {
	BRect bounds = Bounds();
	SetHighColor(kAccent);
	FillRect(bounds);

	BFont logoFont;
	logoFont.SetSize(kLogoFontSize);
	logoFont.SetFace(B_HEAVY_FACE);
	SetFont(&logoFont);
	SetHighColor(kHeaderText);
	font_height lfh;
	logoFont.GetHeight(&lfh);
	DrawString(
		"news.coroke.net", BPoint(kTabBarPaddingH, kHeaderHeight / 2 + lfh.ascent / 2 - 1));

	BFont tabFont;
	tabFont.SetSize(kTabFontSize);
	tabFont.SetFace(B_BOLD_FACE);
	SetFont(&tabFont);
	font_height tfh;
	tabFont.GetHeight(&tfh);

	SetDrawingMode(B_OP_ALPHA);
	for (size_t i = 0; i < fTabs.size(); i++) {
		bool active = fTabs[i].key == fActiveKey;
		if (active && IsFocus()) {
			SetHighColor(255, 255, 255, 64);
			FillRoundRect(fTabs[i].rect, 4, 4);
		}
		SetHighColor(active ? kHeaderText : kHeaderTextDim);
		float textY = fTabs[i].rect.top + (fTabs[i].rect.Height() / 2) + tfh.ascent / 2 - 1;
		DrawString(fTabs[i].title.String(), BPoint(fTabs[i].rect.left + kTabPaddingH, textY));

		if (active) {
			// .tab-nav a.active { border-bottom: 2px solid rgba(255,255,255,0.9); }
			SetHighColor(kHeaderText);
			BRect underline = fTabs[i].rect;
			FillRect(BRect(underline.left, underline.bottom - 2, underline.right,
				underline.bottom));
		}
	}
}

void HeaderView::SelectTab(size_t index, bool keyboard) {
	BMessage msg(kMsgTabSelected);
	msg.AddString("key", fTabs[index].key);
	msg.AddBool("keyboard", keyboard);
	Window()->PostMessage(&msg);
}

void HeaderView::MouseDown(BPoint where) {
	for (size_t i = 0; i < fTabs.size(); i++) {
		if (fTabs[i].rect.Contains(where)) {
			SelectTab(i, false);
			return;
		}
	}
}

void HeaderView::KeyDown(const char* bytes, int32 numBytes) {
	if (numBytes < 1 || fTabs.empty()) {
		BView::KeyDown(bytes, numBytes);
		return;
	}

	size_t active = 0;
	for (size_t i = 0; i < fTabs.size(); i++) {
		if (fTabs[i].key == fActiveKey)
			active = i;
	}

	switch (bytes[0]) {
		case B_LEFT_ARROW:
			if (active > 0)
				SelectTab(active - 1, true);
			return;
		case B_RIGHT_ARROW:
			if (active + 1 < fTabs.size())
				SelectTab(active + 1, true);
			return;
		case B_DOWN_ARROW:
		case B_ENTER:
		case B_SPACE:
			Window()->PostMessage(kMsgFocusContent);
			return;
	}
	BView::KeyDown(bytes, numBytes);
}

void HeaderView::MakeFocus(bool focus) {
	BView::MakeFocus(focus);
	Invalidate();
}
