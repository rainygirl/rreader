#include "HttpFetch.h"

#include <DataIO.h>
#include <HttpRequest.h>
#include <OS.h>
#include <Url.h>
#include <UrlContext.h>
#include <UrlProtocolListener.h>
#include <UrlProtocolRoster.h>
#include <UrlRequest.h>

#include <cstring>

namespace {

// NOTE: see the same note in NewsFetcher.cpp -- BUrlProtocolListener's
// virtual signatures can shift slightly between Haiku releases; the
// Run()-then-wait-on-a-semaphore flow below is the part that's stable.
class CollectingListener : public BUrlProtocolListener {
public:
	explicit CollectingListener(sem_id doneSem) : fDone(doneSem), fSuccess(false) {}

	void DataReceived(BUrlRequest* caller, const char* data, off_t position,
		ssize_t size) override {
		fData.Write(data, size);
	}

	void RequestCompleted(BUrlRequest* caller, bool success) override {
		fSuccess = success;
		release_sem(fDone);
	}

	BMallocIO fData;
	sem_id fDone;
	bool fSuccess;
};

bool RunSync(const BString& url, CollectingListener* listener) {
	BUrlContext context;
	BUrl parsedUrl(url);
	BUrlRequest* request = BUrlProtocolRoster::MakeRequest(parsedUrl, listener, &context);
	if (request == NULL)
		return false;

	request->Run();
	acquire_sem(listener->fDone);
	delete request;
	return listener->fSuccess && listener->fData.BufferLength() > 0;
}

} // namespace

bool HttpFetch::GetSync(const BString& url, BString* outBody) {
	sem_id doneSem = create_sem(0, "http_fetch_done");
	CollectingListener listener(doneSem);
	bool ok = RunSync(url, &listener);
	if (ok) {
		outBody->SetTo(
			static_cast<const char*>(listener.fData.Buffer()), listener.fData.BufferLength());
	}
	delete_sem(doneSem);
	return ok;
}

bool HttpFetch::GetSyncBinary(const BString& url, uint8** outData, size_t* outSize) {
	sem_id doneSem = create_sem(0, "http_fetch_bin_done");
	CollectingListener listener(doneSem);
	bool ok = RunSync(url, &listener);
	if (ok) {
		*outSize = listener.fData.BufferLength();
		*outData = new uint8[*outSize];
		memcpy(*outData, listener.fData.Buffer(), *outSize);
	} else {
		*outData = NULL;
		*outSize = 0;
	}
	delete_sem(doneSem);
	return ok;
}
