// Progressive-enhancement handlers kept OUT of inline attributes so a strict
// Content-Security-Policy (script-src 'self') can be enforced. Inline on*=
// handlers were also a stored-XSS vector when they interpolated user data.
document.addEventListener("DOMContentLoaded", function () {
  // Confirm before submitting any form that declares a data-confirm message.
  // Reading the message via getAttribute keeps it a plain string — even a
  // student/module name like "'); alert(1)//" is shown literally, never run.
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        event.preventDefault();
      }
    });
  });

  // Auto-submit the parent <form> when a [data-autosubmit] control changes.
  document.querySelectorAll("[data-autosubmit]").forEach(function (control) {
    control.addEventListener("change", function () {
      if (control.form) {
        control.form.submit();
      }
    });
  });
});
