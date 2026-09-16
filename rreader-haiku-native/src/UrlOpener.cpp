#include "UrlOpener.h"

#include <Roster.h>

void UrlOpener::Open(const BString& url) {
	if (url.IsEmpty())
		return;

	BString mime("application/x-vnd.Be.URL.https");
	if (url.IFindFirst("http://") == 0)
		mime = "application/x-vnd.Be.URL.http";

	const char* args[] = {url.String(), NULL};
	status_t status = be_roster->Launch(mime.String(), 1, const_cast<char**>(args));

	if (status != B_OK && status != B_ALREADY_RUNNING) {
		// Fall back to a plain http handler in case the https one isn't
		// registered for some reason -- better to try than to silently fail.
		be_roster->Launch("application/x-vnd.Be.URL.http", 1, const_cast<char**>(args));
	}
}
