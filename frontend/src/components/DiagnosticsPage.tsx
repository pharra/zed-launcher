import {Button, Card, Chip, Spinner, toast} from "@heroui/react";

import {api} from "../lib/api";
import {useT} from "../lib/i18n";
import {sourceLabel} from "../lib/status";
import type {Info} from "../lib/types";
import {AlertIcon, CheckIcon, CpuIcon, DiskIcon, ExternalIcon, RefreshIcon, TerminalIcon} from "./icons";

interface DiagnosticsPageProps {
  info: Info | null;
  onRefresh: () => void;
}

function StatusRow({label, value}: {label: string; value: string | null}) {
  const {t} = useT();
  const ok = Boolean(value);
  const display = value === "available" ? t("available", "可用") : value;
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/40 py-2 last:border-0">
      <span className="text-sm">{label}</span>
      <span className={`flex items-center gap-1.5 text-xs ${ok ? "text-success" : "text-warning"}`}>
        {ok ? <CheckIcon className="size-3.5" /> : <AlertIcon className="size-3.5" />}
        <span className="max-w-[320px] truncate" title={display ?? t("Not found", "未找到")}>
          {display ?? t("Not found", "未找到")}
        </span>
      </span>
    </div>
  );
}

export function DiagnosticsPage({info, onRefresh}: DiagnosticsPageProps) {
  const {t} = useT();
  async function open(path: string) {
    try {
      await api.openPath(path);
    } catch (error) {
      toast.danger(t("Could not open the folder", "无法打开文件夹"), {
        description: String((error as Error).message),
      });
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">{t("System diagnostics", "系统诊断")}</h2>
          <p className="text-sm text-muted">
            {t(
              "Runtime, graphics and storage detected by the launcher.",
              "启动器检测到的运行环境、显卡与存储信息。",
            )}
          </p>
        </div>
        <Button variant="secondary" onPress={onRefresh}>
          <RefreshIcon className="size-4" />
          {t("Refresh", "刷新")}
        </Button>
      </div>

      {!info ? (
        <div className="flex items-center gap-2 py-16 text-sm text-muted">
          <Spinner size="sm" />
          {t("Loading…", "加载中…")}
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="p-4">
            <Card.Header className="flex-row items-center gap-2 p-0">
              <TerminalIcon className="size-4 text-accent" />
              <Card.Title className="text-sm">{t("Runtime", "运行环境")}</Card.Title>
            </Card.Header>
            <Card.Content className="mt-2 p-0">
              <StatusRow label="umu-run" value={info.tools.umu_run} />
              <StatusRow label="MangoHud" value={info.tools.mangohud} />
              <StatusRow label="GameMode" value={info.tools.gamemoderun} />
              <StatusRow label="Gamescope" value={info.tools.gamescope} />
              <StatusRow label="kwin_wayland" value={info.tools.kwin} />
              <StatusRow
                label="wp_single_pixel_buffer_manager_v1"
                value={
                  info.tools.kwin_session?.wayland === false
                    ? t("X11 session — not needed", "X11 会话 — 不需要")
                    : info.tools.kwin_session?.supported
                      ? t("available — nested KWin can start", "可用 — 嵌套 KWin 可以启动")
                      : t("missing — nested KWin cannot start", "缺失 — 嵌套 KWin 无法启动")
                }
              />
              <StatusRow label="dbus-run-session" value={info.tools.dbus_run_session} />
              <StatusRow label="systemd-inhibit" value={info.tools.systemd_inhibit} />
              <StatusRow label="notify-send" value={info.tools.notify_send} />
              <StatusRow label="icoextract" value={info.tools.icoextract} />
            </Card.Content>
          </Card>

          <Card className="p-4">
            <Card.Header className="flex-row items-center gap-2 p-0">
              <CpuIcon className="size-4 text-accent" />
              <Card.Title className="text-sm">{t("Graphics", "显卡")}</Card.Title>
            </Card.Header>
            <Card.Content className="mt-2 flex flex-col gap-2 p-0">
              {info.gpus.length === 0 && (
                <p className="text-sm text-muted">{t("No DRM devices detected.", "未检测到 DRM 设备。")}</p>
              )}
              {info.gpus.map((gpu) => (
                <div key={gpu.card} className="flex items-center justify-between rounded-xl bg-surface/50 px-3 py-2">
                  <span className="text-sm">{gpu.card}</span>
                  <Chip size="sm" variant="soft" className="font-mono text-[10px]">
                    {gpu.vendor}:{gpu.device}
                  </Chip>
                </div>
              ))}
            </Card.Content>
          </Card>

          <Card className="p-4">
            <Card.Header className="flex-row items-center gap-2 p-0">
              <DiskIcon className="size-4 text-accent" />
              <Card.Title className="text-sm">{t("Proton builds", "Proton 版本")}</Card.Title>
            </Card.Header>
            <Card.Content className="mt-2 flex flex-col gap-2 p-0">
              {info.protons.length === 0 && (
                <p className="text-sm text-muted">
                  {t(
                    "No Proton build found. Download one from the Proton manager or install",
                    "未找到 Proton，请从 Proton 管理器下载，或安装",
                  )}{" "}
                  <code>proton-ge-bin</code>
                  {t(".", "。")}
                </p>
              )}
              {info.protons.map((build) => (
                <div key={build.path} className="flex flex-col rounded-xl bg-surface/50 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm">{build.name}</span>
                    <Chip size="sm" variant="soft" className="text-[10px]">
                      {sourceLabel(build.source, t)}
                    </Chip>
                  </div>
                  <span className="truncate text-xs text-muted">{build.path}</span>
                </div>
              ))}
            </Card.Content>
          </Card>

          <Card className="p-4">
            <Card.Header className="flex-row items-center gap-2 p-0">
              <ExternalIcon className="size-4 text-accent" />
              <Card.Title className="text-sm">{t("Storage", "存储")}</Card.Title>
            </Card.Header>
            <Card.Content className="mt-2 p-0">
              {(
                [
                  [t("Prefix folder", "Prefix 目录"), info.config.prefix_root],
                  [t("Config", "配置"), info.paths.config],
                  [t("Data", "数据"), info.paths.data],
                  [t("Logs", "日志"), info.paths.logs],
                  [t("Proton downloads", "Proton 下载"), info.paths.protons],
                ] as const
              ).map(([label, path]) => (
                <div
                  key={label}
                  className="flex items-center justify-between gap-3 border-b border-border/40 py-2 last:border-0"
                >
                  <div className="flex min-w-0 flex-col">
                    <span className="text-sm">{label}</span>
                    <span className="truncate text-xs text-muted">{path}</span>
                  </div>
                  <Button size="sm" variant="secondary" onPress={() => void open(path)}>
                    {t("Open", "打开")}
                  </Button>
                </div>
              ))}
            </Card.Content>
          </Card>
        </div>
      )}
    </div>
  );
}
