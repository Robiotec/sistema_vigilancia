(function () {
  const config = window.__WEB_APP_CONFIG__ || {};
  const suffix = typeof config.staticAssetVersion === "string" && config.staticAssetVersion
    ? `?v=${encodeURIComponent(config.staticAssetVersion)}`
    : "";

  import(`/static/web_app/cameras/admin_fallback.js${suffix}`).catch((error) => {
    window.console.error("No se pudo cargar el modulo de administracion de camaras.", error);
  });
})();
