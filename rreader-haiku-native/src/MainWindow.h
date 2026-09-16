// MainWindow.h -- top-level window: HeaderView (logo + tabs) over a
// BScrollView containing the FlowLayoutView (card grid). Owns the fetch ->
// parse -> render pipeline for https://news.coroke.net/.
#ifndef NEWS_COROKE_MAIN_WINDOW_H
#define NEWS_COROKE_MAIN_WINDOW_H

#include <Message.h>
#include <ScrollView.h>
#include <String.h>
#include <StringView.h>
#include <Window.h>
#include <vector>

#include "FlowLayoutView.h"
#include "HeaderView.h"
#include "NewsData.h"

class MainWindow : public BWindow {
public:
	MainWindow();

	void MessageReceived(BMessage* message) override;
	bool QuitRequested() override;
	void FrameResized(float width, float height) override;

private:
	void StartFetch();
	void HandleFetchResult(BMessage* message);
	void ShowCategory(const BString& key);
	void ShowStatus(const char* text);
	void HideStatus();

	HeaderView* fHeader;
	BScrollView* fScrollView;
	FlowLayoutView* fFlowView;
	BStringView* fStatusView; // centered "Loading..." / error text, shown when there's no data yet
	bool fStatusHidden;

	std::vector<Category> fCategories;
	BString fCurrentCategory;
};

#endif // NEWS_COROKE_MAIN_WINDOW_H
