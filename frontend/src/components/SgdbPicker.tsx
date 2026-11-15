import {useEffect, useState} from "react";
import {Button, Input, Label, Modal, ScrollShadow, Spinner, toast} from "@heroui/react";

import {api} from "../lib/api";
import {useT} from "../lib/i18n";
import type {Game} from "../lib/types";
import {SearchIcon} from "./icons";

interface SgdbPickerProps {
  open: boolean;
  game: Game | null;
  onClose: () => void;
  onApplied: (game: Game) => void;
}

interface SgdbMatch {
  id: string;
  name: string;
}

interface SgdbGrid {
  id: string;
  url: string;
  thumb: string;
}

export function SgdbPicker({open, game, onClose, onApplied}: SgdbPickerProps) {
  const {t} = useT();
  const [term, setTerm] = useState("");
  const [matches, setMatches] = useState<SgdbMatch[] | null>(null);
  const [grids, setGrids] = useState<SgdbGrid[] | null>(null);
  const [activeMatch, setActiveMatch] = useState<SgdbMatch | null>(null);
  const [busy, setBusy] = useState(false);
  const [applying, setApplying] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setTerm(game?.title ?? "");
    setMatches(null);
    setGrids(null);
    setActiveMatch(null);
  }, [open, game]);

  async function search(event?: React.FormEvent) {
    event?.preventDefault();
    if (!term.trim()) return;
    setBusy(true);
    setMatches(null);
    setGrids(null);
    setActiveMatch(null);
    try {
      setMatches(await api.sgdbSearch(term.trim()));
    } catch (error) {
      setMatches([]);
      toast.danger(t("SteamGridDB search failed", "SteamGridDB 搜索失败"), {
        description: String((error as Error).message),
      });
    } finally {
      setBusy(false);
    }
  }

  async function loadGrids(match: SgdbMatch) {
    setBusy(true);
    setActiveMatch(match);
    setGrids(null);
    try {
      setGrids(await api.sgdbGrids(match.id));
    } catch (error) {
      setGrids([]);
      toast.danger(t("Could not load covers", "无法加载封面"), {
        description: String((error as Error).message),
      });
    } finally {
      setBusy(false);
    }
  }

  async function apply(grid: SgdbGrid) {
    if (!game) return;
    setApplying(grid.id);
    try {
      const updated = await api.setSgdbArtwork(game.id, grid.url);
      toast.success(t("Cover updated", "封面已更新"));
      onApplied(updated);
      onClose();
    } catch (error) {
      toast.danger(t("Could not apply the cover", "无法应用封面"), {
        description: String((error as Error).message),
      });
    } finally {
      setApplying(null);
    }
  }

  return (
    <Modal.Backdrop isOpen={open} onOpenChange={(value) => !value && onClose()}>
      <Modal.Container size="lg">
        <Modal.Dialog className="max-h-[88vh]">
          <Modal.CloseTrigger />
          <Modal.Header>
            <Modal.Heading>{t("Cover art from SteamGridDB", "从 SteamGridDB 获取封面")}</Modal.Heading>
          </Modal.Header>
          <Modal.Body className="flex flex-col gap-4 overflow-y-auto">
            <form className="flex flex-col gap-1.5" onSubmit={(event) => void search(event)}>
              <Label>{t("Search", "搜索")}</Label>
              <div className="flex gap-2">
                <Input
                  className="flex-1"
                  aria-label={t("Search SteamGridDB", "搜索 SteamGridDB")}
                  value={term}
                  onChange={(event) => setTerm(event.target.value)}
                  placeholder={game?.title ?? t("Game name", "游戏名称")}
                />
                <Button type="submit" isDisabled={busy || !term.trim()}>
                  <SearchIcon className="size-4" />
                  {t("Search", "搜索")}
                </Button>
              </div>
              <p className="text-xs text-muted">
                {t(
                  "Needs a SteamGridDB API key in Settings.",
                  "需要在设置中填写 SteamGridDB API key。",
                )}
              </p>
            </form>

            {busy && (
              <div className="flex items-center gap-2 py-6 text-sm text-muted">
                <Spinner size="sm" />
                {t("Loading…", "加载中…")}
              </div>
            )}

            {!busy && matches !== null && matches.length === 0 && (
              <p className="py-4 text-center text-sm text-muted">
                {t("No matching game found.", "未找到匹配的游戏。")}
              </p>
            )}

            {!busy && matches !== null && matches.length > 0 && (
              <div className="flex flex-col gap-1">
                <span className="text-xs text-muted">{t("Matches", "匹配结果")}</span>
                <ScrollShadow className="max-h-32 rounded-xl border border-border/50 bg-surface/40 p-1">
                  {matches.map((match) => (
                    <button
                      key={match.id}
                      type="button"
                      className={`flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-start text-sm hover:bg-surface-secondary ${
                        activeMatch?.id === match.id ? "bg-surface-secondary" : ""
                      }`}
                      onClick={() => void loadGrids(match)}
                    >
                      <span className="truncate">{match.name}</span>
                      <span className="text-[10px] text-muted">#{match.id}</span>
                    </button>
                  ))}
                </ScrollShadow>
              </div>
            )}

            {!busy && grids !== null && grids.length === 0 && (
              <p className="py-4 text-center text-sm text-muted">
                {t("This game has no covers.", "这个游戏没有封面。")}
              </p>
            )}

            {!busy && grids !== null && grids.length > 0 && (
              <ScrollShadow className="max-h-[46vh]">
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                  {grids.map((grid) => (
                    <button
                      key={grid.id}
                      type="button"
                      className="relative aspect-[2/3] overflow-hidden rounded-lg border border-border/50 hover:border-accent"
                      disabled={applying !== null}
                      onClick={() => void apply(grid)}
                    >
                      <img alt="" className="size-full object-cover" loading="lazy" src={grid.thumb} />
                      {applying === grid.id && (
                        <span className="absolute inset-0 flex items-center justify-center bg-black/60">
                          <Spinner size="sm" />
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </ScrollShadow>
            )}
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" slot="close">
              {t("Close", "关闭")}
            </Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
