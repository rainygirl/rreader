// HttpFetch.h -- blocking HTTP GET helper (libcurl; Haiku's BUrlRequest
// API is private and not linkable from third-party apps). Call only from
// worker threads, never the UI thread.
#ifndef NEWS_COROKE_HTTP_FETCH_H
#define NEWS_COROKE_HTTP_FETCH_H

#include <String.h>
#include <SupportDefs.h>

namespace HttpFetch {

// Call once from main() before any thread uses GetSync*.
void GlobalInit();

// Blocks the calling thread until the request completes. On success,
// fills `outBody` with the raw response bytes and returns true.
bool GetSync(const BString& url, BString* outBody);

// Same, but for binary data (images) where the response isn't valid UTF-8
// text -- writes the raw bytes into `outData`/`outSize` (caller owns the
// buffer, free with delete[]).
bool GetSyncBinary(const BString& url, uint8** outData, size_t* outSize);

} // namespace HttpFetch

#endif // NEWS_COROKE_HTTP_FETCH_H
