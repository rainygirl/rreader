#include "App.h"
#include "HttpFetch.h"

int main() {
	HttpFetch::GlobalInit();
	App app;
	app.Run();
	return 0;
}
