import {Button, Card, Chip, Tooltip} from "@heroui/react";

import {artworkUrl, formatPlaytime} from "../lib/api";
import {useT} from "../lib/i18n";
import type {Game} from "../lib/types";
import {
  GamepadIcon,
  LinkIcon,
  PencilIcon,
  PlayIcon,
  StopIcon,
  TerminalIcon,
  TrashIcon,
  UnlinkIcon,
} from "./icons";

interface GameCardProps {
  game: Game;
  protonLabel: string;
  running: boolean;
  onPlay: (game: Game) => void;
  onShowLog: (game: Game) => void;
  onStop: (game: Game) => void;
  onEdit: (game: Game) => void;
  onDelete: (game: Game) => void;
  onShortcut: (game: Game) => void;
  onTools: (game: Game) => void;
  onDetails: (game: Game) => void;
}

const gradients = [
  "from-sky-500/30 via-indigo-500/20 to-fuchsia-500/30",
  "from-emerald-500/30 via-teal-500/20 to-cyan-500/30",
  "from-amber-500/30 via-orange-500/20 to-rose-500/30",
  "from-violet-500/30 via-purple-500/20 to-pink-500/30",
];

function gradientFor(id: string) {
  let hash = 0;
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) % gradients.length;
  return gradients[hash];
}

export function GameCard({
  game,
  protonLabel,
  running,
  onPlay,
  onShowLog,
  onStop,
  onEdit,
  onDelete,
  onShortcut,
  onTools,
  onDetails,
}: GameCardProps) {
  const {lang, t} = useT();
  const initials = game.title.slice(0, 2).toUpperCase();
  const prefixName = game.prefix_path.split("/").filter(Boolean).pop() ?? "prefix";

  return (
    <Card className="group overflow-hidden border border-border/50 bg-surface/70 p-2 transition-shadow hover:shadow-xl">
      <button
        type="button"
        className={`relative aspect-[3/4] w-full overflow-hidden rounded-xl bg-gradient-to-br ${gradientFor(game.id)}`}
        onClick={() => (running ? onShowLog(game) : onPlay(game))}
      >
        {game.cover ? (
          <img alt="" className="absolute inset-0 size-full object-cover" loading="lazy" src={artworkUrl(game.cover)} />
        ) : (
          <span className="absolute inset-0 flex items-center justify-center text-5xl font-semibold text-foreground/70">
            {game.icon ? (
              <img alt="" className="size-16 object-contain drop-shadow" loading="lazy" src={artworkUrl(game.icon)} />
            ) : (
              initials
            )}
          </span>
        )}
        <span className="absolute inset-0 flex items-center justify-center bg-black/45 opacity-0 backdrop-blur-[2px] transition-opacity group-hover:opacity-100">
          <span className="flex size-14 items-center justify-center rounded-full bg-accent text-accent-foreground shadow-lg">
            <PlayIcon className="size-6 translate-x-[1px]" />
          </span>
        </span>
        {running && (
          <span className="absolute start-2 top-2 flex items-center gap-1 rounded-full bg-success/90 px-2 py-0.5 text-[10px] font-medium text-success-foreground">
            <span className="size-1.5 animate-pulse rounded-full bg-current" />
            {t("Running", "运行中")}
          </span>
        )}
      </button>

      <Card.Header className="gap-1 px-1 pb-1 pt-3">
        <Card.Title className="truncate text-sm">
          <button
            type="button"
            className="w-full truncate text-start hover:underline"
            title={`${game.title} — show details`}
            onClick={() => onDetails(game)}
          >
            {game.title}
          </button>
        </Card.Title>
        <Card.Description className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px]">
          <Chip size="sm" variant="soft" className="h-5 px-2 text-[10px]">
            {protonLabel}
          </Chip>
          <span>{formatPlaytime(game.playtime, lang === "zh")}</span>
        </Card.Description>
      </Card.Header>

      <Card.Footer className="flex-col items-stretch gap-1 px-1 pb-1 pt-1">
        <div className="flex min-w-0 gap-1">
          {running ? (
            <>
              <Button
                size="sm"
                variant="secondary"
                className="min-w-0 flex-1 truncate px-2"
                onPress={() => onShowLog(game)}
              >
                <TerminalIcon className="size-3.5 shrink-0" />
                <span className="truncate">{t("Log", "日志")}</span>
              </Button>
              <Button
                size="sm"
                variant="danger-soft"
                className="min-w-0 flex-1 truncate px-2"
                aria-label={t("Stop the game", "终止游戏")}
                onPress={() => onStop(game)}
              >
                <StopIcon className="size-3.5 shrink-0" />
                <span className="truncate">{t("Stop", "终止")}</span>
              </Button>
            </>
          ) : (
            <Button size="sm" className="min-w-0 flex-1 truncate px-2" onPress={() => onPlay(game)}>
              <PlayIcon className="size-3.5 shrink-0" />
              <span className="truncate">{t("Play", "开始游戏")}</span>
            </Button>
          )}
          <Tooltip>
            <Tooltip.Trigger>
              <Button
                isIconOnly
                size="sm"
                variant="secondary"
                aria-label={t("Prefix tools", "Prefix 工具")}
                onPress={() => onTools(game)}
              >
                <GamepadIcon className="size-4" />
              </Button>
            </Tooltip.Trigger>
            <Tooltip.Content>
              {t("Prefix tools — winecfg, regedit, winetricks", "Prefix 工具 — winecfg、regedit、winetricks")}
            </Tooltip.Content>
          </Tooltip>
        </div>

        {/* Below the primary actions, so a running game never squeezes them out. */}
        <div className="flex min-w-0 gap-1">
          <Tooltip>
            <Tooltip.Trigger>
              <Button isIconOnly size="sm" variant="ghost" aria-label={t("Edit", "编辑")} onPress={() => onEdit(game)}>
                <PencilIcon className="size-4" />
              </Button>
            </Tooltip.Trigger>
            <Tooltip.Content>{t("Edit", "编辑")}</Tooltip.Content>
          </Tooltip>
          <Tooltip>
            <Tooltip.Trigger>
              <Button
                isIconOnly
                size="sm"
                variant="ghost"
                aria-label={
                  game.shortcut
                    ? t("Remove shortcut", "删除快捷方式")
                    : t("Create shortcut", "创建快捷方式")
                }
                onPress={() => onShortcut(game)}
              >
                {game.shortcut ? <UnlinkIcon className="size-4" /> : <LinkIcon className="size-4" />}
              </Button>
            </Tooltip.Trigger>
            <Tooltip.Content>
              {game.shortcut
                ? t("Remove the application shortcut", "删除已创建的应用快捷方式")
                : t("Create an application shortcut", "创建应用快捷方式")}
            </Tooltip.Content>
          </Tooltip>
          <Tooltip>
            <Tooltip.Trigger>
              <Button
                isIconOnly
                size="sm"
                variant="ghost"
                aria-label={t("Remove", "移除")}
                onPress={() => onDelete(game)}
              >
                <TrashIcon className="size-4" />
              </Button>
            </Tooltip.Trigger>
            <Tooltip.Content>{t("Remove", "移除")}</Tooltip.Content>
          </Tooltip>
        </div>
      </Card.Footer>

      <button
        type="button"
        className="flex min-w-0 items-center gap-1 rounded-lg px-2 pb-1 pt-0.5 text-[10px] text-muted transition-colors hover:bg-surface-secondary hover:text-foreground"
        onClick={() => onTools(game)}
        title={`${game.prefix_path} — ${t("open prefix tools", "打开 prefix 工具")}`}
      >
        <GamepadIcon className="size-3 shrink-0" />
        <span className="truncate">{prefixName}</span>
        {!game.owned_prefix && <span className="shrink-0">{t("· shared", "· 共享")}</span>}
      </button>
    </Card>
  );
}
