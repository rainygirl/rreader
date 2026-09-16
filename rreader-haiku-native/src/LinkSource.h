// LinkSource.h -- implemented by views that contain clickable links
// (CardView, BriefView) so FlowLayoutView can walk every link on the page
// in order for keyboard navigation.
#ifndef NEWS_COROKE_LINK_SOURCE_H
#define NEWS_COROKE_LINK_SOURCE_H

#include <Rect.h>
#include <String.h>

class LinkSource {
public:
	virtual ~LinkSource() {}

	virtual int LinkCount() const = 0;
	virtual BString LinkUrl(int index) const = 0;
	// Link bounds in the view's own coordinates.
	virtual BRect LinkFrame(int index) const = 0;
	// -1 clears the keyboard selection.
	virtual void SetSelectedLink(int index) = 0;
};

#endif // NEWS_COROKE_LINK_SOURCE_H
