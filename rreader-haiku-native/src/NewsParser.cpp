#include "NewsParser.h"

#include <cstdio>
#include <string>

namespace {

std::string ToStd(const BString& s) {
	return std::string(s.String(), s.Length());
}

BString ToB(const std::string& s) {
	return BString(s.c_str(), s.size());
}

// Finds the substring between the first occurrence of `open` at/after
// `from` and the following `close`. Returns npos via an empty-out on
// failure and leaves `from` unchanged.
bool FindBetween(const std::string& hay, const std::string& open,
	const std::string& close, size_t from, std::string* out, size_t* endPos) {
	size_t start = hay.find(open, from);
	if (start == std::string::npos)
		return false;
	start += open.size();
	size_t end = hay.find(close, start);
	if (end == std::string::npos)
		return false;
	*out = hay.substr(start, end - start);
	if (endPos != nullptr)
		*endPos = end + close.size();
	return true;
}

// Finds the value of `attr="..."` inside the tag text `tag` (e.g. the
// snippet right after an opening <a or <img up to its closing '>').
bool FindAttr(const std::string& tag, const std::string& attr, std::string* out) {
	std::string needle = attr + "=\"";
	size_t start = tag.find(needle);
	if (start == std::string::npos)
		return false;
	start += needle.size();
	size_t end = tag.find('"', start);
	if (end == std::string::npos)
		return false;
	*out = tag.substr(start, end - start);
	return true;
}

// Returns the byte offset just past the matching closing tag for the
// `<div ...>` that starts at `divOpenStart` (the index of '<'), correctly
// skipping over any nested <div> elements. Returns std::string::npos if
// unbalanced.
size_t FindMatchingDivClose(const std::string& hay, size_t divOpenStart) {
	size_t pos = divOpenStart;
	int depth = 0;
	while (pos < hay.size()) {
		size_t nextOpen = hay.find("<div", pos);
		size_t nextClose = hay.find("</div>", pos);
		if (nextClose == std::string::npos)
			return std::string::npos;
		if (nextOpen != std::string::npos && nextOpen < nextClose) {
			depth++;
			pos = nextOpen + 4;
		} else {
			depth--;
			pos = nextClose + 6;
			if (depth == 0)
				return pos;
		}
	}
	return std::string::npos;
}

std::string StripTags(const std::string& s) {
	std::string out;
	out.reserve(s.size());
	bool inTag = false;
	for (char c : s) {
		if (c == '<')
			inTag = true;
		else if (c == '>')
			inTag = false;
		else if (!inTag)
			out.push_back(c);
	}
	return out;
}

std::string Trim(const std::string& s) {
	size_t a = s.find_first_not_of(" \t\r\n");
	if (a == std::string::npos)
		return "";
	size_t b = s.find_last_not_of(" \t\r\n");
	return s.substr(a, b - a + 1);
}

// The favicon <img> src is
// "https://www.google.com/s2/favicons?domain=DOMAIN&sz=32" -- pull DOMAIN
// back out so CardView can re-derive the same URL (or a different size)
// without having to keep the whole thing around.
std::string ExtractFaviconDomain(const std::string& src) {
	const std::string marker = "domain=";
	size_t start = src.find(marker);
	if (start == std::string::npos)
		return "";
	start += marker.size();
	size_t end = src.find('&', start);
	if (end == std::string::npos)
		end = src.size();
	return src.substr(start, end - start);
}

} // namespace

BString NewsParser::DecodeEntities(const BString& text) {
	std::string s = ToStd(text);
	std::string out;
	out.reserve(s.size());
	for (size_t i = 0; i < s.size();) {
		if (s.compare(i, 5, "&amp;") == 0) {
			out.push_back('&');
			i += 5;
		} else if (s.compare(i, 4, "&lt;") == 0) {
			out.push_back('<');
			i += 4;
		} else if (s.compare(i, 4, "&gt;") == 0) {
			out.push_back('>');
			i += 4;
		} else if (s.compare(i, 6, "&quot;") == 0) {
			out.push_back('"');
			i += 6;
		} else if (s.compare(i, 6, "&#x27;") == 0) {
			out.push_back('\'');
			i += 6;
		} else {
			out.push_back(s[i]);
			i += 1;
		}
	}
	return ToB(out);
}

std::vector<Category> NewsParser::Parse(const BString& htmlIn) {
	std::vector<Category> categories;
	std::string html = ToStd(htmlIn);

	// Known display titles (from rreader-web/feeds.json) used if a title
	// can't be read back out of the tab bar for some reason; the category
	// *set* and its order always come from the page itself, never from
	// this map, so a new/renamed/reordered category on the web side still
	// shows up correctly.
	struct { const char* key; const char* title; } kKnownTitles[] = {
		{"tech", "Tech"}, {"news", "Top News"}, {"economy", "Economy"},
	};

	size_t searchPos = 0;
	while (true) {
		size_t sectionStart = html.find("<section data-cat=\"", searchPos);
		if (sectionStart == std::string::npos)
			break;

		std::string tagHeader = html.substr(sectionStart, 200);
		std::string key, view;
		FindAttr(tagHeader, "data-cat", &key);
		FindAttr(tagHeader, "data-view", &view);
		searchPos = sectionStart + 20;

		if (view != "card")
			continue; // list view section; only the card view matters here

		size_t sectionEnd = html.find("</section>", sectionStart);
		if (sectionEnd == std::string::npos)
			break;
		std::string sectionBody = html.substr(sectionStart, sectionEnd - sectionStart);

		Category category;
		category.key = key.c_str();
		category.title = key.c_str();
		for (auto& kt : kKnownTitles) {
			if (key == kt.key) {
				category.title = kt.title;
				break;
			}
		}

		// Walk every <div class="group-card"> inside this section.
		size_t pos = 0;
		while (true) {
			size_t cardStart = sectionBody.find("<div class=\"group-card\">", pos);
			if (cardStart == std::string::npos)
				break;
			size_t cardEnd = FindMatchingDivClose(sectionBody, cardStart);
			if (cardEnd == std::string::npos)
				break;
			std::string card = sectionBody.substr(cardStart, cardEnd - cardStart);
			pos = cardEnd;

			SourceCard sc;

			std::string source, date, faviconTag, topTag, thumbTag, topTitle;
			size_t after;
			if (FindBetween(card, "<span class=\"group-source\">", "</span>", 0, &source, &after))
				sc.source = NewsParser::DecodeEntities(ToB(Trim(source)));
			if (FindBetween(card, "<span class=\"group-date\">", "</span>", 0, &date, &after))
				sc.date = NewsParser::DecodeEntities(ToB(Trim(date)));

			size_t faviconStart = card.find("<img class=\"group-favicon\"");
			if (faviconStart != std::string::npos) {
				size_t faviconTagEnd = card.find('>', faviconStart);
				std::string faviconTagStr =
					card.substr(faviconStart, faviconTagEnd - faviconStart);
				std::string src;
				if (FindAttr(faviconTagStr, "src", &src))
					sc.faviconDomain = ExtractFaviconDomain(src).c_str();
			}

			size_t topStart = card.find("<a class=\"group-top\"");
			if (topStart != std::string::npos) {
				size_t topTagEnd = card.find('>', topStart);
				std::string topTagStr = card.substr(topStart, topTagEnd - topStart);
				std::string href;
				if (FindAttr(topTagStr, "href", &href))
					sc.topUrl = NewsParser::DecodeEntities(ToB(href));
			}

			size_t thumbStart = card.find("<img class=\"group-thumb\"");
			if (thumbStart != std::string::npos) {
				size_t thumbTagEnd = card.find('>', thumbStart);
				std::string thumbTagStr = card.substr(thumbStart, thumbTagEnd - thumbStart);
				std::string src;
				if (FindAttr(thumbTagStr, "src", &src))
					sc.thumbUrl = NewsParser::DecodeEntities(ToB(src));
			}

			size_t titleStart = card.find("<span class=\"group-top-title");
			if (titleStart != std::string::npos) {
				size_t titleTextStart = card.find('>', titleStart) + 1;
				size_t titleTextEnd = card.find("</span>", titleTextStart);
				if (titleTextEnd != std::string::npos) {
					sc.topTitle = NewsParser::DecodeEntities(
						ToB(Trim(card.substr(titleTextStart, titleTextEnd - titleTextStart))));
				}
			}

			// Sub-articles: every <a class="group-sub" href="URL" ...>TITLE</a>
			size_t subPos = 0;
			while (true) {
				size_t subStart = card.find("<a class=\"group-sub\"", subPos);
				if (subStart == std::string::npos)
					break;
				size_t subTagEnd = card.find('>', subStart);
				std::string subTagStr = card.substr(subStart, subTagEnd - subStart);
				size_t subCloseA = card.find("</a>", subTagEnd);
				if (subCloseA == std::string::npos)
					break;
				std::string subInner =
					Trim(card.substr(subTagEnd + 1, subCloseA - subTagEnd - 1));
				subPos = subCloseA + 4;

				std::string href;
				if (FindAttr(subTagStr, "href", &href)) {
					SubArticle sub;
					sub.url = NewsParser::DecodeEntities(ToB(href));
					sub.title = NewsParser::DecodeEntities(ToB(Trim(StripTags(subInner))));
					sc.subs.push_back(sub);
				}
			}

			if (!sc.topUrl.IsEmpty())
				category.cards.push_back(sc);
		}

		if (!category.cards.empty())
			categories.push_back(category);
	}

	return categories;
}
