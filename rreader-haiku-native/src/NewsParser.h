// NewsParser.h -- turns the raw HTML news.coroke.net serves into the
// Category/SourceCard data model (NewsData.h). Deliberately NOT a general
// HTML parser: it only knows the specific, stable markup rreader-web's
// generate.py emits for the card view (rreader-web/generate.py, the
// "group-card" section -- see that file if this ever needs updating
// alongside a markup change there). Plain substring scanning, no <regex>,
// so it doesn't depend on a particular libstdc++/GCC ABI being available.
#ifndef NEWS_COROKE_PARSER_H
#define NEWS_COROKE_PARSER_H

#include <String.h>
#include <vector>

#include "NewsData.h"

namespace NewsParser {

// Parses every `<section data-cat="..." data-view="card" class="pane">`
// block in `html`, in document order. Returns an empty vector (never
// throws) if the page doesn't look like what's expected -- callers should
// treat an empty result as "couldn't parse this page".
std::vector<Category> Parse(const BString& html);

// Decodes the handful of HTML entities generate.py's esc() (Python's
// html.escape) ever produces: &amp; &lt; &gt; &quot; &#x27; -- everything
// else in the page is already plain UTF-8, not entity-encoded.
BString DecodeEntities(const BString& text);

} // namespace NewsParser

#endif // NEWS_COROKE_PARSER_H
