import {Button, Chip, Modal} from "@heroui/react";

import {useT} from "../lib/i18n";
import type {Dependencies} from "../lib/types";
import {AlertIcon, CheckIcon, CpuIcon, TerminalIcon} from "./icons";

interface SetupChecklistProps {
  open: boolean;
  dependencies: Dependencies | null;
  onOpenProton: () => void;
  onOpenSettings: () => void;
  onClose: () => void;
}

export function SetupChecklist({
  open,
  dependencies,
  onOpenProton,
  onOpenSettings,
  onClose,
}: SetupChecklistProps) {
  const {t} = useT();
  if (!dependencies) return null;
  const {required, missing_required} = dependencies;

  return (
    <Modal.Backdrop isOpen={open} onOpenChange={(value) => !value && onClose()}>
      <Modal.Container size="md">
        <Modal.Dialog>
          <Modal.CloseTrigger />
          <Modal.Header>
            <Modal.Icon className="bg-warning-soft text-warning-soft-foreground">
              <AlertIcon className="size-5" />
            </Modal.Icon>
            <Modal.Heading>{t("Setup needed before you can play", "开始游戏前需要完成设置")}</Modal.Heading>
          </Modal.Header>
          <Modal.Body className="gap-3">
            <p className="text-sm text-muted">
              {t(
                "Zed Launcher runs Windows games with umu-launcher and Proton. These are required:",
                "Zed Launcher 通过 umu-launcher 与 Proton 运行 Windows 游戏，以下为必需项：",
              )}
            </p>

            <div className="flex flex-col gap-2">
              <div className="flex items-start gap-3 rounded-xl border border-border/50 bg-surface/40 px-3 py-2.5">
                <span className="mt-0.5">
                  {required.umu_run.available ? (
                    <CheckIcon className="size-4 text-success" />
                  ) : (
                    <AlertIcon className="size-4 text-warning" />
                  )}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-sm font-medium">umu-run</span>
                  <span className="truncate font-mono text-[11px] text-muted">
                    {required.umu_run.path ?? required.umu_run.hint}
                  </span>
                </span>
                {!required.umu_run.available && (
                  <Chip size="sm" variant="soft" className="shrink-0 text-[10px]">
                    {t("missing", "缺失")}
                  </Chip>
                )}
              </div>

              <div className="flex items-start gap-3 rounded-xl border border-border/50 bg-surface/40 px-3 py-2.5">
                <span className="mt-0.5">
                  {required.proton.available ? (
                    <CheckIcon className="size-4 text-success" />
                  ) : (
                    <AlertIcon className="size-4 text-warning" />
                  )}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-sm font-medium">Proton</span>
                  <span className="truncate font-mono text-[11px] text-muted">
                    {required.proton.path ??
                      `${required.proton.hint}${required.proton.count === 0 ? " (no builds found)" : ""}`}
                  </span>
                </span>
                {!required.proton.available && (
                  <Chip size="sm" variant="soft" className="shrink-0 text-[10px]">
                    missing
                  </Chip>
                )}
              </div>
            </div>

            <p className="text-xs text-muted">
              {t(
                "On NixOS enable programs.steam.enable (for the Steam runtime) and add umu-launcher; Proton builds can also be downloaded here and stored in the launcher data folder.",
                "在 NixOS 上请启用 programs.steam.enable（提供 Steam 运行库）并安装 umu-launcher；Proton 也可以在这里下载并保存到启动器数据目录。",
              )}
            </p>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onPress={onOpenSettings}>
              {t("Open Settings", "打开设置")}
            </Button>
            {missing_required.includes("proton") && (
              <Button onPress={onOpenProton}>
                <CpuIcon className="size-4" />
                {t("Download Proton", "下载 Proton")}
              </Button>
            )}
            {!missing_required.includes("proton") && (
              <Button slot="close">
                <TerminalIcon className="size-4" />
                {t("Continue", "继续")}
              </Button>
            )}
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
