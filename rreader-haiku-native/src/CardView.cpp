#include "CardView.h"

#include <Font.h>
#include <Message.h>
#include <Picture.h>
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

// CSS line boxes are font-size * line-height, with the glyph box centered
// in them -- not (ascent + descent + leading) * line-height.
float LineBoxBaseline(float lineTop, float lineHeight, const BFont& font) {
	font_height fh;
	font.GetHeight(&fh);
	return lineTop + (lineHeight - (fh.ascent + fh.descent)) / 2 + fh.ascent;
}
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
	  fSelectedLink(-1),
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

// CSS `object-fit: cover` + `border-radius: 6px`: crop the larger dimension
// to a square instead of squashing the image, and round the corners by
// clipping to a rounded rect.
void CardView::DrawThumb(BRect dest) {
	BRect source = fThumbBitmap->Bounds();
	float side = std::min(source.Width(), source.Height());
	source.left += (source.Width() - side) / 2;
	source.top += (source.Height() - side) / 2;
	source.right = source.left + side;
	source.bottom = source.top + side;

	BPicture clip;
	BeginPicture(&clip);
	FillRoundRect(dest, kThumbCornerRadius, kThumbCornerRadius);
	EndPicture();

	PushState();
	ClipToPicture(&clip);
	DrawBitmap(fThumbBitmap, source, dest);
	PopState();
}

void CardView::RecomputeHeight() {
	float innerWidth = kCardWidth - kTopPaddingLeft - kTopPaddingRight;
	if (!fData.thumbUrl.IsEmpty())
		innerWidth -= (kThumbSize + kTopInnerGap);

	BFont titleFont;
	titleFont.SetSize(fData.thumbUrl.IsEmpty() ? kTitleFontSize : kTitleFontSizeWithThumb);
	titleFont.SetFace(fData.thumbUrl.IsEmpty() ? B_REGULAR_FACE : B_BOLD_FACE);

	fTitleLines = WrapText(fData.topTitle, titleFont, innerWidth);

	float titleLineHeight = titleFont.Size() * kTitleLineHeight;

	fHeaderBottom = kCardHeaderPaddingTop + kFaviconSize + kCardHeaderPaddingBottom;

	float topInnerHeight = std::max(
		fData.thumbUrl.IsEmpty() ? 0.0f : kThumbSize, fTitleLines.size() * titleLineHeight);
	fTopAreaBottom = fHeaderBottom + kTopPaddingTop + topInnerHeight + kTopPaddingBottom;

	float subLineHeight = kSubFontSize * kSubLineHeight + 2 * kSubPaddingV;

	float total = fTopAreaBottom + fData.subs.size() * subLineHeight + kCardBottomPadding;
	ResizeTo(kCardWidth, total);
}

void CardView::Draw(BRect updateRect) {
	BRect bounds = Bounds();
	SetDrawingMode(B_OP_OVER);

	SetHighColor(kCardBackground);
	FillRoundRect(bounds, kCardCornerRadius, kCardCornerRadius, B_SOLID_HIGH);
	SetHighColor(fHoveringTop ? kCardBorderHover : kCardBorder);
	StrokeRoundRect(bounds, kCardCornerRadius, kCardCornerRadius);

	// .group-top:hover / .group-sub:hover background; the keyboard focus gets
	// a stronger tint instead of a text color change.
	int hovered = fHoveringTop ? 0 : (fHoveringSubIndex >= 0 ? fHoveringSubIndex + 1 : -1);
	if (hovered >= 0 && hovered != fSelectedLink) {
		SetHighColor(kHoverBackground);
		FillRect(LinkFrame(hovered).InsetByCopy(1, 0) & bounds.InsetByCopy(1, 1));
	}
	if (fSelectedLink >= 0) {
		SetHighColor(kFocusBackground);
		FillRect(LinkFrame(fSelectedLink).InsetByCopy(1, 0) & bounds.InsetByCopy(1, 1));
	}

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
		float thumbTop = ty + std::max(0.0f,
			(fTopAreaBottom - kTopPaddingBottom - ty - kThumbSize) / 2);
		DrawThumb(BRect(tx, thumbTop, tx + kThumbSize - 1, thumbTop + kThumbSize - 1));
		titleX = tx + kThumbSize + kTopInnerGap;
	} else if (!fData.thumbUrl.IsEmpty() && !fThumbFailed) {
		titleX = tx + kThumbSize + kTopInnerGap; // reserve space while still loading
	}

	BFont titleFont;
	titleFont.SetSize(fData.thumbUrl.IsEmpty() ? kTitleFontSize : kTitleFontSizeWithThumb);
	titleFont.SetFace(fData.thumbUrl.IsEmpty() ? B_REGULAR_FACE : B_BOLD_FACE);
	SetFont(&titleFont);
	SetHighColor(fHoveringTop ? kAccent : kTitleText);
	float lineStep = titleFont.Size() * kTitleLineHeight;
	// align-items: center -- the shorter of thumbnail/title is centered
	// against the taller one.
	float titleBlockHeight = fTitleLines.size() * lineStep;
	float titleTop = ty + std::max(0.0f, (fTopAreaBottom - kTopPaddingBottom - ty
		- titleBlockHeight) / 2);
	for (size_t i = 0; i < fTitleLines.size(); i++) {
		DrawString(fTitleLines[i].String(),
			BPoint(titleX, LineBoxBaseline(titleTop + i * lineStep, lineStep, titleFont)));
	}

	// ── Sub-article rows ──
	BFont subFont;
	subFont.SetSize(kSubFontSize);
	float subLineHeight = kSubFontSize * kSubLineHeight + 2 * kSubPaddingV;

	float sy = fTopAreaBottom;
	for (size_t i = 0; i < fData.subs.size(); i++) {
		SetHighColor(kDivider);
		StrokeLine(BPoint(0, sy), BPoint(bounds.right, sy));

		SetFont(&subFont);
		SetHighColor((int)i == fHoveringSubIndex ? kAccent : kSubText);
		BString line = TruncateWithEllipsis(
			fData.subs[i].title, subFont, kCardWidth - 2 * kSubPaddingH);
		DrawString(line.String(),
			BPoint(kSubPaddingH, LineBoxBaseline(sy, subLineHeight, subFont)));

		sy += subLineHeight;
	}
}

int CardView::LinkCount() const {
	return 1 + (int)fData.subs.size();
}

BString CardView::LinkUrl(int index) const {
	if (index == 0)
		return fData.topUrl;
	return fData.subs[index - 1].url;
}

BRect CardView::LinkFrame(int index) const {
	if (index == 0)
		return BRect(0, fHeaderBottom, Bounds().Width(), fTopAreaBottom);
	float height = kSubFontSize * kSubLineHeight + 2 * kSubPaddingV;
	float top = fTopAreaBottom + (index - 1) * height;
	return BRect(0, top, Bounds().Width(), top + height);
}

void CardView::SetSelectedLink(int index) {
	if (index == fSelectedLink)
		return;
	fSelectedLink = index;
	Invalidate();
}

void CardView::MouseDown(BPoint where) {
	for (int i = 0; i < LinkCount(); i++) {
		if (LinkFrame(i).Contains(where) && !LinkUrl(i).IsEmpty()) {
			UrlOpener::Open(LinkUrl(i));
			return;
		}
	}
}

void CardView::MouseMoved(BPoint where, uint32 code, const BMessage* dragMessage) {
	bool newHoverTop = false;
	int newHoverSub = -1;

	if (code != B_EXITED_VIEW) {
		for (int i = 0; i < LinkCount(); i++) {
			if (!LinkFrame(i).Contains(where))
				continue;
			if (i == 0)
				newHoverTop = true;
			else
				newHoverSub = i - 1;
			break;
		}
	}

	if (newHoverTop != fHoveringTop || newHoverSub != fHoveringSubIndex) {
		fHoveringTop = newHoverTop;
		fHoveringSubIndex = newHoverSub;
		Invalidate();
	}
}

void CardView::MessageReceived(BMessage* message) {
	// Only the scrolled view itself owns a scroll bar, so the wheel has to be
	// handed up or it does nothing while the pointer is over a card.
	if (message->what == B_MOUSE_WHEEL_CHANGED && Parent() != NULL) {
		Parent()->MessageReceived(message);
		return;
	}

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
