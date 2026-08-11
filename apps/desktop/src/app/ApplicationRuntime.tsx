import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { Button, Field, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

export type ApplicationTheme = "light" | "dark";

export interface ShortcutDefinition {
  readonly id: "command" | "help" | "home";
  readonly keys: string;
  readonly label: string;
}

export const SHORTCUTS: readonly ShortcutDefinition[] = Object.freeze([
  { id: "command", keys: "Ctrl+K", label: "Focus the command search" },
  { id: "help", keys: "Ctrl+/", label: "Open keyboard shortcuts" },
  { id: "home", keys: "Alt+H", label: "Move focus to the project home" },
]);

export function nextTheme(theme: ApplicationTheme): ApplicationTheme {
  return theme === "light" ? "dark" : "light";
}

export function storedTheme(storage: Pick<Storage, "getItem"> | null): ApplicationTheme {
  if (!storage) return "light";
  try {
    return storage.getItem("research-observatory.theme") === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function isShortcut(event: KeyboardEvent, key: string, modifier: "ctrl" | "alt"): boolean {
  return event.key.toLowerCase() === key && (modifier === "ctrl" ? event.ctrlKey : event.altKey)
    && !event.metaKey && !(modifier === "ctrl" && event.altKey) && !(modifier === "alt" && event.ctrlKey);
}

interface CommandDefinition {
  readonly id: string;
  readonly label: string;
  readonly description: string;
  readonly run: () => void;
}

export function ApplicationRuntime(): ReactNode {
  const [theme, setTheme] = useState<ApplicationTheme>(() => storedTheme(globalThis.window?.localStorage ?? null));
  const [query, setQuery] = useState("");
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [announcement, setAnnouncement] = useState("Desktop shell ready. No project is open.");
  const commandRef = useRef<HTMLInputElement>(null);
  const homeRef = useRef<HTMLElement>(null);
  const shortcutTriggerRef = useRef<HTMLButtonElement>(null);
  const shortcutCloseRef = useRef<HTMLButtonElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  const announce = useCallback((message: string) => {
    setAnnouncement("");
    globalThis.window?.requestAnimationFrame(() => setAnnouncement(message));
  }, []);

  const applyTheme = useCallback((next: ApplicationTheme) => {
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem("research-observatory.theme", next);
    } catch {
      // Theme persistence is optional; the in-memory selection remains usable.
    }
    announce(`${next === "dark" ? "Dark" : "Light"} theme active.`);
  }, [announce]);

  const openShortcuts = useCallback((trigger?: HTMLElement | null) => {
    restoreFocusRef.current = trigger ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    setShortcutsOpen(true);
  }, []);

  const closeShortcuts = useCallback(() => {
    setShortcutsOpen(false);
    const restore = restoreFocusRef.current;
    globalThis.window?.requestAnimationFrame(() => restore?.focus());
  }, []);

  const containShortcutFocus = useCallback((event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key !== "Tab") return;
    event.preventDefault();
    shortcutCloseRef.current?.focus();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.body.dataset.applicationReady = "true";
    return () => {
      delete document.body.dataset.applicationReady;
    };
  }, [theme]);

  useEffect(() => {
    if (shortcutsOpen) shortcutCloseRef.current?.focus();
  }, [shortcutsOpen]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (isShortcut(event, "k", "ctrl")) {
        event.preventDefault();
        commandRef.current?.focus();
      } else if (isShortcut(event, "/", "ctrl")) {
        event.preventDefault();
        openShortcuts();
      } else if (isShortcut(event, "h", "alt")) {
        event.preventDefault();
        homeRef.current?.focus();
      } else if (event.key === "Escape" && shortcutsOpen) {
        event.preventDefault();
        closeShortcuts();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [closeShortcuts, openShortcuts, shortcutsOpen]);

  const commands = useMemo<readonly CommandDefinition[]>(() => [
    {
      id: "toggle-theme",
      label: "Toggle color theme",
      description: "Switch between the approved light and dark themes.",
      run: () => applyTheme(nextTheme(theme)),
    },
    {
      id: "keyboard-shortcuts",
      label: "Show keyboard shortcuts",
      description: "Open the keyboard command reference.",
      run: () => openShortcuts(commandRef.current),
    },
  ], [applyTheme, openShortcuts, theme]);
  const normalizedQuery = query.trim().toLowerCase();
  const visibleCommands = commands.filter(({ label, description }) =>
    !normalizedQuery || `${label} ${description}`.toLowerCase().includes(normalizedQuery));

  return (
    <div className="application-shell" data-application-ready="true">
      <a className="skip-link" href="#main-content" onClick={() => homeRef.current?.focus()}>Skip to project home</a>
      <header className="topbar" aria-label="Application">
        <a className="brand" href="#main-content" onClick={() => homeRef.current?.focus()} aria-label="Research Observatory project home">
          <span className="brand-mark" aria-hidden="true">RO</span>
          <span>Research Observatory</span>
        </a>
        <div className="topbar-actions">
          <span className="project-context" data-project-context>No project open</span>
          <Button ref={shortcutTriggerRef} onClick={() => openShortcuts(shortcutTriggerRef.current)} aria-haspopup="dialog" data-shortcut-help>
            Shortcuts
          </Button>
          <Button onClick={() => applyTheme(nextTheme(theme))} aria-pressed={theme === "dark"} data-theme-toggle>
            {theme === "dark" ? "Use light theme" : "Use dark theme"}
          </Button>
        </div>
      </header>

      <div className="shell-body">
        <aside className="sidebar" aria-label="Available workspaces">
          <nav>
            <a href="#main-content" aria-current="page" onClick={() => homeRef.current?.focus()}>Project home</a>
          </nav>
          <p>Only implemented capabilities appear here.</p>
        </aside>

        <main id="main-content" ref={homeRef} tabIndex={-1}>
          <div className="page-header">
            <Typography as="h1" variant="page-title">Desktop foundation</Typography>
            <Typography className="page-subtitle">
              A local, offline application shell. Research workspaces appear only when their capability is implemented.
            </Typography>
          </div>

          <section className="command-area" aria-labelledby="command-title">
            <Typography id="command-title" as="h2" variant="section-title">Application commands</Typography>
            <Field
              id="shell-command"
              label="Find a command"
              description="Press Ctrl+K from anywhere in the application."
              inputRef={commandRef}
              input={{
                type: "search",
                value: query,
                onChange: (event) => setQuery(event.currentTarget.value),
                autoComplete: "off",
              }}
            />
            <ul className="command-results" aria-label="Matching commands">
              {visibleCommands.map((command) => (
                <li key={command.id}>
                  <Button data-command-id={command.id} onClick={command.run}>{command.label}</Button>
                  <span>{command.description}</span>
                </li>
              ))}
            </ul>
            {visibleCommands.length === 0 ? <p role="status">No application commands match.</p> : null}
          </section>

          <div className="status-grid">
            <Panel title="Desktop shell" tone="success">
              <StatusBadge tone="success">Ready</StatusBadge>
              <p>The signed-development Tauri window and React renderer are running locally.</p>
            </Panel>
            <Panel title="Local service" tone="neutral">
              <StatusBadge>Not started</StatusBadge>
              <p>The supervised analytical service will appear here when CAP-01.S03 is implemented.</p>
            </Panel>
          </div>
        </main>
      </div>

      <footer className="trust-footer" data-trust-footer>
        This shell runs locally and makes no network requests. Reference prototypes and illustrative research data are not shipped as application screens.
      </footer>

      <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true" data-live-region>{announcement}</div>

      {shortcutsOpen ? (
        <div className="dialog-backdrop" role="presentation">
          <section
            className="shortcut-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="shortcut-title"
            onKeyDown={containShortcutFocus}
          >
            <Typography id="shortcut-title" as="h2" variant="section-title">Keyboard shortcuts</Typography>
            <dl>
              {SHORTCUTS.map((shortcut) => (
                <div key={shortcut.id}><dt><kbd>{shortcut.keys}</kbd></dt><dd>{shortcut.label}</dd></div>
              ))}
            </dl>
            <Button ref={shortcutCloseRef} tone="primary" onClick={closeShortcuts}>Close shortcuts</Button>
          </section>
        </div>
      ) : null}
    </div>
  );
}
