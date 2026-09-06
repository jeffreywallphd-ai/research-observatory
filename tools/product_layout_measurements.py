"""Actual shared-flow and shell edges; declared CSS gaps alone are insufficient."""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any


def exercise_workflow_context_keyboard(page: Any) -> dict[str, int]:
    """Traverse real context actions with Tab, starting at the preceding control."""
    selector = "main > [data-workflow-context] button:visible"
    actions = page.locator(selector + ":not(:disabled)")
    result = {"buttonCount": page.locator(selector).count(), "enabledCount": actions.count(), "traversedCount": 0}
    if not actions.count():
        return result
    anchor = actions.first.evaluate_handle(r"""node => {
      const candidates = [...document.querySelectorAll('button,input,select,textarea,a[href],[tabindex],summary')]
        .filter(item => item.tabIndex >= 0 && !item.disabled && item.getClientRects().length
          && getComputedStyle(item).visibility === 'visible');
      return candidates[candidates.indexOf(node) - 1];
    }""")
    try:
        anchor.evaluate("node => node.focus()")
        for index in range(actions.count()):
            page.keyboard.press("Tab")
            action = actions.nth(index)
            if not action.evaluate("node => node === document.activeElement"):
                raise ValueError("workflow context action was skipped or disabled control received Tab focus")
            page.wait_for_function("parseFloat(getComputedStyle(document.activeElement).outlineWidth) >= 2")
            if not action.evaluate("""node => { const r = node.getBoundingClientRect();
              return r.top >= -.5 && r.bottom <= innerHeight + .5 && r.left >= -.5 && r.right <= innerWidth + .5;
            }"""):
                raise ValueError("workflow context keyboard target is not visible within the viewport")
            result["traversedCount"] += 1
    finally:
        anchor.dispose()
    return result


PANEL_FLOW_GEOMETRY = r"""element => {
  const visible = node => node.getClientRects().length && getComputedStyle(node).visibility === 'visible';
  return [...element.querySelectorAll('.ro-panel > div')].filter(visible).map(node => {
    const style = getComputedStyle(node), rect = node.getBoundingClientRect();
    const children = [...node.children].filter(child => visible(child)
      && !['absolute', 'fixed'].includes(getComputedStyle(child).position));
    return {
      display: style.display,
      singleColumn: style.gridTemplateColumns.trim().split(/\s+/).length === 1,
      gap: parseFloat(style.rowGap), top: rect.top, bottom: rect.bottom,
      paddingStart: parseFloat(style.paddingBlockStart), paddingEnd: parseFloat(style.paddingBlockEnd),
      borderStart: parseFloat(style.borderBlockStartWidth), borderEnd: parseFloat(style.borderBlockEndWidth),
      childCount: children.length,
      children: children.map(child => {
        const s = getComputedStyle(child), r = child.getBoundingClientRect();
        return {tag: child.tagName.toLowerCase(), top: r.top, bottom: r.bottom,
          marginStart: parseFloat(s.marginBlockStart), marginEnd: parseFloat(s.marginBlockEnd)};
      })
    };
  });
}"""

SHELL_GEOMETRY = r"""() => {
  const rect = selector => {
    const node = document.querySelector(selector);
    if (!node || !node.getClientRects().length) return null;
    const r = node.getBoundingClientRect();
    return {top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height, width: r.width};
  };
  return {stacked: matchMedia('(max-width: 50rem)').matches,
    sidebar: rect('.sidebar'), body: rect('.shell-body'), main: rect('main'), footer: rect('.trust-footer'),
    clientWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth};
}"""


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _near(left: float, right: float) -> bool:
    return abs(left - right) <= 0.5


def panel_flow_errors(flows: Any, *, require_paragraph_pair: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(flows, list):
        return ["panel flow measurements are missing"]
    paragraph_pair = False
    for index, flow in enumerate(flows):
        label = f"panel flow {index}"
        fields = ("gap", "top", "bottom", "paddingStart", "paddingEnd", "borderStart", "borderEnd")
        if not isinstance(flow, dict) or any(not _number(flow.get(key)) for key in fields):
            errors.append(f"{label} has missing or nonfinite geometry")
            continue
        if flow.get("display") != "grid" or not isinstance(flow.get("singleColumn"), bool):
            errors.append(f"{label} has no measured grid layout")
            continue
        children = flow.get("children")
        if (
            not isinstance(children, list)
            or type(flow.get("childCount")) is not int
            or flow["childCount"] != len(children)
        ):
            errors.append(f"{label} child inventory differs")
            continue
        if any(
            not isinstance(child, dict)
            or not isinstance(child.get("tag"), str)
            or any(not _number(child.get(key)) for key in ("top", "bottom", "marginStart", "marginEnd"))
            or child["bottom"] < child["top"]
            for child in children
        ):
            errors.append(f"{label} has invalid child geometry")
            continue
        if flow["bottom"] < flow["top"] or any(flow[key] < 0 for key in fields if key not in {"top", "bottom"}):
            errors.append(f"{label} has inverted edges or negative spacing")
            continue
        for child in children:
            if child["tag"] == "p" and (not _near(child["marginStart"], 0) or not _near(child["marginEnd"], 0)):
                errors.append(f"{label} paragraph margins escape shared spacing")
        # Multi-column composition is not a vertical stack. Its child margins
        # still have owners, but cross-column distances are not row gaps.
        if not flow["singleColumn"] or not children:
            continue
        first, last = children[0], children[-1]
        if not _near(first["top"] - flow["top"], flow["borderStart"] + flow["paddingStart"] + first["marginStart"]):
            errors.append(f"{label} first-child edge differs")
        if not _near(flow["bottom"] - last["bottom"], flow["borderEnd"] + flow["paddingEnd"] + last["marginEnd"]):
            errors.append(f"{label} last-child edge differs")
        for previous, child in pairwise(children):
            expected = flow["gap"] + previous["marginEnd"] + child["marginStart"]
            if not _near(child["top"] - previous["bottom"], expected):
                errors.append(f"{label} effective child distance differs from owned spacing")
            paragraph_pair |= previous["tag"] == child["tag"] == "p"
    if require_paragraph_pair and not paragraph_pair:
        errors.append("populated Task Center paragraph-pair coverage is missing")
    return errors


def shell_geometry_errors(shell: Any, *, stacked: bool) -> list[str]:
    if not isinstance(shell, dict) or shell.get("stacked") is not stacked:
        return ["shell layout mode is missing or incorrect"]
    for name in ("sidebar", "body", "main", "footer"):
        rect = shell.get(name)
        if not isinstance(rect, dict) or any(
            not _number(rect.get(key)) for key in ("top", "bottom", "left", "right", "height", "width")
        ):
            return [f"shell {name} has missing or nonfinite edges"]
        if (
            rect["height"] <= 0
            or rect["width"] <= 0
            or not _near(rect["bottom"] - rect["top"], rect["height"])
            or not _near(rect["right"] - rect["left"], rect["width"])
        ):
            return [f"shell {name} has inconsistent edges"]
    if any(not _number(shell.get(key)) for key in ("clientWidth", "scrollWidth")) or shell["clientWidth"] <= 0:
        return ["shell document width measurements are missing"]
    errors: list[str] = []
    if shell["scrollWidth"] > shell["clientWidth"] + 0.5:
        errors.append("shell escapes document width")
    sidebar, body, main, footer = (shell[name] for name in ("sidebar", "body", "main", "footer"))
    if not _near(body["bottom"], footer["top"]) or main["bottom"] > footer["top"] + 0.5:
        errors.append("shell content/footer boundary differs")
    if not _near(sidebar["top"], body["top"]):
        errors.append("sidebar does not start at the shell body")
    if stacked:
        if sidebar["bottom"] > main["top"] + 0.5:
            errors.append("stacked navigation overlaps content")
    elif not _near(sidebar["bottom"], footer["top"]) or sidebar["right"] > main["left"] + 0.5:
        errors.append("side-by-side sidebar does not reach the footer or overlaps content")
    return errors
