#include "NewsFetcher.h"

#include <Message.h>
#include <OS.h>

#include "HttpFetch.h"


namespace {

thread_id sFetchThread = -1;

struct FetchJob {
	BString url;
	BMessenger target;
};

int32 FetchThreadFunc(void* cookie) {
	FetchJob* job = static_cast<FetchJob*>(cookie);

	BString body;
	bool ok = HttpFetch::GetSync(job->url, &body);

	BMessage msg(kMsgNewsFetched);
	if (ok) {
		msg.AddBool("success", true);
		msg.AddString("html", body);
	} else {
		msg.AddBool("success", false);
		msg.AddString("error", "Could not fetch news.coroke.net");
	}
	job->target.SendMessage(&msg);

	delete job;
	return 0;
}

} // namespace

void NewsFetcher::FetchAsync(const BString& url, const BMessenger& target) {
	FetchJob* job = new FetchJob{url, target};
	thread_id tid = spawn_thread(FetchThreadFunc, "news-fetch", B_NORMAL_PRIORITY, job);
	if (tid < 0) {
		BMessage msg(kMsgNewsFetched);
		msg.AddBool("success", false);
		msg.AddString("error", "Could not spawn fetch thread");
		target.SendMessage(&msg);
		delete job;
		return;
	}
	sFetchThread = tid;
	resume_thread(tid);
}

void NewsFetcher::Shutdown() {
	if (sFetchThread >= 0) {
		status_t result;
		wait_for_thread(sFetchThread, &result);
		sFetchThread = -1;
	}
}
