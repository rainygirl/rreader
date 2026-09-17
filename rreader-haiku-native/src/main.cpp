#include "App.h"
#include "HttpFetch.h"
#include "ImageLoader.h"
#include "NewsFetcher.h"

int main() {
	HttpFetch::GlobalInit();
	{
		App app;
		app.Run();

		// Background threads may still be downloading or decoding (decoding
		// creates BBitmaps, which needs the app_server connection) when the
		// window closes, so stop them while `app` still exists and before
		// static destructors and library teardown run.
		HttpFetch::AbortAll();
		ImageLoader::Shutdown();
		NewsFetcher::Shutdown();
	}
	HttpFetch::GlobalCleanup();
	return 0;
}
