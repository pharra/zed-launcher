import {useState} from "react";
import {Button, Input, Label} from "@heroui/react";

import {useT} from "../lib/i18n";
import type {ExtraProgram} from "../lib/types";
import {ChevronDownIcon, FolderIcon, PlusIcon, TrashIcon} from "./icons";
import {PathBrowser} from "./PathBrowser";

interface LaunchOrderProps {
  gamePath: string;
  entries: ExtraProgram[];
  onChange: (entries: ExtraProgram[]) => void;
}

function blankProgram(): ExtraProgram {
  return {kind: "program", path: "", args: "", delay: 0};
}

/** Game entries always come from the game record; keep exactly one, wherever it sits. */
export function withGameRow(entries: ExtraProgram[], gamePath: string): ExtraProgram[] {
  let placed = false;
  const rows = entries.map((entry) => {
    if (entry.kind !== "game") return entry;
    if (placed) return null;
    placed = true;
    return {kind: "game" as const, path: gamePath, args: "", delay: 0};
  });
  const kept = rows.filter((row): row is ExtraProgram => row !== null);
  return placed ? kept : [...kept, {kind: "game", path: gamePath, args: "", delay: 0}];
}

export function LaunchOrder({gamePath, entries, onChange}: LaunchOrderProps) {
  const {t} = useT();
  const [browseIndex, setBrowseIndex] = useState<number | null>(null);

  function replace(index: number, patch: Partial<ExtraProgram>) {
    onChange(entries.map((entry, position) => (position === index ? {...entry, ...patch} : entry)));
  }

  function move(from: number, to: number) {
    if (to < 0 || to >= entries.length || from === to) return;
    const next = [...entries];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    onChange(next);
  }

  function remove(index: number) {
    onChange(entries.filter((_, position) => position !== index));
  }

  function add() {
    onChange([...entries, blankProgram()]);
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <p className="text-xs leading-snug text-muted">
        {t(
          "Programs start in this order — rows below the game start as soon as the game is up. Use the arrows to reorder. Everything runs in one umu-run container, so the extra programs share the game's wine session.",
          "程序按此顺序启动，游戏行之后的程序会在游戏起来后立即启动。使用箭头调整顺序。全部程序在同一个 umu-run 容器里运行，因此额外程序与游戏共享同一个 wine 会话。",
        )}
      </p>

      <div className="flex flex-col gap-2">
        {entries.map((entry, index) => {
          const isGame = entry.kind === "game";
          return (
            <div
              key={`${entry.kind}-${index}`}
              className={`flex min-w-0 flex-col gap-2 rounded-xl border px-3 py-2.5 transition ${
                isGame ? "border-accent/40 bg-accent/5" : "border-border/50 bg-surface/40"
              }`}
            >
              <div className="flex min-w-0 items-center gap-2">
                <span className="shrink-0 rounded-md bg-surface px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-muted">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium">
                  {isGame
                    ? t("The game itself", "游戏自身")
                    : t("Extra program", "额外程序")}
                </span>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    isIconOnly
                    size="sm"
                    variant="ghost"
                    aria-label={t("Move up", "上移")}
                    isDisabled={index === 0}
                    onPress={() => move(index, index - 1)}
                  >
                    <ChevronDownIcon className="size-4 rotate-180" />
                  </Button>
                  <Button
                    isIconOnly
                    size="sm"
                    variant="ghost"
                    aria-label={t("Move down", "下移")}
                    isDisabled={index === entries.length - 1}
                    onPress={() => move(index, index + 1)}
                  >
                    <ChevronDownIcon className="size-4" />
                  </Button>
                  <Button
                    isIconOnly
                    size="sm"
                    variant="ghost"
                    aria-label={t("Remove program", "移除程序")}
                    isDisabled={isGame}
                    onPress={() => remove(index)}
                  >
                    <TrashIcon className="size-4" />
                  </Button>
                </div>
              </div>

              {isGame ? (
                <span className="min-w-0 font-mono text-[11px] break-all text-muted">
                  {gamePath || t("Choose the executable on the General tab", "请在“常规”标签选择可执行文件")}
                </span>
              ) : (
                <div className="flex min-w-0 flex-col gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <Input
                      aria-label={t("Program path", "程序路径")}
                      className="min-w-0 flex-1"
                      placeholder="/home/you/Games/trainer.exe"
                      value={entry.path}
                      onChange={(event) => replace(index, {path: event.target.value})}
                    />
                    <Button
                      isIconOnly
                      variant="secondary"
                      aria-label={t("Browse for program", "浏览程序")}
                      onPress={() => setBrowseIndex(index)}
                    >
                      <FolderIcon className="size-4" />
                    </Button>
                  </div>
                  <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <Label className="text-[11px] text-muted">
                        {t("Arguments", "参数")}
                      </Label>
                      <Input
                        aria-label={t("Program arguments", "程序参数")}
                        placeholder="--flag value"
                        value={entry.args}
                        onChange={(event) => replace(index, {args: event.target.value})}
                      />
                    </div>
                    <div className="flex w-full flex-col gap-1 sm:w-40">
                      <Label className="text-[11px] text-muted">
                        {t("Delay (seconds)", "延时（秒）")}
                      </Label>
                      <Input
                        aria-label={t("Delay before starting", "启动前延时")}
                        type="number"
                        value={String(entry.delay)}
                        onChange={(event) =>
                          replace(index, {delay: Math.max(0, Number(event.target.value) || 0)})
                        }
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <Button className="self-start" variant="secondary" onPress={add}>
        <PlusIcon className="size-4" />
        {t("Add program", "添加程序")}
      </Button>

      <PathBrowser
        open={browseIndex !== null}
        mode="file"
        initialPath={browseIndex === null ? undefined : entries[browseIndex]?.path}
        onClose={() => setBrowseIndex(null)}
        onSelect={(path) => {
          if (browseIndex !== null) replace(browseIndex, {path});
          setBrowseIndex(null);
        }}
      />
    </div>
  );
}
