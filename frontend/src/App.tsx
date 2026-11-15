import {useCallback, useEffect, useState} from "react";
import {
  Button,
  Card,
  Input,
  ListBox,
  Modal,
  Select,
  Spinner,
  Switch,
  toast,
} from "@heroui/react";

import {api} from "./lib/api";
import type {Game, Info, RunSnapshot} from "./lib/types";
import {BackupModal} from "./components/BackupModal";
import {detectLang, I18nProvider, resolveLang, useT, type Lang, type LangChoice} from "./lib/i18n";
import {CreateGameWizard} from "./components/CreateGameWizard";
import {DiagnosticsPage} from "./components/DiagnosticsPage";
import {GameCard} from "./components/GameCard";
import {GameDetails} from "./components/GameDetails";
import {GameEditor} from "./components/GameEditor";
import {LanguageMenu} from "./components/LanguageMenu";
import {PrefixTools} from "./components/PrefixTools";
import {ProtonManager} from "./components/ProtonManager";
import {RunDrawer} from "./components/RunDrawer";
import {SettingsModal} from "./components/SettingsModal";
import {SetupChecklist} from "./components/SetupChecklist";
import {CpuIcon, GamepadIcon, PlayIcon, PlusIcon, SettingsIcon, TerminalIcon} from "./components/icons";

type View = "library" | "diagnostics";

interface EditorState {
  open: boolean;
  mode: "add" | "edit";
  game: Game | null;
}

export default function App() {
  const [lang, setLangState] = useState<Lang>(() => {
    const stored = localStorage.getItem("zed.lang");
    return stored === "en" || stored === "zh" ? stored : resolveLang(undefined);
  });

  function setLang(next: LangChoice) {
    const resolved = next === "auto" ? detectLang() : next;
    setLangState(resolved);
    localStorage.setItem("zed.lang", resolved);
    localStorage.setItem("zed.langChoice", next);
    void api.updateSettings({language: next});
  }

  const preference = localStorage.getItem("zed.langChoice");
  useEffect(() => {
    if (preference !== "auto") return;
    setLangState(detectLang());
  }, [preference]);

  return (
    <I18nProvider lang={lang} setLang={setLang}>
      <Launcher />
    </I18nProvider>
  );
}

function Launcher() {
  const {lang, setLang, t} = useT();
  const [games, setGames] = useState<Game[]>([]);
  const [info, setInfo] = useState<Info | null>(null);
  const [activeRuns, setActiveRuns] = useState<RunSnapshot[]>([]);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("title");
  const [view, setView] = useState<View>("library");
  const [loading, setLoading] = useState(true);
  const [editor, setEditor] = useState<EditorState>({open: false, mode: "add", game: null});
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [protonOpen, setProtonOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [toolsGame, setToolsGame] = useState<Game | null>(null);
  const [detailsGame, setDetailsGame] = useState<Game | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [backupOpen, setBackupOpen] = useState(false);
  const [stopAllOpen, setStopAllOpen] = useState(false);
  const [stoppingAll, setStoppingAll] = useState(false);
  const [run, setRun] = useState<RunSnapshot | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Game | null>(null);
  const [deletePrefix, setDeletePrefix] = useState(false);
  const [dark, setDark] = useState(() => localStorage.getItem("zed.theme") !== "light");

  const refreshGames = useCallback(async () => {
    setGames(await api.listGames(search, sort));
  }, [search, sort]);

  const refreshInfo = useCallback(async () => {
    const next = await api.info();
    setInfo(next);
    // Adopt the stored language preference once, before the user picks one locally.
    if (!localStorage.getItem("zed.langChoice")) {
      const preference = next.config.language;
      localStorage.setItem("zed.langChoice", preference);
      if (resolveLang(preference) !== lang) setLang(resolveLang(preference));
    }
  }, [lang, setLang]);

  const refreshActive = useCallback(async () => {
    setActiveRuns(await api.activeRuns());
  }, []);

  useEffect(() => {
    void refreshInfo()
      .catch((error: Error) =>
        toast.danger(t("Backend unavailable", "后端不可用"), {description: error.message}),
      );
    void refreshActive();
  }, [refreshInfo, refreshActive]);

  useEffect(() => {
    // Games can exit on their own while the drawer is closed, so poll the active
    // runs instead of relying on launch/stop actions to refresh the header.
    const tick = () => {
      refreshActive().catch(() => undefined);
    };
    const timer = setInterval(tick, 3000);
    const onVisible = () => {
      if (!document.hidden) tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refreshActive]);

  useEffect(() => {
    if (info && !info.dependencies.ready) {
      setSetupOpen(true);
    }
  }, [info]);

  useEffect(() => {
    const timer = setTimeout(() => {
      refreshGames()
        .catch((error: Error) => toast.danger(t("Could not load games", "无法加载游戏"), {description: error.message}))
        .finally(() => setLoading(false));
    }, 150);
    return () => clearTimeout(timer);
  }, [refreshGames]);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", dark);
    root.classList.toggle("light", !dark);
    root.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("zed.theme", dark ? "dark" : "light");
  }, [dark]);

  function runFor(game: Game): RunSnapshot | undefined {
    return activeRuns.find(
      (entry) =>
        entry.game_id === game.id && (entry.status === "running" || entry.status === "starting"),
    );
  }

  /** Open the log drawer for a run that is already going. */
  async function showLog(game: Game) {
    const existing = runFor(game);
    if (existing) {
      setRun(existing);
      return;
    }
    try {
      const runs = await api.activeRuns();
      setActiveRuns(runs);
      const match = runs.find(
        (entry) =>
          entry.game_id === game.id && (entry.status === "running" || entry.status === "starting"),
      );
      if (match) setRun(match);
      else toast.warning(t("This game is not running", "该游戏当前没有运行"));
    } catch (error) {
      toast.danger(t("Could not load the log", "无法加载日志"), {description: String((error as Error).message)});
    }
  }

  async function play(game: Game) {
    if (runFor(game)) {
      await showLog(game);
      return;
    }
    try {
      setRun(await api.launchGame(game.id));
      void refreshActive();
    } catch (error) {
      toast.danger(t("Could not launch the game", "无法启动游戏"), {description: String((error as Error).message)});
    }
  }

  async function stopGame(game: Game) {
    const existing = runFor(game);
    if (!existing) {
      toast.warning(t("This game is not running", "该游戏当前没有运行"));
      await refreshActive();
      return;
    }
    try {
      await api.stopRun(existing.run_id);
      toast.success(t("Game stopped", "游戏已终止"), {description: game.title});
      if (run?.run_id === existing.run_id) setRun(null);
      await refreshActive();
      await refreshGames();
    } catch (error) {
      toast.danger(t("Could not stop the game", "无法终止游戏"), {description: String((error as Error).message)});
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    try {
      await api.deleteGame(deleteTarget.id, deletePrefix && deleteTarget.owned_prefix);
      toast.success(t("Game removed", "已移除游戏"), {description: deleteTarget.title});
      setDeleteTarget(null);
      setDeletePrefix(false);
      await refreshGames();
    } catch (error) {
      toast.danger(t("Could not remove the game", "无法移除游戏"), {description: String((error as Error).message)});
    }
  }

  async function stopAll() {
    const active = activeRuns.filter((entry) => entry.status === "running" || entry.status === "starting");
    setStoppingAll(true);
    try {
      for (const entry of active) {
        await api.stopRun(entry.run_id);
      }
      toast.success(t("Stopped all games", "已停止所有游戏"));
      await refreshActive();
    } catch (error) {
      toast.danger(t("Could not stop every game", "无法停止全部游戏"), {description: String((error as Error).message)});
    } finally {
      setStoppingAll(false);
      setStopAllOpen(false);
    }
  }

  async function createShortcut(game: Game) {
    try {
      if (game.shortcut) {
        await api.deleteShortcut(game.id, "applications");
        toast.success(t("Application shortcut removed", "已删除应用快捷方式"), {description: game.title});
      } else {
        const result = await api.createShortcut(game.id, "applications");
        toast.success(t("Application shortcut created", "已创建应用快捷方式"), {
          description: result.path,
        });
      }
      await refreshGames();
    } catch (error) {
      toast.danger(
        game.shortcut
          ? t("Could not remove the shortcut", "无法删除快捷方式")
          : t("Could not create the shortcut", "无法创建快捷方式"),
        {description: String((error as Error).message)},
      );
    }
  }

  function openEditor(mode: "add" | "edit", game: Game | null = null) {
    setEditor({open: true, mode, game});
  }

  function protonLabel(game: Game): string {
    if (!game.proton_path) return "Default Proton";
    const build = info?.protons.find((entry) => entry.path === game.proton_path);
    return build?.name ?? game.proton_path.split("/").filter(Boolean).pop() ?? "Proton";
  }

  const runningGames = new Set(activeRuns.map((entry) => entry.game_id));
  const missingRequired = info?.dependencies.missing_required ?? [];
  const depsReady = missingRequired.length === 0;
  const missingLabel = missingRequired
    .map((key) => (key === "proton" ? "Proton" : key === "umu_run" ? "umu-run" : key))
    .join(" and ");
  const visible = games;

  return (
    <div className="flex h-full flex-col bg-background text-foreground">
      <header className="flex flex-wrap items-center gap-3 border-b border-border/60 px-5 py-3">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400 to-indigo-600 text-lg font-black text-white shadow-lg shadow-indigo-500/20">
            Z
          </div>
          <div className="leading-tight">
            <h1 className="text-base font-semibold">Zed Launcher</h1>
            <p className="text-[11px] text-muted">Proton · umu-launcher · NixOS</p>
          </div>
        </div>

        <div className="mx-2 hidden h-8 w-px bg-border/60 sm:block" />

        <div className="flex flex-1 items-center gap-2">
          {view === "library" && (
            <Input
              aria-label={t("Search games", "搜索游戏")}
              className="w-64"
              placeholder={t("Search games…", "搜索游戏…")}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          )}
          {view === "library" && (
            <Select
              aria-label={t("Sort games", "排序")}
              className="w-40"
              selectedKey={sort}
              onSelectionChange={(key) => setSort(String(key))}
            >
              <Select.Trigger>
                <Select.Value />
                <Select.Indicator />
              </Select.Trigger>
              <Select.Popover>
                <ListBox>
                  <ListBox.Item id="title" textValue={t("Alphabetical", "按名称")}>
                    {t("Alphabetical", "按名称")}
                    <ListBox.ItemIndicator />
                  </ListBox.Item>
                  <ListBox.Item id="playtime" textValue={t("Playtime", "游玩时长")}>
                    {t("Playtime", "游玩时长")}
                    <ListBox.ItemIndicator />
                  </ListBox.Item>
                  <ListBox.Item id="last_played" textValue={t("Last played", "最近游玩")}>
                    {t("Last played", "最近游玩")}
                    <ListBox.ItemIndicator />
                  </ListBox.Item>
                  <ListBox.Item id="created_at" textValue={t("Recently added", "最近添加")}>
                    {t("Recently added", "最近添加")}
                    <ListBox.ItemIndicator />
                  </ListBox.Item>
                </ListBox>
              </Select.Popover>
            </Select>
          )}
        </div>

        <nav className="flex items-center gap-1" aria-label={t("Main", "主导航")}>
          <Button size="sm" variant={view === "library" ? "secondary" : "tertiary"} onPress={() => setView("library")}>
            <GamepadIcon className="size-4" />
            {t("Library", "游戏库")}
          </Button>
          <Button
            size="sm"
            variant={view === "diagnostics" ? "secondary" : "tertiary"}
            onPress={() => {
              setView("diagnostics");
              void refreshInfo();
            }}
          >
            <TerminalIcon className="size-4" />
            {t("Diagnostics", "诊断")}
          </Button>
          <LanguageMenu value={lang} onChange={setLang} />
          <Button size="sm" variant="tertiary" onPress={() => setDark((value) => !value)}>
            {dark ? t("Light", "浅色") : t("Dark", "深色")}
          </Button>
        </nav>

        <div className="flex items-center gap-2">
          {activeRuns.length > 0 && (
            <div className="flex items-center gap-1 rounded-full bg-success-soft px-2 py-1 text-[11px] text-success-soft-foreground">
              <span className="size-1.5 animate-pulse rounded-full bg-current" />
              {t(`${activeRuns.length} running`, `${activeRuns.length} 个运行中`)}
              <button
                type="button"
                className="ms-1 rounded-full px-1.5 py-0.5 hover:bg-black/10"
                onClick={() => setStopAllOpen(true)}
              >
                {t("Stop all", "全部停止")}
              </button>
            </div>
          )}
          <Button
            isIconOnly
            variant="secondary"
            aria-label={t("Proton manager", "Proton 管理器")}
            onPress={() => setProtonOpen(true)}
          >
            <CpuIcon className="size-4" />
          </Button>
          <Button
            isIconOnly
            variant="secondary"
            aria-label={t("Settings", "设置")}
            onPress={() => setSettingsOpen(true)}
          >
            <SettingsIcon className="size-4" />
          </Button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto p-5">
        {view === "diagnostics" ? (
          <DiagnosticsPage
            info={info}
            onRefresh={() => {
              void refreshInfo();
              void refreshActive();
            }}
          />
        ) : (
          <div className="mx-auto w-full max-w-7xl">
            {!depsReady && (
              <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-warning/40 bg-warning-soft/40 px-4 py-3 text-warning-soft-foreground">
                <span className="text-sm">
                  {t(
                    `${missingLabel} is not available yet, so games cannot be created or launched.`,
                    `${missingLabel} 尚未就绪，暂时无法创建或启动游戏。`,
                  )}
                </span>
                <Button
                  size="sm"
                  variant="secondary"
                  onPress={() => (missingRequired.includes("proton") ? setProtonOpen(true) : setSettingsOpen(true))}
                >
                  {missingRequired.includes("proton")
                    ? t("Download Proton", "下载 Proton")
                    : t("Open Settings", "打开设置")}
                </Button>
              </div>
            )}
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">{t("Your library", "我的游戏库")}</h2>
                <p className="text-sm text-muted">
                  {t(
                    `${visible.length} ${visible.length === 1 ? "game" : "games"}`,
                    `${visible.length} 个游戏`,
                  )}

                  {activeRuns.length > 0 &&
                    t(` · ${activeRuns.length} running`, ` · ${activeRuns.length} 个运行中`)}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="secondary" onPress={() => openEditor("add")}>
                  <PlayIcon className="size-4" />
                  {t("Add existing game", "添加已有游戏")}
                </Button>
                <Button onPress={() => setWizardOpen(true)}>
                  <PlusIcon className="size-4" />
                  {t("Create game", "创建游戏")}
                </Button>
              </div>
            </div>

            {loading ? (
              <div className="flex items-center gap-2 py-20 text-sm text-muted">
                <Spinner size="sm" />
                {t("Loading library…", "正在加载游戏库…")}
              </div>
            ) : visible.length === 0 ? (
              <Card className="flex flex-col items-center gap-3 border border-dashed border-border/70 bg-surface/40 px-6 py-16 text-center">
                <div className="flex size-16 items-center justify-center rounded-3xl bg-accent-soft text-accent-soft-foreground">
                  <PlayIcon className="size-7 translate-x-[1px]" />
                </div>
                <div>
                  <p className="text-base font-medium">
                    {games.length === 0 ? t("No games yet", "还没有游戏") : t("Nothing matches this search", "没有匹配的游戏")}
                  </p>
                  <p className="text-sm text-muted">
                    {t(
                      "Create a game to get a fresh prefix, or add a game that already has one.",
                      "「创建游戏」会新建独立 prefix；「添加已有游戏」使用现有的 prefix。",
                    )}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" onPress={() => openEditor("add")}>
                    {t("Add existing game", "添加已有游戏")}
                  </Button>
                  <Button onPress={() => setWizardOpen(true)}>
                    <PlusIcon className="size-4" />
                    {t("Create game", "创建游戏")}
                  </Button>
                </div>
              </Card>
            ) : (
              <div className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-4">
                {visible.map((game) => (
                  <GameCard
                    key={game.id}
                    game={game}
                    protonLabel={protonLabel(game)}
                    running={runningGames.has(game.id)}
                    onPlay={play}
                    onShowLog={(target) => void showLog(target)}
                    onStop={(target) => void stopGame(target)}
                    onEdit={(target) => openEditor("edit", target)}
                    onDelete={(target) => {
                      setDeleteTarget(target);
                      setDeletePrefix(false);
                    }}
                    onShortcut={createShortcut}
                    onTools={setToolsGame}
                    onDetails={setDetailsGame}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      <footer className="flex items-center justify-between border-t border-border/60 px-5 py-2 text-[11px] text-muted">
        <span className="flex items-center gap-1.5">
          <GamepadIcon className="size-3.5" />
          umu-launcher · Proton
        </span>
        <span
          className={depsReady ? undefined : "text-warning"}
          title={
            depsReady
              ? (info?.proton_effective ?? "")
              : t(`Missing: ${missingLabel}`, `缺少：${missingLabel}`)
          }
        >
          {!info
            ? t("Checking runtime…", "正在检查运行环境…")
            : depsReady
              ? t(
                  `Ready · ${info.protons.length} Proton ${info.protons.length === 1 ? "build" : "builds"}`,
                  `就绪 · ${info.protons.length} 个 Proton 版本`,
                )
              : t(
                  `Missing ${missingLabel} — check the setup prompt`,
                  `缺少 ${missingLabel} — 请查看启动提示`,
                )}
        </span>
      </footer>

      <GameEditor
        open={editor.open}
        mode={editor.mode}
        game={editor.game}
        protons={info?.protons ?? []}
        dependencies={info?.dependencies ?? null}
        onClose={() => setEditor({open: false, mode: "add", game: null})}
        onSaved={() => {
          void refreshGames();
          void refreshInfo();
        }}
      />

      <SettingsModal
        open={settingsOpen}
        info={info}
        onOpenProton={() => {
          setSettingsOpen(false);
          setProtonOpen(true);
        }}
        onOpenBackups={() => {
          setSettingsOpen(false);
          setBackupOpen(true);
        }}
        onClose={() => setSettingsOpen(false)}
        onSaved={() => {
          void refreshInfo();
          void refreshGames();
        }}
      />

      <CreateGameWizard
        open={wizardOpen}
        protons={info?.protons ?? []}
        dependencies={info?.dependencies ?? null}
        prefixRoot={info?.config.prefix_root ?? ""}
        onClose={() => setWizardOpen(false)}
        onCreated={() => {
          void refreshGames();
          void refreshInfo();
        }}
      />

      <PrefixTools
        game={toolsGame}
        protons={info?.protons ?? []}
        onClose={() => setToolsGame(null)}
      />

      <ProtonManager
        open={protonOpen}
        onClose={() => setProtonOpen(false)}
        onChanged={() => {
          void refreshInfo();
          void refreshGames();
        }}
      />

      <RunDrawer
        run={run}
        confirmKill={info?.config.confirm_kill ?? true}
        onClose={() => setRun(null)}
        onExited={() => {
          void refreshGames();
          void refreshActive();
        }}
      />

      <GameDetails
        game={detailsGame}
        running={detailsGame ? runningGames.has(detailsGame.id) : false}
        onClose={() => setDetailsGame(null)}
        onPlay={(game) => {
          setDetailsGame(null);
          void play(game);
        }}
        onTools={(game) => {
          setDetailsGame(null);
          setToolsGame(game);
        }}
        onDelete={(game) => {
          setDetailsGame(null);
          setDeleteTarget(game);
          setDeletePrefix(false);
        }}
        onChanged={() => {
          void refreshGames();
          const id = detailsGame?.id;
          if (id) {
            void api
              .getGame(id)
              .then((updated) =>
                setDetailsGame((current) => (current && current.id === updated.id ? updated : current)),
              )
              .catch(() => undefined);
          }
        }}
      />

      <BackupModal
        open={backupOpen}
        destination={info?.config.backup_dir ?? ""}
        onClose={() => setBackupOpen(false)}
        onRestored={() => {
          void refreshGames();
          void refreshInfo();
        }}
      />

      <SetupChecklist
        open={setupOpen}
        dependencies={info?.dependencies ?? null}
        onOpenProton={() => {
          setSetupOpen(false);
          setProtonOpen(true);
        }}
        onOpenSettings={() => {
          setSetupOpen(false);
          setSettingsOpen(true);
        }}
        onClose={() => setSetupOpen(false)}
      />

      <Modal.Backdrop isOpen={stopAllOpen} onOpenChange={setStopAllOpen}>
        <Modal.Container size="sm">
          <Modal.Dialog>
            <Modal.Header>
              <Modal.Heading>{t("Stop all running games?", "停止所有运行中的游戏？")}</Modal.Heading>
            </Modal.Header>
            <Modal.Body>
              <p className="text-sm text-muted">
                {t(
                  `${activeRuns.length} ${activeRuns.length === 1 ? "game is" : "games are"} running. All of them will be terminated.`,
                  `当前有 ${activeRuns.length} 个游戏正在运行，全部都会被终止。`,
                )}
              </p>
            </Modal.Body>
            <Modal.Footer>
              <Button variant="secondary" slot="close">
                {t("Cancel", "取消")}
              </Button>
              <Button variant="danger-soft" isDisabled={stoppingAll} onPress={() => void stopAll()}>
                {stoppingAll ? t("Stopping…", "正在停止…") : t("Stop all", "全部停止")}
              </Button>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>

      <Modal.Backdrop
        isOpen={deleteTarget !== null}
        onOpenChange={(value) => {
          if (!value) {
            setDeleteTarget(null);
            setDeletePrefix(false);
          }
        }}
      >
        <Modal.Container size="sm">
          <Modal.Dialog>
            <Modal.Header>
              <Modal.Heading>
                {t(`Remove ${deleteTarget?.title}?`, `移除 ${deleteTarget?.title}？`)}
              </Modal.Heading>
            </Modal.Header>
            <Modal.Body className="gap-3">
              <p className="text-sm text-muted">
                {t(
                  "The library entry is removed. Game files always stay untouched.",
                  "只会移除游戏库条目，游戏文件不会被删除。",
                )}
              </p>
              {deleteTarget?.owned_prefix && (
                <div className="flex items-start justify-between gap-3 rounded-xl border border-border/50 bg-surface/40 px-3 py-2.5">
                  <div className="flex flex-col">
                    <span className="text-sm font-medium">
                      {t("Also delete the Wine prefix", "同时删除 Wine prefix")}
                    </span>
                    <span className="break-all font-mono text-[11px] text-muted">
                      {deleteTarget.prefix_path}
                    </span>
                  </div>
                  <Switch size="sm" isSelected={deletePrefix} onChange={setDeletePrefix}>
                    <Switch.Content>
                      <Switch.Control>
                        <Switch.Thumb />
                      </Switch.Control>
                    </Switch.Content>
                  </Switch>
                </div>
              )}
            </Modal.Body>
            <Modal.Footer>
              <Button variant="secondary" slot="close">
                {t("Cancel", "取消")}
              </Button>
              <Button variant="danger-soft" onPress={() => void confirmDelete()}>
                {t("Remove", "移除")}
              </Button>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </div>
  );
}
