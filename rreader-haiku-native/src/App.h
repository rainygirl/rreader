// App.h -- BApplication entry point. App name shown in Deskbar/Tracker is
// "news.coroke.net" (the MIME app signature's short description, set in
// the resource attributes -- see README.md's "App name" section for how
// to set that with mimeset/setversion since it isn't literally the
// app-signature string itself).
#ifndef NEWS_COROKE_APP_H
#define NEWS_COROKE_APP_H

#include <Application.h>

class MainWindow;

class App : public BApplication {
public:
	App();

	void ReadyToRun() override;

private:
	MainWindow* fWindow;
};

#endif // NEWS_COROKE_APP_H
