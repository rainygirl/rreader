#include "ImageLoader.h"

#include <Bitmap.h>
#include <BitmapStream.h>
#include <DataIO.h>
#include <Message.h>
#include <TranslatorRoster.h>

#include <condition_variable>
#include <deque>
#include <mutex>
#include <thread>
#include <vector>

#include "HttpFetch.h"

namespace {

// A thread per image (~80 per tab) made every TLS handshake time out on
// slower machines; a few workers with reused curl handles finish quickly.
const int kWorkerCount = 4;

struct LoadJob {
	BString url;
	BMessenger target;
};

std::mutex sQueueLock;
std::condition_variable sQueueCond;
std::deque<LoadJob> sQueue;
std::once_flag sStartOnce;
std::vector<std::thread> sWorkers;
bool sStopping = false;

bool Stopping() {
	std::lock_guard<std::mutex> lock(sQueueLock);
	return sStopping;
}

BBitmap* Decode(uint8* data, size_t size) {
	BMemoryIO source(data, size);
	BBitmapStream outStream;
	BBitmap* bitmap = NULL;
	if (BTranslatorRoster::Default()->Translate(
			&source, NULL, NULL, &outStream, B_TRANSLATOR_BITMAP) == B_OK)
		outStream.DetachBitmap(&bitmap);
	return bitmap;
}

void Reply(const LoadJob& job, BBitmap* bitmap) {
	BMessage msg(kMsgImageLoaded);
	msg.AddString("url", job.url);
	msg.AddBool("success", bitmap != NULL);
	if (bitmap != NULL)
		msg.AddPointer("bitmap", bitmap);
	if (job.target.SendMessage(&msg) != B_OK)
		delete bitmap;
}

void WorkerLoop() {
	while (true) {
		LoadJob job;
		{
			std::unique_lock<std::mutex> lock(sQueueLock);
			sQueueCond.wait(lock, [] { return sStopping || !sQueue.empty(); });
			if (sStopping)
				return;
			job = sQueue.front();
			sQueue.pop_front();
		}
		if (!job.target.IsValid())
			continue;

		uint8* data = NULL;
		size_t size = 0;
		BBitmap* bitmap = NULL;
		if (HttpFetch::GetSyncBinary(job.url, &data, &size) && !Stopping())
			bitmap = Decode(data, size);
		delete[] data;
		Reply(job, bitmap);
	}
}

void StartWorkers() {
	BTranslatorRoster::Default(); // load translators once, before workers race for it
	for (int i = 0; i < kWorkerCount; i++)
		sWorkers.emplace_back(WorkerLoop);
}

} // namespace

void ImageLoader::LoadAsync(const BString& url, const BMessenger& target) {
	if (url.IsEmpty()) {
		Reply(LoadJob{url, target}, NULL);
		return;
	}
	std::call_once(sStartOnce, StartWorkers);
	{
		std::lock_guard<std::mutex> lock(sQueueLock);
		sQueue.push_back(LoadJob{url, target});
	}
	sQueueCond.notify_one();
}

// Workers must be gone before exit() destroys the queue globals and tears
// down libcurl/OpenSSL; quitting mid-load used to crash in exactly that way.
void ImageLoader::Shutdown() {
	{
		std::lock_guard<std::mutex> lock(sQueueLock);
		sStopping = true;
		sQueue.clear();
	}
	sQueueCond.notify_all();
	for (std::thread& worker : sWorkers)
		worker.join();
	sWorkers.clear();
}

void ImageLoader::CancelPending() {
	std::lock_guard<std::mutex> lock(sQueueLock);
	sQueue.clear();
}
