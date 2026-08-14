// KUSANYA — pure client-side logic, split out of kusanya.js (P3.8) purely
// so it can be unit-tested without a full jsdom-simulated page: these two
// functions have no side effects and no dependency on the rest of the
// script's DOM wiring. See static/js/kusanya-logic.test.js.
//
// UMD-lite export: a plain global in the browser (loaded before
// kusanya.js — see base.html/base_auth.html), CommonJS under Node/Vitest.
(function (root, factory) {
  const logic = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = logic;
  } else {
    root.KZLogic = logic;
  }
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  // Resolves a stored theme preference ("light" | "dark" | "system" | null)
  // to the theme that should actually be painted. Mirrors the synchronous
  // resolver in partials/theme_init.html exactly — keep the two in sync.
  function resolveTheme(choice, systemPrefersDark) {
    if (choice === "light" || choice === "dark") return choice;
    return systemPrefersDark ? "dark" : "light";
  }

  // True if a keydown's target is somewhere a "/" or "?" keystroke should
  // be typed literally rather than treated as a keyboard shortcut.
  function isTypingInField(target) {
    const tag = target && target.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || Boolean(target && target.isContentEditable);
  }

  return { resolveTheme: resolveTheme, isTypingInField: isTypingInField };
});
