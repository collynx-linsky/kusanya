// Real unit tests for the pure logic split out of kusanya.js (P3.8).
// No DOM required for these -- see kusanya.dom.test.js for the
// jsdom-simulated integration tests of the rest of the script.
import { describe, it, expect } from "vitest";
import kzLogic from "./kusanya-logic.js";

const { resolveTheme, isTypingInField } = kzLogic;

describe("resolveTheme", () => {
  it("returns 'light' unchanged regardless of system preference", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("light", false)).toBe("light");
  });

  it("returns 'dark' unchanged regardless of system preference", () => {
    expect(resolveTheme("dark", true)).toBe("dark");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("falls through to the system preference for 'system'", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });

  it("treats a missing/unrecognized stored value the same as 'system'", () => {
    expect(resolveTheme(null, true)).toBe("dark");
    expect(resolveTheme(undefined, false)).toBe("light");
    expect(resolveTheme("", true)).toBe("dark");
  });
});

describe("isTypingInField", () => {
  it("is true for INPUT and TEXTAREA elements", () => {
    expect(isTypingInField({ tagName: "INPUT" })).toBe(true);
    expect(isTypingInField({ tagName: "TEXTAREA" })).toBe(true);
  });

  it("is true for contenteditable elements regardless of tag", () => {
    expect(isTypingInField({ tagName: "DIV", isContentEditable: true })).toBe(true);
  });

  it("is false for ordinary elements", () => {
    expect(isTypingInField({ tagName: "DIV" })).toBe(false);
    expect(isTypingInField({ tagName: "BUTTON", isContentEditable: false })).toBe(false);
  });

  it("does not throw on a null/undefined target", () => {
    expect(isTypingInField(null)).toBe(false);
    expect(isTypingInField(undefined)).toBe(false);
  });
});
