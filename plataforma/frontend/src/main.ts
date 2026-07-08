import "bootstrap/dist/css/bootstrap.min.css";
import "bootstrap";
import "./styles/theme.css";

import { ApiClient } from "./shared/api";
import { ToastBus } from "./shared/toast";
import { CameraViewerPage } from "./pages/camera-viewer";
import { DashboardPage } from "./pages/dashboard";
import { DetectionReportsPage } from "./pages/detection-reports";
import { DeviceAdminPage } from "./pages/device-admin";
import { EventsHistoryPage } from "./pages/events-history";
import { FleetKilometersPage } from "./pages/fleet-kilometers";
import { FleetMapPage } from "./pages/fleet-map";
import { GeofenceAdminPage } from "./pages/geofences";
import { LoginPage } from "./pages/login";
import { NotificationsPage } from "./pages/notifications";
import { OperationsPage } from "./pages/operations";
import { ProfilePage } from "./pages/profile";
import { UserAccessPage } from "./pages/user-access";
import { AppSidebar } from "./shared/sidebar";
import { SessionActions } from "./shared/session-actions";

const toastBus = new ToastBus(document.getElementById("toast-region"));
const api = new ApiClient({ onError: (message) => toastBus.error(message) });

const shell = document.getElementById("app-shell");
if (shell) {
  new AppSidebar(shell, document.getElementById("sidebar-toggle") as HTMLButtonElement | null).mount();
}

const sessionActionsRoot = document.getElementById("session-actions");
if (sessionActionsRoot) {
  new SessionActions(sessionActionsRoot, api, toastBus).mount();
}

const dashboardRoot = document.getElementById("dashboard-root");
if (dashboardRoot) {
  new DashboardPage(dashboardRoot, api).mount();
}

const deviceAdminRoot = document.getElementById("device-admin-root");
if (deviceAdminRoot) {
  new DeviceAdminPage(deviceAdminRoot, api, toastBus).mount();
}

const cameraViewerRoot = document.getElementById("camera-viewer-root");
if (cameraViewerRoot) {
  new CameraViewerPage(cameraViewerRoot, api, toastBus).mount();
}

const eventsHistoryRoot = document.getElementById("events-history-root");
if (eventsHistoryRoot) {
  new EventsHistoryPage(eventsHistoryRoot, api, toastBus).mount();
}

const fleetMapRoot = document.getElementById("fleet-map-root");
if (fleetMapRoot) {
  new FleetMapPage(fleetMapRoot, api, toastBus).mount();
}

const geofenceAdminRoot = document.getElementById("geofence-admin-root");
if (geofenceAdminRoot) {
  new GeofenceAdminPage(geofenceAdminRoot, api, toastBus).mount();
}

const fleetKilometersRoot = document.getElementById("fleet-kilometers-root");
if (fleetKilometersRoot) {
  new FleetKilometersPage(fleetKilometersRoot, api, toastBus).mount();
}

const detectionReportsRoot = document.getElementById("detection-reports-root");
if (detectionReportsRoot) {
  new DetectionReportsPage(detectionReportsRoot, api, toastBus).mount();
}

const notificationsRoot = document.getElementById("notifications-root");
if (notificationsRoot) {
  new NotificationsPage(notificationsRoot, api, toastBus).mount();
}

const operationsRoot = document.getElementById("operations-root");
if (operationsRoot) {
  new OperationsPage(operationsRoot, api, toastBus).mount();
}

const userAccessRoot = document.getElementById("user-access-root");
if (userAccessRoot) {
  new UserAccessPage(userAccessRoot, api, toastBus).mount();
}

const profileRoot = document.getElementById("profile-root");
if (profileRoot) {
  new ProfilePage(profileRoot, api, toastBus).mount();
}

const loginRoot = document.getElementById("login-root");
if (loginRoot) {
  new LoginPage(loginRoot, api, toastBus).mount();
}
