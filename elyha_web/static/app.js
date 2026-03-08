(function () {
  "use strict";

  const App = window.ElyhaWebAppComponent;
  if (typeof App !== "function") {
    throw new Error("Web app component is unavailable. Please check /web/static/web/app/*.js");
  }

  const root = document.getElementById("root");
  if (!root) {
    throw new Error("Missing #root mount node in web UI page");
  }

  ReactDOM.createRoot(root).render(React.createElement(App));
})();
