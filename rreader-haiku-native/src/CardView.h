// CardView.h -- draws one source's card: favicon + source + date header,
// top story (thumbnail + title), and a list of sub-article links. Mirrors
// rreader-web's .group-card / .group-header / .group-top / .group-sub CSS
// (see generate.py) as closely as Haiku's Interface Kit drawing allows.
// Fixed width (NewsMetrics::kCardWidth); height is computed from content
// in RecomputeHeight() and set via ResizeTo before FlowLayoutView ever
// positions it.
#ifndef NEWS_COROKE_CARD_VIEW_H
#define NEWS_COROKE_CARD_VIEW_H

#include <Bitmap.h>
#include <Font.h>
#include <Message.h>
#include <View.h>
#include <vector>

#include "NewsData.h"

class CardView : public BView {
public:
	CardView(BRect frame, const SourceCard& card);
	virtual ~CardView();

	void AttachedToWindow() override;
	void Draw(BRect updateRect) override;
	void MouseDown(BPoint where) override;
	void MouseMoved(BPoint where, uint32 code, const BMessage* dragMessage) override;
	void MessageReceived(BMessage* message) override;

private:
	struct ClickRegion {
		BRect rect;
		BString url;
	};

	void RecomputeHeight();
	// Wraps `text` in `font` to fit `maxWidth`, appending lines as it goes.
	// Used for the (possibly multi-line) top title.
	std::vector<BString> WrapText(const BString& text, const BFont& font, float maxWidth) const;
	// Truncates `text` with an ellipsis to fit `maxWidth` in `font` -- used
	// for the single-line sub-article rows (CSS: text-overflow: ellipsis).
	BString TruncateWithEllipsis(const BString& text, const BFont& font, float maxWidth) const;

	SourceCard fData;
	std::vector<BString> fTitleLines;
	std::vector<ClickRegion> fClickRegions;
	float fHeaderBottom;
	float fTopAreaBottom;

	BBitmap* fThumbBitmap;
	BBitmap* fFaviconBitmap;
	bool fThumbFailed;
	bool fFaviconFailed;

	bool fHoveringTop;
	int fHoveringSubIndex; // -1 if none
};

#endif // NEWS_COROKE_CARD_VIEW_H
