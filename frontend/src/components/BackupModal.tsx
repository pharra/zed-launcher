import {useCallback, useEffect, useState} from "react";
import {Button, Chip, Input, Modal, ScrollShadow, Spinner, Switch, toast} from "@heroui/react";

import {api, formatDate, formatSize} from "../lib/api";
import {useT} from "../lib/i18n";
import type {BackupEntry} from "../lib/types";
import {AlertIcon, CheckIcon, FolderIcon, RefreshIcon, TrashIcon} from "./icons";
import {PathBrowser} from "./PathBrowser";

interface BackupModalProps {
  open: boolean;
  destination: string;
  onClose: () => void;
  onRestored: () => void;
}

export function BackupModal({open, destination, onClose, onRestored}: BackupModalProps) {
  const [folder, setFolder] = useState(destination);
  const [entries, setEntries] = useState<BackupEntry[] | null>(null);
  const [includeArtwork, setIncludeArtwork] = useState(true);
  const [includeSaves, setIncludeSaves] = useState(false);
  const [saveInfo, setSaveInfo] = useState<{bytes: number; count: number} | null>(null);
  const {lang, t} = useT();
  const [busy, setBusy] = useState(false);
  const [browse, setBrowse] = useState(false);
  const [restoreTarget, setRestoreTarget] = useState<BackupEntry | null>(null);

  const load = useCallback(
    async (target = folder) => {
      try {
        const result = await api.listBackups(target || undefined);
        setEntries(result.backups);
        if (!folder && result.destination) setFolder(result.destination);
      } catch (error) {
        setEntries([]);
        toast.danger(t("Could not list backups", "无法列出备份"), {
          description: String((error as Error).message),
        });
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [folder],
  );

  useEffect(() => {
    if (!open) return;
    setFolder(destination);
    setEntries(null);
    setRestoreTarget(null);
    void load(destination);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, destination]);

  async function createBackup() {
    setBusy(true);
    try {
      const result = await api.createBackup(folder, includeArtwork, includeSaves);
      toast.success(t("Backup created", "备份已创建"), {
        description: `${result.name} · ${formatSize(result.size)} · ${result.games ?? 0} ${t("games", "个游戏")}`,
      });
      await load();
    } catch (error) {
      toast.danger(t("Could not create the backup", "无法创建备份"), {
        description: String((error as Error).message),
      });
    } finally {
      setBusy(false);
    }
  }

  async function restore(entry: BackupEntry) {
    setBusy(true);
    try {
      const result = await api.restoreBackup(entry.path);
      toast.success(t("Backup restored", "备份已恢复"), {
        description: [
          `${result.games} ${t("games", "个游戏")}`,
          `${result.artwork_files} ${t("artwork files", "个图片文件")}`,
          result.save_files ? `${result.save_files} ${t("save files", "个存档文件")}` : "",
        ]
          .filter(Boolean)
          .join(" · "),
      });
      setRestoreTarget(null);
      onRestored();
      await load();
    } catch (error) {
      toast.danger(t("Could not restore the backup", "无法恢复备份"), {
        description: String((error as Error).message),
      });
    } finally {
      setBusy(false);
    }
  }

  async function remove(entry: BackupEntry) {
    try {
      await api.deleteBackup(entry.path);
      toast.success(t("Backup deleted", "备份已删除"));
      await load();
    } catch (error) {
      toast.danger(t("Could not delete the backup", "无法删除备份"), {
        description: String((error as Error).message),
      });
    }
  }

  return (
    <>
      <Modal.Backdrop isOpen={open} onOpenChange={(value) => !value && onClose()}>
        <Modal.Container size="lg">
          <Modal.Dialog className="max-h-[88vh]">
            <Modal.CloseTrigger />
            <Modal.Header>
              <Modal.Heading>{t("Backups", "备份")}</Modal.Heading>
            </Modal.Header>
            <Modal.Body className="gap-4 overflow-y-auto">
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">{t("Backup folder", "备份目录")}</span>
                <div className="flex gap-2">
                  <Input
                    aria-label={t("Backup folder", "备份目录")}
                    className="flex-1"
                    value={folder}
                    placeholder={t("Defaults to the launcher data folder", "默认使用启动器数据目录")}
                    onChange={(event) => setFolder(event.target.value)}
                  />
                  <Button
                    isIconOnly
                    variant="secondary"
                    aria-label={t("Browse for backup folder", "浏览备份目录")}
                    onPress={() => setBrowse(true)}
                  >
                    <FolderIcon className="size-4" />
                  </Button>
                  <Button
                    isIconOnly
                    variant="secondary"
                    aria-label={t("Refresh", "刷新")}
                    onPress={() => void load()}
                  >
                    <RefreshIcon className="size-4" />
                  </Button>
                </div>
                <p className="text-xs text-muted">
                  {t(
                    "Backups contain the game library and covers. Wine prefixes are never copied; their paths are recorded in the manifest.",
                    "备份包含游戏库与封面。Wine prefix 不会被复制，只在清单中记录其路径。",
                  )}
                </p>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/50 bg-surface/40 px-3 py-2.5">
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-3">
                    <Switch size="sm" isSelected={includeArtwork} onChange={setIncludeArtwork}>
                      <Switch.Content>
                        <Switch.Control>
                          <Switch.Thumb />
                        </Switch.Control>
                      </Switch.Content>
                    </Switch>
                    <span className="text-sm">{t("Include cover images", "包含封面图片")}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <Switch
                      size="sm"
                      isSelected={includeSaves}
                      onChange={(value) => {
                        setIncludeSaves(value);
                        if (value && saveInfo === null) {
                          void api
                            .savegameEstimate()
                            .then(setSaveInfo)
                            .catch(() => setSaveInfo(null));
                        }
                      }}
                    >
                      <Switch.Content>
                        <Switch.Control>
                          <Switch.Thumb />
                        </Switch.Control>
                      </Switch.Content>
                    </Switch>
                    <span className="text-sm">{t("Include savegames", "包含游戏存档")}</span>
                    {includeSaves && saveInfo && (
                      <span className="text-[11px] text-muted">
                        {saveInfo.count} {t("folders", "个目录")} · {formatSize(saveInfo.bytes)}
                      </span>
                    )}
                  </div>
                </div>
                <Button isDisabled={busy} onPress={() => void createBackup()}>
                  {busy ? t("Working…", "处理中…") : t("Create backup now", "立即创建备份")}
                </Button>
              </div>

              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{t("Existing backups", "现有备份")}</span>
                  <span className="text-[11px] text-muted">
                    {entries?.length ?? 0} {t("found", "个")}
                  </span>
                </div>
                {entries === null ? (
                  <div className="flex items-center gap-2 py-8 text-sm text-muted">
                    <Spinner size="sm" />
                    {t("Loading…", "加载中…")}
                  </div>
                ) : entries.length === 0 ? (
                  <p className="rounded-xl bg-surface/50 px-4 py-6 text-center text-sm text-muted">
                    {t("No backups yet in this folder.", "此目录中还没有备份。")}
                  </p>
                ) : (
                  <ScrollShadow className="max-h-[36vh] rounded-xl border border-border/50 bg-surface/40 p-1">
                    <div className="flex flex-col">
                      {entries.map((entry) => (
                        <div
                          key={entry.path}
                          className="flex items-center gap-2 rounded-lg px-3 py-2 hover:bg-surface-secondary"
                        >
                          <span className="flex min-w-0 flex-1 flex-col">
                            <span className="truncate text-sm">{entry.name}</span>
                            <span className="truncate text-[11px] text-muted">
                              {formatDate(entry.created_at, lang)} · {formatSize(entry.size)}
                              {entry.games !== null
                                ? ` · ${entry.games} ${t("games", "个游戏")}`
                                : ""}
                            </span>
                          </span>
                          {entry.restorable ? (
                            <Chip size="sm" variant="soft" className="text-[10px]">
                              <CheckIcon className="me-1 size-3" />
                              {t("valid", "有效")}
                            </Chip>
                          ) : (
                            <Chip size="sm" variant="soft" className="text-[10px]">
                              <AlertIcon className="me-1 size-3" />
                              {t("invalid", "无效")}
                            </Chip>
                          )}
                          <Button
                            size="sm"
                            variant="secondary"
                            isDisabled={!entry.restorable || busy}
                            onPress={() => setRestoreTarget(entry)}
                          >
                            {t("Restore", "恢复")}
                          </Button>
                          <Button
                            isIconOnly
                            size="sm"
                            variant="secondary"
                            aria-label={t(`Delete ${entry.name}`, `删除 ${entry.name}`)}
                            isDisabled={busy}
                            onPress={() => void remove(entry)}
                          >
                            <TrashIcon className="size-3.5" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  </ScrollShadow>
                )}
              </div>
            </Modal.Body>
            <Modal.Footer>
              <Button variant="secondary" slot="close">
                {t("Close", "关闭")}
              </Button>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>

      <PathBrowser
        open={browse}
        mode="directory"
        title={t("Select a backup folder", "选择备份目录")}
        initialPath={folder}
        onClose={() => setBrowse(false)}
        onSelect={(path) => {
          setFolder(path);
          void load(path);
        }}
      />

      <Modal.Backdrop
        isOpen={restoreTarget !== null}
        onOpenChange={(value) => !value && setRestoreTarget(null)}
      >
        <Modal.Container size="sm">
          <Modal.Dialog>
            <Modal.Header>
              <Modal.Heading>{t("Restore this backup?", "恢复这个备份？")}</Modal.Heading>
            </Modal.Header>
            <Modal.Body className="gap-2">
              <p className="text-sm text-muted">
                {t("The current library and covers are replaced by", "当前的游戏库与封面将被替换为")}{" "}
                <span className="font-medium text-foreground">{restoreTarget?.name}</span>
                {t(". A copy of the current database is kept as ", "。当前数据库的副本会保留为 ")}
                <code>library.db.before-restore</code>
                {t(".", "。")}
              </p>
              <p className="text-xs text-muted">
                {t("Wine prefixes and game files are not touched.", "Wine prefix 与游戏文件不会被修改。")}
              </p>
            </Modal.Body>
            <Modal.Footer>
              <Button variant="secondary" slot="close">
                {t("Cancel", "取消")}
              </Button>
              <Button
                variant="danger-soft"
                isDisabled={busy}
                onPress={() => restoreTarget && void restore(restoreTarget)}
              >
                {busy ? t("Restoring…", "正在恢复…") : t("Restore", "恢复")}
              </Button>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </>
  );
}
