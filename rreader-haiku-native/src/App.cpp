#include "App.h"

#include "MainWindow.h"

// The MIME signature namespace ("x-vnd.rainygirl-NewsCoroke") is just an
// internal identifier Haiku uses to track the app's type/icon/etc; it is
// NOT what shows up as the app's display name in Deskbar or the Tracker
// title bar -- that comes from the window title ("news.coroke.net", set
// in MainWindow's constructor) and the app's mimeset "long description"
// resource attribute (see README.md).
App::App() : BApplication("application/x-vnd.rainygirl-NewsCoroke"), fWindow(NULL) {
}

void App::ReadyToRun() {
	fWindow = new MainWindow();
	fWindow->Show();
}
