(function registerRobiotecUiHelpers(window, document) {
  const namespace = window.RobiotecUI || {};

  function copyTextFallback(text) {
    const helper = document.createElement("textarea");
    helper.value = text;
    helper.setAttribute("readonly", "");
    helper.style.position = "fixed";
    helper.style.left = "-9999px";
    helper.style.top = "0";
    document.body.appendChild(helper);
    try {
      helper.focus();
      helper.select();
      return Boolean(document.execCommand("copy"));
    } catch (error) {
      return false;
    } finally {
      helper.remove();
    }
  }

  async function copyTextValue(text) {
    const value = String(text || "").trim();
    if (!value || value === "--") return false;
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function" && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      return true;
    }
    return copyTextFallback(value);
  }

  function copyButtonDataValue(copyButton) {
    if (!(copyButton instanceof Element)) return "";
    const targetId = copyButton.getAttribute("data-camera-copy-target");
    const targetField = targetId ? document.getElementById(targetId) : null;
    if (targetField && "value" in targetField) {
      return targetField.value;
    }
    return copyButton.getAttribute("data-copy-value") || "";
  }

  function handleCopyButtonFeedback(copyButton, value = copyButtonDataValue(copyButton)) {
    if (!(copyButton instanceof HTMLElement)) return;
    const originalLabel = copyButton.textContent || "Copiar";
    copyButton.textContent = "Copiando...";
    void copyTextValue(value)
      .then((ok) => {
        copyButton.textContent = ok ? "Copiado" : "No copiado";
      })
      .catch(() => {
        copyButton.textContent = "No copiado";
      })
      .finally(() => {
        window.setTimeout(() => {
          copyButton.textContent = originalLabel;
        }, 1200);
      });
  }

  namespace.copyTextValue = namespace.copyTextValue || copyTextValue;
  namespace.copyButtonDataValue = namespace.copyButtonDataValue || copyButtonDataValue;
  namespace.handleCopyButtonFeedback = namespace.handleCopyButtonFeedback || handleCopyButtonFeedback;

  window.RobiotecUI = namespace;
})(window, document);
