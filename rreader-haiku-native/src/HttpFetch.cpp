#include "HttpFetch.h"

#include <curl/curl.h>

#include <cstdio>
#include <cstring>
#include <string>
#include <sys/stat.h>

namespace {

const char* kCaBundle = "/boot/system/data/ssl/CARootCertificates.pem";

size_t AppendToString(char* data, size_t size, size_t nmemb, void* userp) {
	static_cast<std::string*>(userp)->append(data, size * nmemb);
	return size * nmemb;
}

// One handle per thread, reused so keep-alive connections and the parsed
// CA bundle survive between requests (TLS setup is expensive on old CPUs).
CURL* ThreadHandle() {
	thread_local CURL* handle = curl_easy_init();
	if (handle != NULL)
		curl_easy_reset(handle);
	return handle;
}

bool Fetch(const BString& url, std::string* out) {
	CURL* curl = ThreadHandle();
	if (curl == NULL)
		return false;

	curl_easy_setopt(curl, CURLOPT_URL, url.String());
	curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
	curl_easy_setopt(curl, CURLOPT_MAXREDIRS, 5L);
	curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 20L);
	curl_easy_setopt(curl, CURLOPT_TIMEOUT, 60L);
	curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
	curl_easy_setopt(curl, CURLOPT_ACCEPT_ENCODING, "");
	curl_easy_setopt(curl, CURLOPT_USERAGENT, "news.coroke.net-haiku/1.0");
	curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, AppendToString);
	curl_easy_setopt(curl, CURLOPT_WRITEDATA, out);

	struct stat st;
	if (stat(kCaBundle, &st) == 0)
		curl_easy_setopt(curl, CURLOPT_CAINFO, kCaBundle);

	CURLcode res = curl_easy_perform(curl);
	long status = 0;
	curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &status);

	bool ok = res == CURLE_OK && status >= 200 && status < 300 && !out->empty();
	if (!ok) {
		fprintf(stderr, "[http] %s: %s (HTTP %ld)\n", url.String(),
			curl_easy_strerror(res), status);
	}
	return ok;
}

} // namespace

void HttpFetch::GlobalInit() {
	curl_global_init(CURL_GLOBAL_ALL);
}

bool HttpFetch::GetSync(const BString& url, BString* outBody) {
	std::string body;
	if (!Fetch(url, &body))
		return false;
	outBody->SetTo(body.data(), body.size());
	return true;
}

bool HttpFetch::GetSyncBinary(const BString& url, uint8** outData, size_t* outSize) {
	std::string body;
	if (!Fetch(url, &body)) {
		*outData = NULL;
		*outSize = 0;
		return false;
	}
	*outSize = body.size();
	*outData = new uint8[*outSize];
	memcpy(*outData, body.data(), *outSize);
	return true;
}
