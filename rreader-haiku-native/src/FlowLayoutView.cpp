#include "FlowLayoutView.h"

#include <ScrollBar.h>

#include <algorithm>
#include <cmath>

#include <utility>

#include "BriefView.h"
#include "Colors.h"
#include "LinkSource.h"
#include "UrlOpener.h"

FlowLayoutView::FlowLayoutView(BRect frame, const char* name)
	: BView(frame, name, B_FOLLOW_ALL_SIDES,
		  B_WILL_DRAW | B_FRAME_EVENTS | B_NAVIGABLE),
	  fBrief(NULL),
	  fContentHeight(0),
	  fSelectedView(-1),
	  fSelectedLink(-1),
	  fRelayouting(false) {
	SetViewColor(NewsColors::kPageBackground);
}

FlowLayoutView::~FlowLayoutView() {
}

void FlowLayoutView::ClearCards() {
	fCards.clear();
	fBrief = NULL;
	fContentHeight = 0;
	fSelectedView = -1;
	fSelectedLink = -1;
}

void FlowLayoutView::SetBrief(BriefView* brief) {
	fBrief = brief;
	if (brief != NULL && brief->Parent() != this)
		AddChild(brief);
}

void FlowLayoutView::AddCard(BView* card) {
	if (!card->IsHidden())
		card->Hide(); // avoid drawing at a stale (0,0) position before Relayout runs
	if (card->Parent() != this)
		AddChild(card);
	fCards.push_back(card);
}

float FlowLayoutView::VisibleHeight() const {
	return Bounds().Height();
}

void FlowLayoutView::Relayout() {
	// ResizeTo below triggers FrameResized, which calls back in here; without
	// this guard the two ping-pong forever over a sub-pixel height difference.
	if (fRelayouting)
		return;
	fRelayouting = true;

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

	if (fBrief != NULL) {
		y += NewsMetrics::kBriefMarginTop;
		fBrief->SetWidth(gridWidth);
		fBrief->MoveTo(leftMargin, y);
		y += fBrief->Bounds().Height() + NewsMetrics::kBriefMarginBottom;
	}

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

	// The view stays the size of the scroll frame; Haiku doesn't derive the
	// scroll range from the content, so it has to be set by hand whenever the
	// content height changes.
	float visibleHeight = VisibleHeight();
	BScrollBar* scrollBar = ScrollBar(B_VERTICAL);
	if (scrollBar != NULL) {
		scrollBar->SetRange(0, std::max(0.0f, fContentHeight - visibleHeight));
		scrollBar->SetProportion(
			fContentHeight > 0 ? std::min(1.0f, visibleHeight / fContentHeight) : 1.0f);
		scrollBar->SetSteps(24, visibleHeight);
	}

	fRelayouting = false;
	Invalidate();
}

void FlowLayoutView::FrameResized(float width, float height) {
	BView::FrameResized(width, height);
	Relayout();
}

// The views holding links, in reading order: the brief box first, then the
// cards as laid out.
std::vector<BView*> FlowLayoutView::LinkViews() const {
	std::vector<BView*> views;
	if (fBrief != NULL)
		views.push_back(fBrief);
	views.insert(views.end(), fCards.begin(), fCards.end());
	return views;
}

void FlowLayoutView::MoveSelection(int delta) {
	std::vector<BView*> views = LinkViews();
	if (views.empty())
		return;

	// Flatten (view, link) pairs so a single index can walk the whole page.
	std::vector<std::pair<int, int>> links;
	for (size_t v = 0; v < views.size(); v++) {
		LinkSource* source = dynamic_cast<LinkSource*>(views[v]);
		for (int l = 0; source != NULL && l < source->LinkCount(); l++)
			links.push_back(std::make_pair((int)v, l));
	}
	if (links.empty())
		return;

	int current = -1;
	for (size_t i = 0; i < links.size(); i++) {
		if (links[i].first == fSelectedView && links[i].second == fSelectedLink) {
			current = (int)i;
			break;
		}
	}

	int next = current < 0 ? (delta > 0 ? 0 : (int)links.size() - 1) : current + delta;
	next = std::max(0, std::min((int)links.size() - 1, next));

	for (BView* view : views) {
		LinkSource* source = dynamic_cast<LinkSource*>(view);
		if (source != NULL)
			source->SetSelectedLink(-1);
	}

	fSelectedView = links[next].first;
	fSelectedLink = links[next].second;
	LinkSource* selected = dynamic_cast<LinkSource*>(views[fSelectedView]);
	selected->SetSelectedLink(fSelectedLink);
	ScrollToSelection();
}

void FlowLayoutView::ScrollToSelection() {
	std::vector<BView*> views = LinkViews();
	if (fSelectedView < 0 || fSelectedView >= (int)views.size())
		return;
	LinkSource* source = dynamic_cast<LinkSource*>(views[fSelectedView]);
	if (source == NULL)
		return;

	BRect frame = source->LinkFrame(fSelectedLink);
	frame.OffsetBy(views[fSelectedView]->Frame().LeftTop());
	float visibleTop = Bounds().top;
	float visibleHeight = VisibleHeight();

	if (frame.top < visibleTop)
		ScrollTo(0, std::max(0.0f, frame.top - NewsMetrics::kGridGapV));
	else if (frame.bottom > visibleTop + visibleHeight)
		ScrollTo(0, frame.bottom - visibleHeight + NewsMetrics::kGridGapV);
}

void FlowLayoutView::ActivateSelection() {
	std::vector<BView*> views = LinkViews();
	if (fSelectedView < 0 || fSelectedView >= (int)views.size())
		return;
	LinkSource* source = dynamic_cast<LinkSource*>(views[fSelectedView]);
	if (source == NULL)
		return;
	BString url = source->LinkUrl(fSelectedLink);
	if (!url.IsEmpty())
		UrlOpener::Open(url);
}

void FlowLayoutView::KeyDown(const char* bytes, int32 numBytes) {
	if (numBytes < 1) {
		BView::KeyDown(bytes, numBytes);
		return;
	}

	switch (bytes[0]) {
		case B_UP_ARROW:
		case B_LEFT_ARROW:
			MoveSelection(-1);
			return;
		case B_DOWN_ARROW:
		case B_RIGHT_ARROW:
			MoveSelection(1);
			return;
		case B_ENTER:
		case B_SPACE:
			ActivateSelection();
			return;
		case B_PAGE_UP:
			MoveSelection(-8);
			return;
		case B_PAGE_DOWN:
			MoveSelection(8);
			return;
	}

	BView::KeyDown(bytes, numBytes);
}

void FlowLayoutView::MakeFocus(bool focus) {
	BView::MakeFocus(focus);
	Invalidate();
}
