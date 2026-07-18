(function () {
  const config = window.COSMONET_CONFIG || {};
  const valueOrPlaceholder = (value, placeholder) => value || placeholder;

  document.querySelectorAll("[data-merchant-name]").forEach((element) => {
    element.textContent = valueOrPlaceholder(config.merchantName, "самозанятый: укажите ФИО");
  });
  document.querySelectorAll("[data-merchant-inn]").forEach((element) => {
    element.textContent = valueOrPlaceholder(config.merchantInn, "укажите ИНН");
  });
  document.querySelectorAll("[data-merchant-city]").forEach((element) => {
    element.textContent = valueOrPlaceholder(config.merchantCity, "укажите город");
  });
  document.querySelectorAll("[data-support-email]").forEach((element) => {
    const email = valueOrPlaceholder(config.supportEmail, "укажите e-mail поддержки");
    element.textContent = email;
    if (config.supportEmail) element.href = `mailto:${config.supportEmail}`;
  });
  document.querySelectorAll("[data-updated-at]").forEach((element) => {
    element.textContent = config.updatedAt || "укажите дату";
  });
  document.querySelectorAll("[data-bot-link]").forEach((element) => {
    if (!config.botUrl) {
      element.classList.add("is-disabled");
      element.setAttribute("aria-disabled", "true");
      element.title = "Добавьте ссылку на бота в config.js";
      return;
    }
    element.href = config.botUrl;
  });
})();