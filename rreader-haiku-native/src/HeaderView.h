// HeaderView.h -- the accent-colored header bar: "news.coroke.net" logo on
// the left, Tech / Top News / Economy tab buttons, matching rreader-web's
// <header>/.header-inner/.logo/.tab-nav CSS.
#ifndef NEWS_COROKE_HEADER_VIEW_H
#define NEWS_COROKE_HEADER_VIEW_H

#include <String.h>
#include <View.h>
#include <vector>

// Sent to the header's target when a tab is clicked. Field: "key" (string).
extern const uint32 kMsgTabSelected;

class HeaderView : public BView {
public:
	HeaderView(BRect frame);

	// Replaces the tab list (key + display title, in the order they should
	// appear) and picks `activeKey` as selected.
	void SetTabs(const std::vector<BString>& keys, const std::vector<BString>& titles,
		const BString& activeKey);
	void SetActiveTab(const BString& key);

	void Draw(BRect updateRect) override;
	void MouseDown(BPoint where) override;
	void FrameResized(float width, float height) override;

private:
	struct Tab {
		BString key;
		BString title;
		BRect rect;
	};

	void LayoutTabs();

	std::vector<Tab> fTabs;
	BString fActiveKey;
};

#endif // NEWS_COROKE_HEADER_VIEW_H
