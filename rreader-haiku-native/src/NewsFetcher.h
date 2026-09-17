// NewsFetcher.h -- fetches https://news.coroke.net/ on a background thread
// (HttpFetch/libcurl) and posts the result back to a
// target BHandler as a BMessage, so the UI thread never blocks on the
// network.
#ifndef NEWS_COROKE_FETCHER_H
#define NEWS_COROKE_FETCHER_H

#include <Handler.h>
#include <Messenger.h>
#include <String.h>

// Message posted back to the target handler when a fetch finishes.
// Fields: "success" (bool), "html" (string, only if success), "error"
// (string, only if !success).
inline constexpr uint32 kMsgNewsFetched = 'nwsF';

namespace NewsFetcher {

// Fires off an async GET for `url` and posts kMsgNewsFetched to `target`
// once it completes (success or failure). Safe to call from the UI thread;
// does its own thread management internally.
void FetchAsync(const BString& url, const BMessenger& target);

// Waits for an in-flight fetch thread to finish (after HttpFetch::AbortAll()).
void Shutdown();

} // namespace NewsFetcher

#endif // NEWS_COROKE_FETCHER_H
