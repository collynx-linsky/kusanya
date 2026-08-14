// jsdom-simulated integration tests for kusanya.js itself (not a
// reimplementation of its logic) -- these load the actual production
// script against a hand-built DOM fragment and assert on real DOM
// mutations, the same way the browser would exercise it. Scoped to the
// two behaviours that are pure DOM wiring with no Bootstrap/HTMX runtime
// dependency (password toggle, bulk-selection bar); the command palette,
// toasts, and modal wiring depend on the Bootstrap JS bundle loaded from
// a CDN in the real page and are left to manual/live verification per
// docs/DESIGN_SYSTEM.md, rather than faking a bootstrap.Toast/Modal here.
import { describe, it, expect, beforeEach, vi } from "vitest";
import kzLogic from "./kusanya-logic.js";

async function loadKusanya() {
  vi.resetModules();
  window.KZLogic = kzLogic;
  await import("./kusanya.js");
}

describe("kusanya.js password visibility toggle (jsdom integration)", () => {
  beforeEach(() => {
    document.body.innerHTML = '<input type="password" class="form-control" id="pw">';
  });

  it("wraps a password input and adds a working show/hide toggle", async () => {
    await loadKusanya();

    const input = document.getElementById("pw");
    const wrap = input.closest(".kz-password-wrap");
    expect(wrap).not.toBeNull();

    const toggle = wrap.querySelector("button");
    expect(toggle).not.toBeNull();
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
    expect(input.type).toBe("password");

    toggle.click();
    expect(input.type).toBe("text");
    expect(toggle.getAttribute("aria-pressed")).toBe("true");

    toggle.click();
    expect(input.type).toBe("password");
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
  });

  it("does not double-wrap an input that's already wrapped", async () => {
    await loadKusanya();
    const before = document.querySelectorAll(".kz-password-wrap").length;

    await loadKusanya(); // simulate the script running again against the same DOM
    const after = document.querySelectorAll(".kz-password-wrap").length;

    expect(after).toBe(before);
  });
});

describe("kusanya.js bulk-selection toolbar (jsdom integration)", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="kz-bulk-bar" class="d-none"></div>
      <span id="kz-bulk-count"></span>
      <input type="checkbox" id="kz-bulk-select-all">
      <input type="checkbox" class="kz-bulk-checkbox" value="1">
      <input type="checkbox" class="kz-bulk-checkbox" value="2">
    `;
  });

  it("shows the bulk bar and updates the count when a row is checked", async () => {
    await loadKusanya();
    const checkboxes = document.querySelectorAll(".kz-bulk-checkbox");
    checkboxes[0].checked = true;
    checkboxes[0].dispatchEvent(new Event("change", { bubbles: true }));

    const bar = document.getElementById("kz-bulk-bar");
    expect(bar.classList.contains("d-none")).toBe(false);
    expect(document.getElementById("kz-bulk-count").textContent).toBe("1");
  });

  it("hides the bulk bar again once every row is unchecked", async () => {
    await loadKusanya();
    const checkboxes = document.querySelectorAll(".kz-bulk-checkbox");
    checkboxes[0].checked = true;
    checkboxes[0].dispatchEvent(new Event("change", { bubbles: true }));
    checkboxes[0].checked = false;
    checkboxes[0].dispatchEvent(new Event("change", { bubbles: true }));

    expect(document.getElementById("kz-bulk-bar").classList.contains("d-none")).toBe(true);
  });

  it("select-all checks every row and updates the count", async () => {
    await loadKusanya();
    const selectAll = document.getElementById("kz-bulk-select-all");
    selectAll.checked = true;
    selectAll.dispatchEvent(new Event("change", { bubbles: true }));

    document.querySelectorAll(".kz-bulk-checkbox").forEach((cb) => expect(cb.checked).toBe(true));
    expect(document.getElementById("kz-bulk-count").textContent).toBe("2");
  });
});
