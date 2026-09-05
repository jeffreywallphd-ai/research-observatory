import type { Ref } from "react";

import { Button } from "./index";

export interface DirectoryPickerFieldProps {
  readonly id: string;
  readonly label: string;
  readonly description: string;
  readonly value: string;
  readonly onChoose: () => void;
  readonly disabled?: boolean;
  readonly pending?: boolean;
  readonly buttonRef?: Ref<HTMLButtonElement>;
}

/** A presentation-only field; the application owns selection and authority. */
export function DirectoryPickerField({
  id, label, description, value, onChoose, disabled = false, pending = false, buttonRef,
}: DirectoryPickerFieldProps) {
  if (!id.trim() || !label.trim() || !description.trim()) throw new TypeError("Folder fields require a label and help.");
  return (
    <div id={id} className="ro-field" role="group" aria-labelledby={`${id}-label`} aria-busy={pending || undefined}>
      <span id={`${id}-label`} className="ro-field__label">{label}</span>
      <span id={`${id}-description`} className="ro-field__description">{description}</span>
      <output id={`${id}-location`} className="ro-directory-location" aria-labelledby={`${id}-label`}>
        {value || "No folder selected"}
      </output>
      <div className="ro-action-row">
        <Button ref={buttonRef ?? null} id={`${id}-choose`} disabled={disabled || pending} onClick={onChoose}
          aria-label={`${value ? "Change folder…" : "Choose folder…"} — ${label}`}
          aria-describedby={`${id}-description ${id}-location`}>
          {value ? "Change folder…" : "Choose folder…"}
        </Button>
      </div>
    </div>
  );
}
