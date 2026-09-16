// UrlOpener.h -- open a URL in the user's default browser via BRoster,
// the standard Haiku mechanism (the same one Haiku's own apps use for
// clickable links). Never opens anything in-app.
#ifndef NEWS_COROKE_URL_OPENER_H
#define NEWS_COROKE_URL_OPENER_H

#include <String.h>

namespace UrlOpener {

// Launches the registered handler for the URL's scheme (WebPositive or
// whatever browser is set as default) via the "application/x-vnd.Be.URL.*"
// MIME types Haiku registers for http/https.
void Open(const BString& url);

} // namespace UrlOpener

#endif // NEWS_COROKE_URL_OPENER_H
