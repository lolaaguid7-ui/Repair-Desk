"use strict";
// Progressive enhancement: keep open forms intact when the local server is unreachable.
document.querySelector('.skip-link')?.addEventListener('click', event => {
  event.preventDefault(); document.querySelector('main').focus();
});
function bindForms() {
document.querySelectorAll('form[method="post"]:not([data-bound])').forEach(form => {
  form.dataset.bound = 'true';
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (form.dataset.submitting) return;
    const body = new URLSearchParams(new FormData(form));
    form.dataset.submitting = 'true';
    form.setAttribute('aria-busy', 'true');
    form.querySelectorAll('button[type="submit"], button:not([type])').forEach(button => {
      if (!button.disabled) {button.dataset.submitDisabled = 'true';button.disabled = true;}
    });
    document.querySelector('.client-error')?.remove();
    try {
      const response = await fetch(form.action, {method:'POST', body, credentials:'same-origin', redirect:'follow'});
      if (response.redirected && response.ok && new URL(response.url).origin === location.origin) {
        location.assign(response.url); return;
      }
      const html = await response.text();
      const incoming = new DOMParser().parseFromString(html, 'text/html');
      const main = incoming.querySelector('main');
      if (!main?.querySelector('form[method="post"]')) {
        const message = incoming.querySelector('.notice.error span, .empty-state p')?.textContent;
        showError(message || 'Your change was not confirmed. Your entries are still here. Try again.');
        return;
      }
      document.querySelector('main').replaceWith(document.importNode(main, true));
      document.title = incoming.title;
      bindForms();
      const focus = document.querySelector('[aria-invalid="true"], [role="alert"]');
      if (focus) {if (!focus.matches('input,select,textarea')) focus.tabIndex=-1;focus.focus();}
    } catch (_) {
      showError('The local app could not be reached. Your entries are still here. Check that Repair Desk is running, then try again.');
    } finally {
      restoreForms();
    }
  });
});
}
function showError(message) {
  const alert = document.createElement('div');
  alert.className = 'notice error client-error';alert.setAttribute('role','alert');alert.tabIndex=-1;
  alert.textContent = message;document.querySelector('main').prepend(alert);alert.focus();
}
function restoreForms() {
  document.querySelectorAll('form[data-submitting]').forEach(form => {
    delete form.dataset.submitting; form.removeAttribute('aria-busy');
  });
  document.querySelectorAll('[data-submit-disabled]').forEach(button => {
    button.disabled = false; delete button.dataset.submitDisabled;
  });
}
window.addEventListener('pageshow', restoreForms);
bindForms();
const invalid = document.querySelector('[aria-invalid="true"]');
if (invalid) invalid.focus();
