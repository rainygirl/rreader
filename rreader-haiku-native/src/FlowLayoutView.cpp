#include "FlowLayoutView.h"

#include <ScrollBar.h>

#include <algorithm>
#include <cmath>

#include "Colors.h"

FlowLayoutView::FlowLayoutView(BRect frame, const char* name)
	: BView(frame, name, B_FOLLOW_LEFT | B_FOLLOW_TOP, B_WILL_DRAW | B_FRAME_EVENTS),
	  fContentHeight(0) {
	SetViewColor(NewsColors::kPageBackground);
}

FlowLayoutView::~FlowLayoutView() {
}

void FlowLayoutView::ClearCards() {
	fCards.clear();
	fContentHeight = 0;
}

void FlowLayoutView::AddCard(BView* card) {
	if (!card->IsHidden())
		card->Hide(); // avoid drawing at a stale (0,0) position before Relayout runs
	if (card->Parent() != this)
		AddChild(card);
	fCards.push_back(card);
}

void FlowLayoutView::Relayout() {
	float width = Bounds().Width();
	float usableWidth = width - 2 * NewsMetrics::kGridPaddingH;

	int columns = static_cast<int>(
		std::floor((usableWidth + NewsMetrics::kGridGapH)
			/ (NewsMetrics::kCardWidth + NewsMetrics::kGridGapH)));
	if (columns < 1)
		columns = 1;

	// Center the grid: with a fixed card width, the columns rarely fill the
	// view exactly, so give the leftover space to the left margin too
	// (matching the web layout's centered `max-width` container).
	float gridWidth =
		columns * NewsMetrics::kCardWidth + (columns - 1) * NewsMetrics::kGridGapH;
	float leftMargin = std::max(
		NewsMetrics::kGridPaddingH, (width - gridWidth) / 2.0f);

	float y = NewsMetrics::kGridPaddingTop;
	float rowHeight = 0;
	int col = 0;

	for (size_t i = 0; i < fCards.size(); i++) {
		BView* card = fCards[i];
		float x = leftMargin + col * (NewsMetrics::kCardWidth + NewsMetrics::kGridGapH);
		card->MoveTo(x, y);
		if (card->IsHidden())
			card->Show();

		rowHeight = std::max(rowHeight, card->Bounds().Height());
		col++;
		if (col >= columns) {
			col = 0;
			y += rowHeight + NewsMetrics::kGridGapV;
			rowHeight = 0;
		}
	}
	if (col != 0)
		y += rowHeight + NewsMetrics::kGridGapV;

	fContentHeight = y + NewsMetrics::kGridPaddingBottom;

	// Resize ourselves so the enclosing BScrollView gets a correct
	// scroll range; keep the current width, only height changes.
	float targetHeight = std::max(fContentHeight, Bounds().Height());
	if (fabs(targetHeight - Bounds().Height()) > 0.5f)
		ResizeTo(width, targetHeight);

	Invalidate();
}

void FlowLayoutView::FrameResized(float width, float height) {
	BView::FrameResized(width, height);
	Relayout();
}
