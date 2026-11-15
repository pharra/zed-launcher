import {useEffect, useState} from "react";
import {Button, Chip, Modal, ScrollShadow, Spinner, toast} from "@heroui/react";

import {api, artworkUrl, formatDate, formatPlaytime} from "../lib/api";
import {useT} from "../lib/i18n";
import {statusLabel} from "../lib/status";
import type {Game, RunRecord} from "../lib/types";
import {ExternalIcon, ImageIcon, PlayIcon, SearchIcon, TerminalIcon, TrashIcon} from "./icons";
import {SgdbPicker} from "./SgdbPicker";

interface GameDetailsProps {
  game: Game | null;
  running: boolean;
  onClose: () => void;
  onPlay: (game: Game) => void;
  onTools: (game: Game) => void;
  onDelete: (game: Game) => void;
  onChanged: () => void;
}

const statusColor = (status: string): "success" | "warning" | "danger" | "default" => {
  if (status === "running" || status === "starting") return "success";
  if (status === "failed") return "danger";
  if (status === "stopped" || status === "closed" || status === "unknown") return "warning";
  return "default";
};

function formatDuration(seconds: number | null): string {
  if (!seconds) return "—";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${seconds}s`;
}

export function GameDetails({
  game,
  running,
  onClose,
  onPlay,
  onTools,
  onDelete,
  onChanged,
}: GameDetailsProps) {
  const {lang, t} = useT();
  const [runs, setRuns] = useState<RunRecord[] | null>(null);
  const [sgdbOpen, setSgdbOpen] = useState(false);
  const [extracting, setExtracting] = useState(false);

  useEffect(() => {
    if (!game) return;
    setRuns(null);
    api
      .gameRuns(game.id, 12)
      .then(setRuns)
      .catch((error: Error) => {
        setRuns([]);
        toast.danger(t("Could not load the run history", "无法加载运行历史"), {description: error.message});
      });
  }, [game]);

  async function extractIcon() {
    if (!game) return;
    setExtracting(true);
    try {
      await api.extractIcon(game.id);
      toast.success(t("Icon extracted", "图标已提取"));
      onChanged();
    } catch (error) {
      toast.danger(t("Could not extract an icon", "无法提取图标"), {
        description: String((error as Error).message),
      });
    } finally {
      setExtracting(false);
    }
  }

  async function openLog(path: string) {
    try {
      await api.openPath(path);
    } catch (error) {
      toast.danger(t("Could not open the log", "无法打开日志"), {description: String((error as Error).message)});
    }
  }

  return (
    <Modal.Backdrop isOpen={game !== null} onOpenChange={(value) => !value && onClose()}>
      <Modal.Container size="lg">
        <Modal.Dialog className="max-h-[88vh]">
          <Modal.CloseTrigger />
          <Modal.Header>
            <Modal.Heading>{game?.title}</Modal.Heading>
            {running && (
              <Chip size="sm" color="success" variant="soft" className="text-[10px]">
                {t("running", "运行中")}
              </Chip>
            )}
          </Modal.Header>
          <Modal.Body className="gap-4 overflow-y-auto">
            <div className="grid gap-2 sm:grid-cols-3">
              <div className="flex flex-col rounded-xl border border-border/50 bg-surface/40 px-3 py-2">
                <span className="text-[11px] text-muted">{t("Playtime", "游玩时长")}</span>
                <span className="text-sm">{formatPlaytime(game?.playtime ?? 0, lang === "zh")}</span>
              </div>
              <div className="flex flex-col rounded-xl border border-border/50 bg-surface/40 px-3 py-2">
                <span className="text-[11px] text-muted">{t("Last played", "最近游玩")}</span>
                <span className="text-sm">{formatDate(game?.last_played ?? null, lang)}</span>
              </div>
              <div className="flex flex-col rounded-xl border border-border/50 bg-surface/40 px-3 py-2">
                <span className="text-[11px] text-muted">{t("Prefix", "Prefix")}</span>
                <span className="truncate text-sm" title={game?.prefix_path}>
                  {game?.prefix_path.split("/").filter(Boolean).pop() ?? "—"}
                  {game && !game.owned_prefix ? " · shared" : ""}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3 rounded-xl border border-border/50 bg-surface/40 p-3">
              <div className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-surface-secondary">
                {game?.cover ? (
                  <img alt="" className="size-full object-cover" src={artworkUrl(game.cover)} />
                ) : game?.icon ? (
                  <img alt="" className="size-10 object-contain" src={artworkUrl(game.icon)} />
                ) : (
                  <ImageIcon className="size-6 text-muted" />
                )}
              </div>
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="text-sm font-medium">{t("Artwork", "封面与图标")}</span>
                <span className="text-[11px] text-muted">
                  {game?.cover
                    ? t("Custom cover", "自定义封面")
                    : t("No cover — showing the extracted icon", "无封面 — 显示提取的图标")}
                </span>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button size="sm" variant="secondary" onPress={() => setSgdbOpen(true)}>
                  <SearchIcon className="size-3.5" />
                  SteamGridDB
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  isDisabled={extracting}
                  onPress={() => void extractIcon()}
                >
                  <ImageIcon className="size-3.5" />
                  {extracting ? t("Extracting…", "提取中…") : t("Extract icon", "提取图标")}
                </Button>
              </div>
            </div>

            <div className="flex flex-col gap-1 rounded-xl border border-border/50 bg-surface/40 p-3 text-[11px]">
              <span className="text-muted">{t("Executable", "可执行文件")}</span>
              <span className="break-all font-mono">{game?.path}</span>
              <span className="mt-1 text-muted">{t("Proton", "Proton")}</span>
              <span className="break-all font-mono">{game?.proton_path || "Default build"}</span>
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{t("Recent runs", "最近运行")}</span>
                <span className="text-[11px] text-muted">{t("Newest first", "最新在前")}</span>
              </div>
              {runs === null ? (
                <div className="flex items-center gap-2 py-6 text-sm text-muted">
                  <Spinner size="sm" />
                  {t("Loading…", "加载中…")}
                </div>
              ) : runs.length === 0 ? (
                <p className="rounded-xl bg-surface/50 px-4 py-6 text-center text-sm text-muted">
                  {t("This game has not been launched yet.", "这款游戏还没有启动过。")}
                </p>
              ) : (
                <ScrollShadow className="max-h-[30vh] rounded-xl border border-border/50 bg-surface/40 p-1">
                  <div className="flex flex-col">
                    {runs.map((run) => (
                      <div
                        key={run.id}
                        className="flex items-center gap-2 rounded-lg px-3 py-2 hover:bg-surface-secondary"
                      >
                        <Chip size="sm" color={statusColor(run.status)} variant="soft" className="text-[10px]">
                          {statusLabel(run.status, t)}
                        </Chip>
                        <span className="flex flex-1 flex-col">
                          <span className="text-xs">{formatDate(run.started_at, lang)}</span>
                          <span className="text-[10px] text-muted">
                            {formatDuration(run.duration)}
                            {run.exit_code !== null && run.exit_code !== undefined
                              ? ` · exit ${run.exit_code}`
                              : ""}
                          </span>
                        </span>
                        <Button
                          size="sm"
                          variant="tertiary"
                          aria-label={t("Open log", "打开日志")}
                          onPress={() => void openLog(run.log_path)}
                        >
                          <ExternalIcon className="size-3.5" />
                          {t("Log", "日志")}
                        </Button>
                      </div>
                    ))}
                  </div>
                </ScrollShadow>
              )}
            </div>
          </Modal.Body>
          <Modal.Footer className="justify-between">
            <Button variant="tertiary" onPress={() => game && onDelete(game)}>
              <TrashIcon className="size-4" />
              {t("Remove", "移除")}
            </Button>
            <div className="flex gap-2">
              <Button variant="secondary" slot="close">
                {t("Close", "关闭")}
              </Button>
              <Button variant="secondary" onPress={() => game && onTools(game)}>
                <TerminalIcon className="size-4" />
                {t("Prefix tools", "Prefix 工具")}
              </Button>
              <Button onPress={() => game && onPlay(game)}>
                {running ? <TerminalIcon className="size-4" /> : <PlayIcon className="size-4" />}
                {running ? t("Log", "日志") : t("Play", "开始游戏")}
              </Button>
            </div>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>

      <SgdbPicker
        open={sgdbOpen}
        game={game}
        onClose={() => setSgdbOpen(false)}
        onApplied={onChanged}
      />
    </Modal.Backdrop>
  );
}
