#include "ImageLoader.h"

#include <Bitmap.h>
#include <BitmapStream.h>
#include <MemoryIO.h>
#include <Message.h>
#include <OS.h>
#include <TranslatorRoster.h>

#include "HttpFetch.h"

const uint32 kMsgImageLoaded = 'imgL';

namespace {

struct LoadJob {
	BString url;
	BMessenger target;
};

int32 LoadThreadFunc(void* cookie) {
	LoadJob* job = static_cast<LoadJob*>(cookie);

	uint8* data = NULL;
	size_t size = 0;
	bool fetched = HttpFetch::GetSyncBinary(job->url, &data, &size);

	BBitmap* bitmap = NULL;
	if (fetched && size > 0) {
		BMemoryIO source(data, size);
		BBitmapStream outStream;
		status_t status = BTranslatorRoster::Default()->Translate(
			&source, NULL, NULL, &outStream, B_TRANSLATOR_BITMAP);
		if (status == B_OK)
			outStream.DetachBitmap(&bitmap);
	}
	delete[] data;

	BMessage msg(kMsgImageLoaded);
	msg.AddString("url", job->url);
	if (bitmap != NULL) {
		msg.AddBool("success", true);
		// Ownership transfers to whoever handles this message (see
		// CardView::MessageReceived) -- they must delete it eventually.
		msg.AddPointer("bitmap", bitmap);
	} else {
		msg.AddBool("success", false);
	}
	job->target.SendMessage(&msg);

	delete job;
	return 0;
}

} // namespace

void ImageLoader::LoadAsync(const BString& url, const BMessenger& target) {
	if (url.IsEmpty()) {
		BMessage msg(kMsgImageLoaded);
		msg.AddString("url", url);
		msg.AddBool("success", false);
		target.SendMessage(&msg);
		return;
	}
	LoadJob* job = new LoadJob{url, target};
	thread_id tid = spawn_thread(LoadThreadFunc, "news-image-load", B_LOW_PRIORITY, job);
	if (tid < 0) {
		BMessage msg(kMsgImageLoaded);
		msg.AddString("url", url);
		msg.AddBool("success", false);
		target.SendMessage(&msg);
		delete job;
		return;
	}
	resume_thread(tid);
}
