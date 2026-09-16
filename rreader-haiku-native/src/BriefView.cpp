#include "BriefView.h"

#include <algorithm>

#include "Colors.h"
#include "UrlOpener.h"

using namespace NewsColors;

namespace {
const float kPadV = 8.0f;
const float kPadH = 18.0f;
const float kItemPadV = 6.0f;
const float kTextIndent = 26.0f;
const float kTextSize = 15.0f;
const float kLineHeight = kTextSize * 1.55f;
const float kSourceSize = 12.0f;
const float kSourceGap = 8.0f;
const float kBadgeSize = 18.0f;
const float kBadgeTop = 8.0f;

const rgb_color kItemDivider = {0xf4, 0xf4, 0xf4, 255};
const rgb_color kSourceText = {0xaa, 0xaa, 0xaa, 255};

std::vector<BString> WrapWords(const BString& text, const BFont& font, float maxWidth) {
	std::vector<BString> lines;
	BString current;
	int32 start = 0;
	int32 length = text.Length();
	while (start < length) {
		int32 space = text.FindFirst(' ', start);
		BString word = space < 0 ? BString(text.String() + start)
								 : BString(text.String() + start, space - start);
		BString candidate = current;
		if (!candidate.IsEmpty())
			candidate << " ";
		candidate << word;
		if (!current.IsEmpty() && font.StringWidth(candidate.String()) > maxWidth) {
			lines.push_back(current);
			current = word;
		} else {
			current = candidate;
		}
		start = space < 0 ? length : space + 1;
	}
	if (!current.IsEmpty() || lines.empty())
		lines.push_back(current);
	return lines;
}

float Baseline(float lineTop, float lineHeight, const BFont& font) {
	font_height fh;
	font.GetHeight(&fh);
	return lineTop + (lineHeight - (fh.ascent + fh.descent)) / 2 + fh.ascent;
}
} // namespace

BriefView::BriefView(const std::vector<BriefItem>& items)
	: BView(BRect(0, 0, 100, 10), "brief", B_FOLLOW_NONE, B_WILL_DRAW),
	  fItems(items),
	  fHoverIndex(-1),
	  fSelectedLink(-1) {
	SetViewColor(kCardBackground);
	fTextFont.SetSize(kTextSize);
	fTextFont.SetFace(B_BOLD_FACE);
	fSourceFont.SetSize(kSourceSize);
	fBadgeFont.SetSize(11.0f);
	fBadgeFont.SetFace(B_BOLD_FACE);
}

void BriefView::SetWidth(float width) {
	float textWidth = width - 2 * kPadH - kTextIndent;
	float y = kPadV;
	fLayouts.clear();
	for (const BriefItem& item : fItems) {
		Layout layout;
		layout.top = y;
		layout.lines = WrapWords(item.text, fTextFont, textWidth);
		layout.sourceLine = layout.lines.size() - 1;
		float lastWidth = fTextFont.StringWidth(layout.lines.back().String());
		float sourceWidth = fSourceFont.StringWidth(item.source.String());
		if (!item.source.IsEmpty() && lastWidth + kSourceGap + sourceWidth > textWidth) {
			layout.sourceLine++;
			layout.sourceX = 0;
		} else {
			layout.sourceX = lastWidth + kSourceGap;
		}
		int lineCount = std::max((int)layout.lines.size(), layout.sourceLine + 1);
		y += kItemPadV + lineCount * kLineHeight + kItemPadV;
		layout.bottom = y;
		fLayouts.push_back(layout);
	}
	ResizeTo(width, y + kPadV);
	Invalidate();
}

void BriefView::Draw(BRect updateRect) {
	BRect bounds = Bounds();
	SetHighColor(kCardBorder);
	StrokeRect(bounds);

	for (size_t i = 0; i < fLayouts.size(); i++) {
		const Layout& layout = fLayouts[i];
		const BriefItem& item = fItems[i];

		if (i > 0) {
			SetHighColor(kItemDivider);
			StrokeLine(BPoint(kPadH, layout.top), BPoint(bounds.right - kPadH, layout.top));
		}

		BRect badge(kPadH, layout.top + kBadgeTop, kPadH + kBadgeSize - 1,
			layout.top + kBadgeTop + kBadgeSize - 1);
		SetHighColor(kAccent);
		FillEllipse(badge);
		BString number;
		number << (int32)(i + 1);
		SetFont(&fBadgeFont);
		SetHighColor(255, 255, 255);
		SetLowColor(kAccent);
		float numberWidth = fBadgeFont.StringWidth(number.String());
		DrawString(number.String(), BPoint(badge.left + (kBadgeSize - numberWidth) / 2,
			Baseline(badge.top, kBadgeSize, fBadgeFont)));

		float textX = kPadH + kTextIndent;
		float lineTop = layout.top + kItemPadV;
		SetLowColor(kCardBackground);
		SetFont(&fTextFont);
		SetHighColor(
			(int)i == fHoverIndex || (int)i == fSelectedLink ? kAccent : kTitleText);
		for (size_t l = 0; l < layout.lines.size(); l++) {
			DrawString(layout.lines[l].String(),
				BPoint(textX, Baseline(lineTop + l * kLineHeight, kLineHeight, fTextFont)));
		}

		if (!item.source.IsEmpty()) {
			SetFont(&fSourceFont);
			SetHighColor(kSourceText);
			DrawString(item.source.String(),
				BPoint(textX + layout.sourceX,
					Baseline(lineTop + layout.sourceLine * kLineHeight, kLineHeight, fTextFont)));
		}
	}
}

int BriefView::LinkCount() const {
	return (int)fItems.size();
}

BString BriefView::LinkUrl(int index) const {
	return fItems[index].url;
}

BRect BriefView::LinkFrame(int index) const {
	if (index >= (int)fLayouts.size())
		return BRect(0, 0, 0, 0);
	return BRect(0, fLayouts[index].top, Bounds().Width(), fLayouts[index].bottom);
}

void BriefView::SetSelectedLink(int index) {
	if (index == fSelectedLink)
		return;
	fSelectedLink = index;
	Invalidate();
}

int BriefView::ItemAt(BPoint where) const {
	for (size_t i = 0; i < fLayouts.size(); i++) {
		if (where.y >= fLayouts[i].top && where.y < fLayouts[i].bottom)
			return (int)i;
	}
	return -1;
}

void BriefView::MessageReceived(BMessage* message) {
	if (message->what == B_MOUSE_WHEEL_CHANGED && Parent() != NULL) {
		Parent()->MessageReceived(message);
		return;
	}
	BView::MessageReceived(message);
}

void BriefView::MouseDown(BPoint where) {
	int index = ItemAt(where);
	if (index >= 0 && !fItems[index].url.IsEmpty())
		UrlOpener::Open(fItems[index].url);
}

void BriefView::MouseMoved(BPoint where, uint32 code, const BMessage* dragMessage) {
	int index = code == B_EXITED_VIEW ? -1 : ItemAt(where);
	if (index != fHoverIndex) {
		fHoverIndex = index;
		Invalidate();
	}
}
