// FlowLayoutView.h -- a scrollable container that lays out fixed-width
// child views in however many columns fit the current width, reflowing on
// resize. This is the native equivalent of rreader-web's CSS
// `.cards { display: grid; grid-template-columns: repeat(3, 1fr); }` plus
// its @media breakpoints, generalized: instead of 3 fixed breakpoints, the
// column count is always `floor(width / (cardWidth + gap))`, so a wide
// enough native window naturally gets 4, 5, 6+ columns instead of capping
// at 3 the way the (max-width: 1200px) web layout does.
#ifndef NEWS_COROKE_FLOW_LAYOUT_VIEW_H
#define NEWS_COROKE_FLOW_LAYOUT_VIEW_H

#include <View.h>
#include <vector>

// Sent to the window when Up is pressed on the topmost link, so the focus
// can move into the tab bar.
inline constexpr uint32 kMsgFocusTabs = 'fcsT';

class BriefView;

class FlowLayoutView : public BView {
public:
	FlowLayoutView(BRect frame, const char* name);
	virtual ~FlowLayoutView();

	// Removes all child card views and forgets about them (does NOT delete
	// them here -- RemoveChild + the caller's own bookkeeping decide
	// lifetime; MainWindow deletes the old CardViews itself before calling
	// this when switching categories).
	void ClearCards();

	// Adds one fixed-width card view to the flow. Width/height must already
	// be set on `card` (NewsMetrics::kCardWidth x whatever CardView computed
	// for its content); FlowLayoutView only decides X/Y position.
	void AddCard(BView* card);

	// Optional box spanning the grid width above the cards (NULL for none).
	// Added as a child like the cards; ClearCards forgets it too.
	void SetBrief(BriefView* brief);

	// Recomputes the column count for the current width and repositions
	// every child accordingly. Called automatically from FrameResized and
	// after AddCard finishes a batch (see MainWindow::ShowCategory).
	void Relayout();

	void FrameResized(float width, float height) override;
	// Arrow keys move the focus between links by on-screen position;
	// Enter/Space opens the focused one in the browser.
	void KeyDown(const char* bytes, int32 numBytes) override;
	void MakeFocus(bool focus) override;

	// Focuses the view and selects the first link on the page.
	void FocusFirstLink();
	void ClearSelection();

private:
	float VisibleHeight() const;
	std::vector<BView*> LinkViews() const;
	enum Direction { kUp, kDown, kLeft, kRight };
	void MoveSelection(Direction direction);
	void ScrollToSelection();
	void ActivateSelection();

	std::vector<BView*> fCards;
	BriefView* fBrief;
	float fContentHeight; // total height needed, used to size ourselves for BScrollView
	int fSelectedView;    // index into LinkViews(), -1 if none
	int fSelectedLink;    // index within that view's links
};

#endif // NEWS_COROKE_FLOW_LAYOUT_VIEW_H
