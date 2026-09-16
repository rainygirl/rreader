#include "MainWindow.h"

#include <Application.h>
#include <Font.h>
#include <Message.h>
#include <Screen.h>
#include <ScrollBar.h>

#include "BriefView.h"
#include "CardView.h"
#include "Colors.h"
#include "ImageLoader.h"
#include "NewsFetcher.h"
#include "NewsParser.h"

using namespace NewsColors;
using namespace NewsMetrics;

namespace {
const char* kNewsUrl = "https://news.coroke.net/";
const float kWindowWidth = 1040.0f;
const float kWindowHeight = 760.0f;
} // namespace

MainWindow::MainWindow()
	: BWindow(BRect(80, 80, 80 + kWindowWidth, 80 + kWindowHeight), "news.coroke.net",
		  B_TITLED_WINDOW, B_ASYNCHRONOUS_CONTROLS | B_QUIT_ON_WINDOW_CLOSE),
	  fHeader(NULL),
	  fScrollView(NULL),
	  fFlowView(NULL),
	  fStatusView(NULL),
	  fStatusHidden(false) {
	// Keep the whole window on screen, or keyboard focus can land below the
	// visible part of the display.
	BRect screen = BScreen(this).Frame();
	float maxHeight = screen.bottom - Frame().top - 8;
	if (Frame().Height() > maxHeight)
		ResizeTo(Frame().Width(), maxHeight);
	BRect bounds = Bounds();

	fHeader = new HeaderView(BRect(0, 0, bounds.Width(), kHeaderHeight - 1));
	AddChild(fHeader);

	// The scroll view sizes itself (and its scroll bar) around the target's
	// frame, so the flow view has to start out at its real size.
	BRect flowFrame(0, kHeaderHeight, bounds.Width() - B_V_SCROLL_BAR_WIDTH, bounds.Height());
	fFlowView = new FlowLayoutView(flowFrame, "flow");

	fScrollView = new BScrollView(
		"scroll", fFlowView, B_FOLLOW_LEFT_RIGHT | B_FOLLOW_TOP_BOTTOM, 0, false, true);
	AddChild(fScrollView);

	BFont statusFont;
	statusFont.SetSize(15.0f);
	fStatusView = new BStringView(
		BRect(0, 0, bounds.Width(), 40), "status", "news.coroke.net 불러오는 중...");
	fStatusView->SetFont(&statusFont);
	fStatusView->SetAlignment(B_ALIGN_CENTER);
	fStatusView->SetHighColor(kMutedText);
	fStatusView->SetViewColor(kPageBackground);
	fStatusView->MoveTo(0, kHeaderHeight + 60);
	fStatusView->ResizeTo(bounds.Width(), 40);
	AddChild(fStatusView);

	StartFetch();
}

void MainWindow::StartFetch() {
	ShowStatus("news.coroke.net 불러오는 중...");
	NewsFetcher::FetchAsync(kNewsUrl, BMessenger(this));
}

// BView::Show()/Hide() are counted, and IsHidden() is true for every view
// while the window itself hasn't been shown yet -- so track it ourselves.
void MainWindow::ShowStatus(const char* text) {
	fStatusView->SetText(text);
	if (fStatusHidden) {
		fStatusView->Show();
		fStatusHidden = false;
	}
}

void MainWindow::HideStatus() {
	if (!fStatusHidden) {
		fStatusView->Hide();
		fStatusHidden = true;
	}
}

void MainWindow::MessageReceived(BMessage* message) {
	switch (message->what) {
		case kMsgNewsFetched:
			HandleFetchResult(message);
			break;
		case kMsgTabSelected: {
			BString key;
			bool keyboard = false;
			message->FindBool("keyboard", &keyboard);
			if (message->FindString("key", &key) == B_OK)
				ShowCategory(key, !keyboard);
			break;
		}
		case kMsgFocusTabs:
			fFlowView->ClearSelection();
			fHeader->MakeFocus(true);
			break;
		case kMsgFocusContent:
			fFlowView->FocusFirstLink();
			break;
		default:
			BWindow::MessageReceived(message);
	}
}

void MainWindow::HandleFetchResult(BMessage* message) {
	bool success = false;
	message->FindBool("success", &success);

	if (!success) {
		BString error;
		message->FindString("error", &error);
		BString text("news.coroke.net을 불러오지 못했습니다");
		if (!error.IsEmpty())
			text << " (" << error << ")";
		ShowStatus(text.String());
		return;
	}

	BString html;
	message->FindString("html", &html);
	fCategories = NewsParser::Parse(html);

	if (fCategories.empty()) {
		ShowStatus("페이지 형식을 인식하지 못했습니다. rreader-web의 카드 HTML 구조가 바뀌었을 수 있습니다.");
		return;
	}

	std::vector<BString> keys, titles;
	for (size_t i = 0; i < fCategories.size(); i++) {
		keys.push_back(fCategories[i].key);
		titles.push_back(fCategories[i].title);
	}
	fHeader->SetTabs(keys, titles, fCategories[0].key);

	ShowCategory(fCategories[0].key);
}

void MainWindow::ShowCategory(const BString& key, bool focusContent) {
	const Category* found = NULL;
	for (size_t i = 0; i < fCategories.size(); i++) {
		if (fCategories[i].key == key) {
			found = &fCategories[i];
			break;
		}
	}
	if (found == NULL)
		return;

	fCurrentCategory = key;
	fHeader->SetActiveTab(key);

	// Remove and delete the previous category's views before building the
	// new set -- FlowLayoutView doesn't own them.
	ImageLoader::CancelPending();
	while (fFlowView->CountChildren() > 0) {
		BView* child = fFlowView->ChildAt(0);
		fFlowView->RemoveChild(child);
		delete child;
	}
	fFlowView->ClearCards();

	if (!found->brief.empty())
		fFlowView->SetBrief(new BriefView(found->brief));

	for (size_t i = 0; i < found->cards.size(); i++) {
		BRect frame(0, 0, kCardWidth, 10);
		CardView* card = new CardView(frame, found->cards[i]);
		fFlowView->AddCard(card);
	}
	fFlowView->ScrollTo(0, 0);
	fFlowView->Relayout();
	if (focusContent)
		fFlowView->MakeFocus(true);

	if (found->cards.empty())
		ShowStatus("이 카테고리에는 표시할 기사가 없습니다.");
	else
		HideStatus();
}

void MainWindow::FrameResized(float width, float height) {
	BWindow::FrameResized(width, height);

	fHeader->ResizeTo(width, kHeaderHeight - 1);
	fFlowView->Relayout();

	fStatusView->ResizeTo(width, 40);
}

bool MainWindow::QuitRequested() {
	be_app->PostMessage(B_QUIT_REQUESTED);
	return true;
}
