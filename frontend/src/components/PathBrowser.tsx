import {useEffect, useState} from "react";
import {Button, Input, Modal, ScrollShadow, Spinner, toast} from "@heroui/react";

import {api} from "../lib/api";
import {useT} from "../lib/i18n";
import type {BrowseEntry} from "../lib/types";
import {CheckIcon, ChevronLeftIcon, DiskIcon, FolderIcon, RefreshIcon} from "./icons";

interface PathBrowserProps {
  open: boolean;
  mode: "file" | "directory";
  initialPath?: string;
  title?: string;
  onClose: () => void;
  onSelect: (path: string) => void;
}

export function PathBrowser({open, mode, initialPath, title, onClose, onSelect}: PathBrowserProps) {
  const {t} = useT();
  const [current, setCurrent] = useState("");
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [manual, setManual] = useState("");
  const [loading, setLoading] = useState(false);

  async function load(path?: string, fallback = true) {
    setLoading(true);
    try {
      const result = await api.browse(path);
      setCurrent(result.path);
      setParent(result.parent);
      setEntries(result.entries);
      setManual(result.path);
    } catch (error) {
      if (fallback && path) {
        await load(undefined, false);
        return;
      }
      toast.danger(t("Could not open folder", "无法打开文件夹"), {
        description: String((error as Error).message),
      });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (open) {
      void load(initialPath || undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialPath]);

  function pick(entry: BrowseEntry) {
    if (entry.is_dir) {
      void load(entry.path);
      return;
    }
    onSelect(entry.path);
    onClose();
  }

  return (
    <Modal.Backdrop isOpen={open} onOpenChange={(value) => !value && onClose()}>
      <Modal.Container size="lg">
        <Modal.Dialog>
          <Modal.CloseTrigger />
          <Modal.Header>
            <Modal.Heading>
              {title ?? (mode === "file" ? t("Select a file", "选择文件") : t("Select a folder", "选择文件夹"))}
            </Modal.Heading>
          </Modal.Header>
          <Modal.Body className="gap-3">
            <div className="flex items-center gap-2">
              <Button
                isIconOnly
                variant="secondary"
                aria-label={t("Parent folder", "上级文件夹")}
                isDisabled={!parent}
                onPress={() => parent && void load(parent)}
              >
                <ChevronLeftIcon className="size-4" />
              </Button>
              <Input
                aria-label={t("Folder path", "文件夹路径")}
                className="flex-1"
                value={manual}
                onChange={(event) => setManual(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void load(manual);
                }}
              />
              <Button isIconOnly variant="secondary" aria-label={t("Go", "前往")} onPress={() => void load(manual)}>
                <CheckIcon className="size-4" />
              </Button>
              <Button isIconOnly variant="secondary" aria-label={t("Refresh", "刷新")} onPress={() => void load(current)}>
                <RefreshIcon className="size-4" />
              </Button>
            </div>

            <ScrollShadow className="h-[45vh] rounded-2xl border border-border/60 bg-surface/50 p-1">
              {loading ? (
                <div className="flex h-full items-center justify-center gap-2 text-sm text-muted">
                  <Spinner size="sm" />
                  Loading…
                </div>
              ) : (
                <div className="flex flex-col">
                  {entries.map((entry) => (
                    <button
                      key={entry.path}
                      className="flex items-center gap-3 rounded-xl px-3 py-2 text-start text-sm transition-colors hover:bg-surface-secondary"
                      onClick={() => pick(entry)}
                      type="button"
                    >
                      {entry.is_dir ? (
                        <FolderIcon className="size-4 shrink-0 text-accent" />
                      ) : (
                        <DiskIcon className={`size-4 shrink-0 ${entry.executable ? "text-success" : "text-muted"}`} />
                      )}
                      <span className="flex-1 truncate">{entry.name}</span>
                      {entry.wine_prefix && (
                        <span className="shrink-0 rounded-full bg-success-soft px-2 py-0.5 text-[9px] uppercase text-success-soft-foreground">
                          prefix
                        </span>
                      )}
                      {!entry.is_dir && entry.executable && (
                        <span className="shrink-0 text-[9px] uppercase text-success">exe</span>
                      )}
                    </button>
                  ))}
                  {entries.length === 0 && (
                    <p className="p-6 text-center text-sm text-muted">{t("This folder is empty.", "此文件夹为空。")}</p>
                  )}
                </div>
              )}
            </ScrollShadow>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" slot="close">
              {t("Cancel", "取消")}
            </Button>
            {mode === "directory" && (
              <Button
                onPress={() => {
                  onSelect(current);
                  onClose();
                }}
              >
                {t("Use this folder", "使用此文件夹")}
              </Button>
            )}
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
