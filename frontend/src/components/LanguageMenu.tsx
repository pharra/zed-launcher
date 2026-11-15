import {Dropdown} from "@heroui/react";

import {LANGUAGES, useT, type Lang, type LangChoice} from "../lib/i18n";

interface LanguageMenuProps {
  value: Lang;
  onChange: (lang: LangChoice) => void;
}

export function LanguageMenu({value, onChange}: LanguageMenuProps) {
  const {t} = useT();
  const current = LANGUAGES.find((entry) => entry.value === value) ?? LANGUAGES[0];

  return (
    <Dropdown>
      <Dropdown.Trigger
        aria-label={t("Language", "语言")}
        className="button button--tertiary button--sm inline-flex items-center gap-1"
      >
        {current.short}
        <svg aria-hidden className="size-3.5 opacity-70" fill="none" viewBox="0 0 24 24">
          <path
            d="m6 9 6 6 6-6"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
          />
        </svg>
      </Dropdown.Trigger>
      <Dropdown.Popover>
        <Dropdown.Menu
          aria-label={t("Language", "语言")}
          selectedKeys={[value]}
          selectionMode="single"
          onAction={(key) => onChange(String(key) as LangChoice)}
        >
          {LANGUAGES.map((entry) => (
            <Dropdown.Item key={entry.value} id={entry.value} textValue={entry.label}>
              {entry.label}
              <Dropdown.ItemIndicator />
            </Dropdown.Item>
          ))}
        </Dropdown.Menu>
      </Dropdown.Popover>
    </Dropdown>
  );
}
