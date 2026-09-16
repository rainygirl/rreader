#include "CardView.h"

#include <Font.h>
#include <Message.h>
#include <Messenger.h>
#include <Window.h>

#include "Colors.h"
#include "ImageLoader.h"
#include "UrlOpener.h"

using namespace NewsColors;
using namespace NewsMetrics;

namespace {
const float kSourceFontSize = 14.0f;
const float kDateFontSize = 11.0f;
const float kTitleFontSize = 14.0f;
const float kTitleFontSizeWithThumb = 16.0f;
const float kSubFontSize = 14.0f;
const float kTitleLineHeight = 1.55f;
const float kSubLineHeight = 1.45f;
const float kTopPaddingTop = 14.0f;
const float kTopPaddingBottom = 14.0f;
const float kTopPaddingLeft = 12.0f;
const float kTopPaddingRight = 14.0f;
const float kTopInnerGap = 10.0f;
const float kSubPaddingV = 7.0f;
const float kSubPaddingH = 14.0f;
} // namespace

CardView::CardView(BRect frame, const SourceCard& card)
	: BView(frame, "card", B_FOLLOW_NONE, B_WILL_DRAW | B_FRAME_EVENTS),
	  fData(card),
	  fHeaderBottom(0),
	  fTopAreaBottom(0),
	  fThumbBitmap(NULL),
	  fFaviconBitmap(NULL),
	  fThumbFailed(false),
	  fFaviconFailed(false),
	  fHoveringTop(false),
	  fHoveringSubIndex(-1) {
	SetViewColor(kCardBackground);
	RecomputeHeight();
	ResizeTo(kCardWidth, Bounds().Height());
}

CardView::~CardView() {
	delete fThumbBitmap;
	delete fFaviconBitmap;
}

void CardView::AttachedToWindow() {
	BView::AttachedToWindow();
	SetEventMask(B_POINTER_EVENTS, 0);

	if (!fData.thumbUrl.IsEmpty())
		ImageLoader::LoadAsync(fData.thumbUrl, BMessenger(this));

	if (!fData.faviconDomain.IsEmpty()) {
		BString faviconUrl("https://www.google.com/s2/favicons?domain=");
		faviconUrl << fData.faviconDomain << "&sz=32";
		ImageLoader::LoadAsync(faviconUrl, BMessenger(this));
	}
}

std::vector<BString> CardView::WrapText(
	const BString& text, const BFont& font, float maxWidth) const {
	std::vector<BString> lines;
	BString current;
	int32 start = 0;
	int32 length = text.Length();

	while (start < length) {
		int32 spacePos = text.FindFirst(' ', start);
		BString word = (spacePos < 0)
			? BString(text.String() + start)
			: BString(text.String() + start, spacePos - start);

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

		start = (spacePos < 0) ? length : spacePos + 1;
	}
	if (!current.IsEmpty())
		lines.push_back(current);
	if (lines.empty())
		lines.push_back(BString());
	return lines;
}

BString CardView::TruncateWithEllipsis(
	const BString& text, const BFont& font, float maxWidth) const {
	BString result(text);
	font.TruncateString(&result, B_TRUNCATE_END, maxWidth);
	return result;
}

void CardView::RecomputeHeight() {
	float innerWidth = kCardWidth - kTopPaddingLeft - kTopPaddingRight;
	if (!fData.thumbUrl.IsEmpty())
		innerWidth -= (kThumbSize + kTopInnerGap);

	BFont titleFont;
	titleFont.SetSize(fData.thumbUrl.IsEmpty() ? kTitleFontSize : kTitleFontSizeWithThumb);
	titleFont.SetFace(fData.thumbUrl.IsEmpty() ? B_REGULAR_FACE : B_BOLD_FACE);

	fTitleLines = WrapText(fData.topTitle, titleFont, innerWidth);

	font_height fh;
	titleFont.GetHeight(&fh);
	float titleLineHeight = (fh.ascent + fh.descent + fh.leading) * kTitleLineHeight;

	fHeaderBottom = kCardHeaderPaddingTop + kFaviconSize + kCardHeaderPaddingBottom;

	float topInnerHeight = std::max(
		fData.thumbUrl.IsEmpty() ? 0.0f : kThumbSize, fTitleLines.size() * titleLineHeight);
	fTopAreaBottom = fHeaderBottom + kTopPaddingTop + topInnerHeight + kTopPaddingBottom;

	BFont subFont;
	subFont.SetSize(kSubFontSize);
	font_height subFh;
	subFont.GetHeight(&subFh);
	float subLineHeight =
		(subFh.ascent + subFh.descent + subFh.leading) * kSubLineHeight + 2 * kSubPaddingV;

	float total = fTopAreaBottom + fData.subs.size() * subLineHeight + kCardBottomPadding;
	ResizeTo(kCardWidth, total);
}

void CardView::Draw(BRect updateRect) {
	BRect bounds = Bounds();

	SetHighColor(kCardBackground);
	FillRoundRect(bounds, kCardCornerRadius, kCardCornerRadius, B_SOLID_HIGH);
	SetHighColor(fHoveringTop ? kCardBorderHover : kCardBorder);
	StrokeRoundRect(bounds, kCardCornerRadius, kCardCornerRadius);

	// ── Header: favicon, source, date ──
	float hx = kCardHeaderPaddingH;
	float hy = kCardHeaderPaddingTop;
	if (fFaviconBitmap != NULL) {
		DrawBitmap(fFaviconBitmap, BRect(hx, hy, hx + kFaviconSize, hy + kFaviconSize));
		hx += kFaviconSize + 6;
	}
	BFont sourceFont;
	sourceFont.SetSize(kSourceFontSize);
	sourceFont.SetFace(B_BOLD_FACE);
	SetFont(&sourceFont);
	SetHighColor(kTitleText);
	font_height sfh;
	sourceFont.GetHeight(&sfh);
	DrawString(fData.source.String(), BPoint(hx, hy + kFaviconSize / 2 + sfh.ascent / 2));

	BFont dateFont;
	dateFont.SetSize(kDateFontSize);
	SetFont(&dateFont);
	SetHighColor(kMutedText);
	float sourceWidth = sourceFont.StringWidth(fData.source.String());
	font_height dfh;
	dateFont.GetHeight(&dfh);
	DrawString(fData.date.String(),
		BPoint(hx + sourceWidth + 8, hy + kFaviconSize / 2 + dfh.ascent / 2));

	// ── Top story: thumbnail + title ──
	float tx = kTopPaddingLeft;
	float ty = fHeaderBottom + kTopPaddingTop;
	float titleX = tx;
	if (fThumbBitmap != NULL) {
		DrawBitmap(fThumbBitmap, BRect(tx, ty, tx + kThumbSize, ty + kThumbSize));
		titleX = tx + kThumbSize + kTopInnerGap;
	} else if (!fData.thumbUrl.IsEmpty() && !fThumbFailed) {
		titleX = tx + kThumbSize + kTopInnerGap; // reserve space while still loading
	}

	BFont titleFont;
	titleFont.SetSize(fData.thumbUrl.IsEmpty() ? kTitleFontSize : kTitleFontSizeWithThumb);
	titleFont.SetFace(fData.thumbUrl.IsEmpty() ? B_REGULAR_FACE : B_BOLD_FACE);
	SetFont(&titleFont);
	SetHighColor(fHoveringTop ? kAccent : kTitleText);
	font_height tfh;
	titleFont.GetHeight(&tfh);
	float lineStep = (tfh.ascent + tfh.descent + tfh.leading) * kTitleLineHeight;
	float titleY = ty + tfh.ascent;
	for (size_t i = 0; i < fTitleLines.size(); i++) {
		DrawString(fTitleLines[i].String(), BPoint(titleX, titleY));
		titleY += lineStep;
	}

	// ── Sub-article rows ──
	BFont subFont;
	subFont.SetSize(kSubFontSize);
	font_height subFh;
	subFont.GetHeight(&subFh);
	float subLineHeight =
		(subFh.ascent + subFh.descent + subFh.leading) * kSubLineHeight + 2 * kSubPaddingV;

	float sy = fTopAreaBottom;
	for (size_t i = 0; i < fData.subs.size(); i++) {
		SetHighColor(kDivider);
		StrokeLine(BPoint(0, sy), BPoint(bounds.right, sy));

		SetFont(&subFont);
		SetHighColor((int)i == fHoveringSubIndex ? kAccent : kSubText);
		BString line = TruncateWithEllipsis(
			fData.subs[i].title, subFont, kCardWidth - 2 * kSubPaddingH);
		DrawString(line.String(), BPoint(kSubPaddingH, sy + kSubPaddingV + subFh.ascent));

		sy += subLineHeight;
	}
}

void CardView::MouseDown(BPoint where) {
	BRect topRect(0, fHeaderBottom, Bounds().Width(), fTopAreaBottom);
	if (topRect.Contains(where) && !fData.topUrl.IsEmpty()) {
		UrlOpener::Open(fData.topUrl);
		return;
	}

	BFont subFont;
	subFont.SetSize(kSubFontSize);
	font_height subFh;
	subFont.GetHeight(&subFh);
	float subLineHeight =
		(subFh.ascent + subFh.descent + subFh.leading) * kSubLineHeight + 2 * kSubPaddingV;

	float sy = fTopAreaBottom;
	for (size_t i = 0; i < fData.subs.size(); i++) {
		BRect rowRect(0, sy, Bounds().Width(), sy + subLineHeight);
		if (rowRect.Contains(where)) {
			UrlOpener::Open(fData.subs[i].url);
			return;
		}
		sy += subLineHeight;
	}
}

void CardView::MouseMoved(BPoint where, uint32 code, const BMessage* dragMessage) {
	bool newHoverTop = false;
	int newHoverSub = -1;

	if (code != B_EXITED_VIEW) {
		BRect topRect(0, fHeaderBottom, Bounds().Width(), fTopAreaBottom);
		newHoverTop = topRect.Contains(where);

		if (!newHoverTop) {
			BFont subFont;
			subFont.SetSize(kSubFontSize);
			font_height subFh;
			subFont.GetHeight(&subFh);
			float subLineHeight =
				(subFh.ascent + subFh.descent + subFh.leading) * kSubLineHeight
				+ 2 * kSubPaddingV;
			float sy = fTopAreaBottom;
			for (size_t i = 0; i < fData.subs.size(); i++) {
				if (BRect(0, sy, Bounds().Width(), sy + subLineHeight).Contains(where)) {
					newHoverSub = (int)i;
					break;
				}
				sy += subLineHeight;
			}
		}
	}

	if (newHoverTop != fHoveringTop || newHoverSub != fHoveringSubIndex) {
		fHoveringTop = newHoverTop;
		fHoveringSubIndex = newHoverSub;
		Invalidate();
	}
}

void CardView::MessageReceived(BMessage* message) {
	if (message->what != kMsgImageLoaded) {
		BView::MessageReceived(message);
		return;
	}

	BString url;
	message->FindString("url", &url);
	bool success = false;
	message->FindBool("success", &success);

	if (url == fData.thumbUrl) {
		if (success) {
			BBitmap* bitmap = NULL;
			if (message->FindPointer("bitmap", (void**)&bitmap) == B_OK) {
				delete fThumbBitmap;
				fThumbBitmap = bitmap;
			}
		} else {
			fThumbFailed = true;
		}
		Invalidate();
	} else if (url.IFindFirst("s2/favicons") >= 0 && !fFaviconBitmap) {
		if (success) {
			BBitmap* bitmap = NULL;
			if (message->FindPointer("bitmap", (void**)&bitmap) == B_OK) {
				delete fFaviconBitmap;
				fFaviconBitmap = bitmap;
			}
		} else {
			fFaviconFailed = true;
		}
		Invalidate();
	}
}
