// HttpFetch.h -- blocking HTTP GET helper (Network Kit), meant to be
// called from a worker thread you already spawned (never from the UI
// thread). Shared by NewsFetcher (page HTML) and ImageLoader (thumbnails/
// favicons) so the BUrlRequest plumbing exists in exactly one place.
#ifndef NEWS_COROKE_HTTP_FETCH_H
#define NEWS_COROKE_HTTP_FETCH_H

#include <String.h>
#include <SupportDefs.h>

namespace HttpFetch {

// Blocks the calling thread until the request completes. On success,
// fills `outBody` with the raw response bytes and returns true.
bool GetSync(const BString& url, BString* outBody);

// Same, but for binary data (images) where the response isn't valid UTF-8
// text -- writes the raw bytes into `outData`/`outSize` (caller owns the
// buffer, free with delete[]).
bool GetSyncBinary(const BString& url, uint8** outData, size_t* outSize);

} // namespace HttpFetch

#endif // NEWS_COROKE_HTTP_FETCH_H
