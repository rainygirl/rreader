// NewsData.h -- plain data model parsed out of news.coroke.net's HTML.
// Mirrors the structure generate.py emits per <div class="group-card">.
#ifndef NEWS_COROKE_DATA_H
#define NEWS_COROKE_DATA_H

#include <String.h>
#include <vector>

// One sub-article link inside a card (every article after the top story
// from the same source, i.e. generate.py's <a class="group-sub">).
struct SubArticle {
	BString title;
	BString url;
};

// One <div class="group-card">: a source's top story plus its sub-articles.
struct SourceCard {
	BString source;      // .group-source
	BString date;        // .group-date
	BString topTitle;     // .group-top-title
	BString topUrl;       // .group-top href
	BString thumbUrl;      // .group-thumb src, empty if none
	BString faviconDomain;  // domain used to build the Google favicon URL
	std::vector<SubArticle> subs;
};

// One <li> of <section class="brief">: a one-sentence headline summary.
struct BriefItem {
	BString text;
	BString url;
	BString source;
};

// One <section data-cat="..." data-view="card">: a whole tab's worth of cards.
struct Category {
	BString key;    // "tech" / "news" / "economy"
	BString title;  // "Tech" / "Top News" / "Economy"
	std::vector<BriefItem> brief;
	std::vector<SourceCard> cards;
};

#endif // NEWS_COROKE_DATA_H
