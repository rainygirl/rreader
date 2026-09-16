#include "FlowLayoutView.h"

#include <ScrollBar.h>
#include <Window.h>

#include <algorithm>
#include <cmath>

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
	  fSelectedLink(-1) {
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

// Moves the keyboard focus to the nearest link in `direction`, by position
// on screen: up/down stay in the same column, left/right jump to the
// neighboring column's link at the closest height.
void FlowLayoutView::MoveSelection(Direction direction) {
	std::vector<BView*> views = LinkViews();

	struct Link {
		int view;
		int index;
		BRect frame;
	};
	std::vector<Link> links;
	for (size_t v = 0; v < views.size(); v++) {
		LinkSource* source = dynamic_cast<LinkSource*>(views[v]);
		for (int l = 0; source != NULL && l < source->LinkCount(); l++) {
			BRect frame = source->LinkFrame(l);
			frame.OffsetBy(views[v]->Frame().LeftTop());
			links.push_back(Link{(int)v, l, frame});
		}
	}
	if (links.empty())
		return;

	int current = -1;
	for (size_t i = 0; i < links.size(); i++) {
		if (links[i].view == fSelectedView && links[i].index == fSelectedLink)
			current = (int)i;
	}

	int next = -1;
	if (current < 0) {
		next = 0;
	} else {
		const BRect& from = links[current].frame;
		const float kSlop = 2.0f;
		float bestPrimary = 0, bestSecondary = 0;
		for (size_t i = 0; i < links.size(); i++) {
			if ((int)i == current)
				continue;
			const BRect& to = links[i].frame;
			bool overlapsH = to.left < from.right - kSlop && to.right > from.left + kSlop;
			float primary, secondary;
			switch (direction) {
				case kDown:
					if (!overlapsH || to.top < from.bottom - kSlop)
						continue;
					primary = to.top - from.bottom;
					secondary = fabs(to.left - from.left);
					break;
				case kUp:
					if (!overlapsH || to.bottom > from.top + kSlop)
						continue;
					primary = from.top - to.bottom;
					secondary = fabs(to.left - from.left);
					break;
				case kRight:
					if (to.left < from.right - kSlop)
						continue;
					primary = to.left - from.right;
					secondary = fabs((to.top + to.bottom) - (from.top + from.bottom)) / 2;
					break;
				case kLeft:
				default:
					if (to.right > from.left + kSlop)
						continue;
					primary = from.left - to.right;
					secondary = fabs((to.top + to.bottom) - (from.top + from.bottom)) / 2;
					break;
			}
			if (next < 0 || primary < bestPrimary - kSlop
				|| (fabs(primary - bestPrimary) <= kSlop && secondary < bestSecondary)) {
				next = (int)i;
				bestPrimary = primary;
				bestSecondary = secondary;
			}
		}
		if (next < 0) {
			if (direction == kUp && Window() != NULL)
				Window()->PostMessage(kMsgFocusTabs);
			return;
		}
		if (LinkSource* old = dynamic_cast<LinkSource*>(views[fSelectedView]))
			old->SetSelectedLink(-1);
	}

	fSelectedView = links[next].view;
	fSelectedLink = links[next].index;
	dynamic_cast<LinkSource*>(views[fSelectedView])->SetSelectedLink(fSelectedLink);
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
			MoveSelection(kUp);
			return;
		case B_DOWN_ARROW:
			MoveSelection(kDown);
			return;
		case B_LEFT_ARROW:
			MoveSelection(kLeft);
			return;
		case B_RIGHT_ARROW:
			MoveSelection(kRight);
			return;
		case B_ENTER:
		case B_SPACE:
			ActivateSelection();
			return;
		case B_PAGE_UP:
			for (int i = 0; i < 8; i++)
				MoveSelection(kUp);
			return;
		case B_PAGE_DOWN:
			for (int i = 0; i < 8; i++)
				MoveSelection(kDown);
			return;
	}

	BView::KeyDown(bytes, numBytes);
}

void FlowLayoutView::ClearSelection() {
	std::vector<BView*> views = LinkViews();
	if (fSelectedView >= 0 && fSelectedView < (int)views.size()) {
		if (LinkSource* source = dynamic_cast<LinkSource*>(views[fSelectedView]))
			source->SetSelectedLink(-1);
	}
	fSelectedView = -1;
	fSelectedLink = -1;
}

void FlowLayoutView::FocusFirstLink() {
	MakeFocus(true);
	ClearSelection();
	MoveSelection(kDown);
}

void FlowLayoutView::MakeFocus(bool focus) {
	BView::MakeFocus(focus);
	Invalidate();
}
