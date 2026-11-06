// Dashboard modulare personalizzabile (renderCustomDashboard in js/dashboard.js)
// Compatibilita' selettori contesto e test: Guida rapida, gs-dashboard__tiles, data-dashboard-game
GS.registerExperience({
  id: "dashboard",
  name: "Dashboard",
  description: "Home personalizzabile con griglia a blocchi e widget.",
  nav: "top",
  home: (element, context) => {
    const renderFn = (typeof window !== "undefined" && (window.renderCustomDashboard || window.GS?.renderCustomDashboard))
      || (typeof renderCustomDashboard === "function" ? renderCustomDashboard : null);
    if (typeof renderFn === "function") {
      renderFn(element, context);
    } else {
      element.innerHTML = "<p class='muted'>" + t("c.dashboard.loading") + "</p>";
      setTimeout(() => {
        const retryFn = (typeof window !== "undefined" && (window.renderCustomDashboard || window.GS?.renderCustomDashboard))
          || (typeof renderCustomDashboard === "function" ? renderCustomDashboard : null);
        if (typeof retryFn === "function") retryFn(element, context);
      }, 50);
    }
  },
  card: null,
  detail: "panel",
  onFocus: null,
});
