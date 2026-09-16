// BriefView.h -- the "3 key headlines" box above the card grid
// (generate.py's .brief / .brief-list CSS).
#ifndef NEWS_COROKE_BRIEF_VIEW_H
#define NEWS_COROKE_BRIEF_VIEW_H

#include <Font.h>
#include <View.h>
#include <vector>

#include "LinkSource.h"
#include "NewsData.h"

class BriefView : public BView, public LinkSource {
public:
	explicit BriefView(const std::vector<BriefItem>& items);

	int LinkCount() const override;
	BString LinkUrl(int index) const override;
	BRect LinkFrame(int index) const override;
	void SetSelectedLink(int index) override;

	// Re-wraps text for `width` and resizes to the resulting height.
	void SetWidth(float width);

	void Draw(BRect updateRect) override;
	void MessageReceived(BMessage* message) override;
	void MouseDown(BPoint where) override;
	void MouseMoved(BPoint where, uint32 code, const BMessage* dragMessage) override;

private:
	struct Layout {
		std::vector<BString> lines;
		float sourceX;     // x of the source label, relative to text start
		int sourceLine;    // line index the source label sits on
		float top;
		float bottom;
	};

	int ItemAt(BPoint where) const;

	std::vector<BriefItem> fItems;
	std::vector<Layout> fLayouts;
	BFont fTextFont;
	BFont fSourceFont;
	BFont fBadgeFont;
	int fHoverIndex;
	int fSelectedLink; // -1 if none
};

#endif // NEWS_COROKE_BRIEF_VIEW_H
