// ImageLoader.h -- fetches an image URL (thumbnail or favicon) on a
// background thread and decodes it to a BBitmap via the Translation Kit,
// then posts it back to a target BHandler. Same async-thread-plus-message
// pattern as NewsFetcher, kept separate since images are decoded (not just
// raw bytes) and there can be many of them in flight per screen.
#ifndef NEWS_COROKE_IMAGE_LOADER_H
#define NEWS_COROKE_IMAGE_LOADER_H

#include <Messenger.h>
#include <String.h>

// Message posted back once an image load finishes. Fields: "url" (string,
// echoes the request so the receiver can match it to the right card/view),
// "success" (bool), "bitmap" (a BBitmap archived via BMessage::AddFlat, if
// success).
inline constexpr uint32 kMsgImageLoaded = 'imgL';

namespace ImageLoader {

void LoadAsync(const BString& url, const BMessenger& target);

// Drops queued (not yet started) loads, e.g. when switching tabs.
void CancelPending();

// Stops and joins the worker threads. Call HttpFetch::AbortAll() first so
// a worker stuck in a slow download returns promptly.
void Shutdown();

} // namespace ImageLoader

#endif // NEWS_COROKE_IMAGE_LOADER_H
