// HeaderView.h -- the accent-colored header bar: "news.coroke.net" logo on
// the left, Tech / Top News / Economy tab buttons, matching rreader-web's
// <header>/.header-inner/.logo/.tab-nav CSS.
#ifndef NEWS_COROKE_HEADER_VIEW_H
#define NEWS_COROKE_HEADER_VIEW_H

#include <String.h>
#include <View.h>
#include <vector>

// Sent to the window when a tab is chosen. Fields: "key" (string),
// "keyboard" (bool, true when chosen with the arrow keys so focus stays in
// the tab bar).
inline constexpr uint32 kMsgTabSelected = 'tabS';
// Sent to the window when Down/Enter leaves the tab bar for the content.
inline constexpr uint32 kMsgFocusContent = 'fcsC';

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
	// Left/Right switch categories, Down/Enter return to the content.
	void KeyDown(const char* bytes, int32 numBytes) override;
	void MakeFocus(bool focus) override;
	void FrameResized(float width, float height) override;

private:
	struct Tab {
		BString key;
		BString title;
		BRect rect;
	};

	void LayoutTabs();
	void SelectTab(size_t index, bool keyboard);

	std::vector<Tab> fTabs;
	BString fActiveKey;
};

#endif // NEWS_COROKE_HEADER_VIEW_H
