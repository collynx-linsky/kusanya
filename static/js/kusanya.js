// KUSANYA — shared client-side behaviour. See docs/DESIGN_SYSTEM.md for
// the conventions this backs (HTMX architecture, toast events).
"use strict";

(function () {
  // ------------------------------------------------------------------
  // Responsive sidebar (off-canvas below lg — see kusanya.css)
  // ------------------------------------------------------------------
  const sidebar = document.getElementById("kzSidebar");
  const backdrop = document.getElementById("kzSidebarBackdrop");
  const toggle = document.getElementById("kzSidebarToggle");

  function closeSidebar() {
    if (!sidebar) return;
    sidebar.classList.remove("show");
    backdrop && backdrop.classList.remove("show");
    toggle && toggle.setAttribute("aria-expanded", "false");
  }

  function openSidebar() {
    if (!sidebar) return;
    sidebar.classList.add("show");
    backdrop && backdrop.classList.add("show");
    toggle && toggle.setAttribute("aria-expanded", "true");
  }

  if (toggle) {
    toggle.addEventListener("click", function () {
      if (sidebar.classList.contains("show")) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });
  }
  if (backdrop) {
    backdrop.addEventListener("click", closeSidebar);
  }
  // Close the mobile drawer after any in-app navigation.
  document.body.addEventListener("htmx:beforeRequest", closeSidebar);

  // ------------------------------------------------------------------
  // Global HTMX loading indicator — a thin top progress bar, since not
  // every request has (or should need) a local htmx-indicator element.
  // ------------------------------------------------------------------
  const progressBar = document.getElementById("kzProgressBar");
  let activeRequests = 0;

  document.body.addEventListener("htmx:beforeRequest", function () {
    activeRequests += 1;
    if (progressBar) progressBar.classList.add("htmx-request");
  });
  document.body.addEventListener("htmx:afterRequest", function () {
    activeRequests = Math.max(0, activeRequests - 1);
    if (activeRequests === 0 && progressBar) {
      progressBar.classList.remove("htmx-request");
    }
  });

  // ------------------------------------------------------------------
  // Toasts. Two ways in:
  //  1. Server-side: an HX-Trigger response header of
  //     {"kzToast": {"message": "...", "level": "success"}} — htmx
  //     dispatches this as a `kzToast` event on the element that made
  //     the request, which bubbles to document.
  //  2. Client-side: window.kzShowToast("message", "success").
  // Levels: success | danger | warning | info (Bootstrap semantic names).
  // ------------------------------------------------------------------
  const TOAST_ICON = {
    success: "bi-check-circle-fill",
    danger: "bi-x-circle-fill",
    warning: "bi-exclamation-triangle-fill",
    info: "bi-info-circle-fill",
  };

  function showToast(message, level) {
    const region = document.getElementById("kz-toasts");
    if (!region || !message) return;
    level = level in TOAST_ICON ? level : "info";

    const el = document.createElement("div");
    el.className = "toast align-items-center border-0 text-bg-" + level;
    el.setAttribute("role", "alert");
    el.innerHTML =
      '<div class="d-flex">' +
      '<div class="toast-body"><i class="bi ' + TOAST_ICON[level] + ' me-2"></i>' +
      String(message).replace(/</g, "&lt;") +
      "</div>" +
      '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>' +
      "</div>";
    region.appendChild(el);

    const toast = new bootstrap.Toast(el, { delay: 5000 });
    el.addEventListener("hidden.bs.toast", function () {
      el.remove();
    });
    toast.show();
  }
  window.kzShowToast = showToast;

  document.body.addEventListener("kzToast", function (evt) {
    const detail = evt.detail || {};
    showToast(detail.message, detail.level);
  });

  // Any non-2xx HTMX response gets a generic toast, unless the response
  // opted out (HX-Trigger already sent its own kzToast) — this is a
  // safety net so a failed inline action is never silently invisible.
  document.body.addEventListener("htmx:responseError", function (evt) {
    if (evt.detail && evt.detail.xhr && evt.detail.xhr.getResponseHeader("HX-Trigger")) {
      return; // the server already told us what to show
    }
    showToast("Something went wrong. Please try again.", "danger");
  });
  document.body.addEventListener("htmx:sendError", function () {
    showToast("Network error — check your connection and try again.", "danger");
  });
})();
