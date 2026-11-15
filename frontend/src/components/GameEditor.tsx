import {useEffect, useState, type ReactNode} from "react";
import {Button, Input, Label, ListBox, Modal, Select, Switch, Tabs, TextArea, toast} from "@heroui/react";

import {api, artworkUrl} from "../lib/api";
import {useT} from "../lib/i18n";
import type {Dependencies, Game, GameInput, ProtonBuild, ShortcutCandidate} from "../lib/types";
import {FolderIcon, SearchIcon} from "./icons";
import {LaunchOrder, withGameRow} from "./LaunchOrder";
import {MountDirs} from "./MountDirs";
import {SgdbPicker} from "./SgdbPicker";
import {PathBrowser} from "./PathBrowser";

interface GameEditorProps {
  open: boolean;
  mode: "add" | "edit";
  game: Game | null;
  protons: ProtonBuild[];
  dependencies: Dependencies | null;
  onClose: () => void;
  onSaved: () => void;
}

const emptyGame: GameInput = {
  title: "",
  path: "",
  args: "",
  launch_args: "",
  working_dir: "",
  pre_launch: "",
  post_launch: "",
  env: "",
  extra_programs: [],
  mount_dirs: [],
  proton_path: "",
  cover: "",
  icon: "",
  mangohud: false,
  gamemode: false,
  gamescope: false,
  gamescope_args: "",
  mangohud_args: "",
  no_sleep: false,
  sdl: false,
  wayland: false,
  wow64: false,
};

function Field({
  label,
  value,
  placeholder,
  onChange,
  action,
  type = "text",
}: {
  label: string;
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
  action?: ReactNode;
  type?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      <div className="flex items-center gap-2">
        <Input
          aria-label={label}
          className="flex-1"
          placeholder={placeholder}
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        {action}
      </div>
    </div>
  );
}

function KeySelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{value: string; label: string}>;
  onChange: (value: string) => void;
}) {
  return (
    <Select className="w-full" selectedKey={value} onSelectionChange={(key) => onChange(String(key))}>
      <Label>{label}</Label>
      <Select.Trigger>
        <Select.Value />
        <Select.Indicator />
      </Select.Trigger>
      <Select.Popover>
        <ListBox>
          {options.map((option) => (
            <ListBox.Item key={option.value} id={option.value} textValue={option.label}>
              {option.label}
              <ListBox.ItemIndicator />
            </ListBox.Item>
          ))}
        </ListBox>
      </Select.Popover>
    </Select>
  );
}

function Toggle({
  label,
  description,
  selected,
  disabled,
  mono,
  onChange,
}: {
  label: string;
  description: string;
  selected: boolean;
  disabled?: boolean;
  mono?: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div
      className={`flex min-w-0 items-start justify-between gap-3 overflow-hidden rounded-xl border px-3 py-2.5 ${
        disabled ? "border-border/30 bg-surface/20 opacity-70" : "border-border/50 bg-surface/40"
      }`}
      title={disabled ? description : undefined}
    >
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-sm font-medium">{label}</span>
        <span
          className={`leading-snug break-all ${mono ? "font-mono text-[10px]" : "text-xs"} ${
            disabled ? "text-warning" : "text-muted"
          }`}
        >
          {description}
        </span>
      </div>
      <div className="shrink-0 pt-0.5">
        <Switch size="sm" isSelected={selected} isDisabled={disabled} onChange={onChange}>
          <Switch.Content>
            <Switch.Control>
              <Switch.Thumb />
            </Switch.Control>
          </Switch.Content>
        </Switch>
      </div>
    </div>
  );
}

function ToolArguments({
  label,
  description,
  value,
  placeholder,
  disabled,
  disabledHint,
  onChange,
}: {
  label: string;
  description: string;
  value: string;
  placeholder: string;
  disabled: boolean;
  disabledHint: string;
  onChange: (value: string) => void;
}) {
  return (
    <div
      className={`flex min-w-0 flex-col gap-1.5 overflow-hidden rounded-xl border px-3 py-2.5 sm:col-span-2 ${
        disabled ? "border-border/30 bg-surface/20 opacity-70" : "border-border/50 bg-surface/40"
      }`}
    >
      <Label>{label}</Label>
      <Input
        aria-label={label}
        disabled={disabled}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <span
        className={`text-xs leading-snug break-words ${disabled ? "text-warning" : "text-muted"}`}
      >
        {disabled ? disabledHint : description}
      </span>
    </div>
  );
}

function ToolToggle({
  label,
  available,
  hint,
  selected,
  onChange,
}: {
  label: string;
  available: boolean;
  hint: string;
  selected: boolean;
  onChange: (value: boolean) => void;
}) {
  const {t} = useT();
  return (
    <Toggle
      label={label}
      description={
        available
          ? selected
            ? t("Enabled for this game", "已为此游戏启用")
            : t("Available — switch on to use it", "可用 — 打开即可使用")
          : hint
      }
      disabled={!available}
      selected={selected && available}
      onChange={onChange}
    />
  );
}

const titleText: Record<"add" | "edit", [string, string]> = {
  add: ["Add an existing game", "添加已有游戏"],
  edit: ["Edit game", "编辑游戏"],
};

export function GameEditor({
  open,
  mode,
  game,
  protons,
  dependencies,
  onClose,
  onSaved,
}: GameEditorProps) {
  const {t} = useT();
  const [form, setForm] = useState<GameInput>(emptyGame);
  const [browse, setBrowse] = useState<null | {mode: "file" | "directory"; field: keyof GameInput}>(null);
  const [saving, setSaving] = useState(false);
  const [coverSource, setCoverSource] = useState<string | null>(null);
  const [coverCleared, setCoverCleared] = useState(false);
  const [sgdbOpen, setSgdbOpen] = useState(false);
  const [scan, setScan] = useState<{open: boolean; loading: boolean; entries: ShortcutCandidate[]}>({
    open: false,
    loading: false,
    entries: [],
  });

  useEffect(() => {
    if (!open) return;
    setCoverSource(null);
    setCoverCleared(false);
    setBrowse(null);
    if (mode === "edit" && game) {
      setForm({...game});
    } else {
      setForm({...emptyGame});
    }
  }, [open, mode, game]);

  function set<K extends keyof GameInput>(key: K, value: GameInput[K]) {
    setForm((current) => ({...current, [key]: value}));
  }

  async function scanPrefix() {
    if (!form.prefix_path) {
      toast.warning(t("Choose a Wine prefix first", "请先选择 Wine prefix"));
      return;
    }
    setScan({open: true, loading: true, entries: []});
    try {
      const result = await api.scanPrefix(form.prefix_path);
      setScan({
        open: true,
        loading: false,
        entries: result.candidates.length ? result.candidates : result.fallback,
      });
    } catch (error) {
      setScan({open: false, loading: false, entries: []});
      toast.danger(t("Could not scan the prefix", "无法扫描 prefix"), {
        description: String((error as Error).message),
      });
    }
  }

  function autoTitle(path: string) {
    const name = path.split("/").filter(Boolean).pop() ?? "";
    const stem = name.replace(/\.(exe|EXE)$/, "");
    if (!form.title) set("title", stem);
  }

  async function save() {
    setSaving(true);
    const payload: GameInput = {
      ...form,
      extra_programs: withGameRow(form.extra_programs ?? [], form.path ?? ""),
      mount_dirs: (form.mount_dirs ?? []).map((dir) => dir.trim()).filter(Boolean),
    };
    try {
      let saved: Game;
      if (mode === "edit" && game) {
        saved = await api.updateGame(game.id, payload);
      } else {
        saved = await api.createGame({...payload, mode: "add"});
      }

      let artworkError: string | null = null;
      try {
        if (coverSource) {
          saved = await api.setArtwork(saved.id, coverSource);
        } else if (coverCleared && mode === "edit" && game) {
          await api.deleteArtwork(game.id);
        }
      } catch (error) {
        artworkError = String((error as Error).message);
      }

      if (artworkError) {
        toast.warning(t("Saved, but the cover could not be updated", "已保存，但封面更新失败"), {
          description: artworkError,
        });
      } else {
        toast.success(
          mode === "edit" ? t("Game updated", "游戏已更新") : t("Game added", "游戏已添加"),
          {description: saved.title},
        );
      }
      onSaved();
      onClose();
    } catch (error) {
      toast.danger(t("Could not save the game", "无法保存游戏"), {
        description: String((error as Error).message),
      });
    } finally {
      setSaving(false);
    }
  }

  const defaultProton = protons[0];
  const protonOptions = [
    {
      value: "",
      label: defaultProton
        ? t(`Default (${defaultProton.name})`, `默认（${defaultProton.name}）`)
        : t("Default (none found)", "默认（未找到）"),
    },
    ...protons.map((build) => ({
      value: build.path,
      label: `${build.name} · ${build.source}`,
    })),
  ];
  const currentProton = form.proton_path ?? "";
  if (currentProton && !protons.some((build) => build.path === currentProton)) {
    protonOptions.push({
      value: currentProton,
      label: t(
        `${currentProton.split("/").filter(Boolean).pop() ?? currentProton} · missing`,
        `${currentProton.split("/").filter(Boolean).pop() ?? currentProton} · 缺失`,
      ),
    });
  }

  const missingPath = !form.path;
  const missingPrefix = mode === "add" && !form.prefix_path;

  return (
    <>
      <Modal.Backdrop isOpen={open} onOpenChange={(value) => !value && onClose()}>
        <Modal.Container size="lg">
          <Modal.Dialog className="max-h-[90vh]">
            <Modal.CloseTrigger />
            <Modal.Header>
              <Modal.Heading>{t(...titleText[mode])}</Modal.Heading>
            </Modal.Header>
            <Modal.Body className="overflow-y-auto">
              <Tabs className="w-full" defaultSelectedKey="general">
                <Tabs.ListContainer>
                  <Tabs.List aria-label={t("Game settings", "游戏设置")}>
                    <Tabs.Tab id="general">
                      {t("General", "常规")}
                      <Tabs.Indicator />
                    </Tabs.Tab>
                    <Tabs.Tab id="programs">
                      {t("Programs", "程序")}
                      <Tabs.Indicator />
                    </Tabs.Tab>
                    <Tabs.Tab id="launch">
                      {t("Launch", "启动")}
                      <Tabs.Indicator />
                    </Tabs.Tab>
                    <Tabs.Tab id="advanced">
                      {t("Advanced", "高级")}
                      <Tabs.Indicator />
                    </Tabs.Tab>
                  </Tabs.List>
                </Tabs.ListContainer>

                <Tabs.Panel className="flex flex-col gap-4 pt-4" id="general">
                  <Field
                    label={t("Title", "标题")}
                    value={form.title ?? ""}
                    placeholder={t("Game title", "游戏名称")}
                    onChange={(value) => set("title", value)}
                  />

                  <Field
                    label={t("Windows executable", "Windows 可执行文件")}
                    value={form.path ?? ""}
                    placeholder="/home/you/Games/Game/game.exe"
                    onChange={(value) => {
                      set("path", value);
                      autoTitle(value);
                    }}
                    action={
                      <Button
                        isIconOnly
                        variant="secondary"
                        aria-label={t("Browse for executable", "浏览可执行文件")}
                        onPress={() => setBrowse({mode: "file", field: "path"})}
                      >
                        <FolderIcon className="size-4" />
                      </Button>
                    }
                  />

                  <Field
                    label={t("Wine prefix", "Wine prefix")}
                    value={form.prefix_path ?? ""}
                    placeholder="/home/you/Games/SomeGame/prefix"
                    onChange={(value) => set("prefix_path", value)}
                    action={
                      <Button
                        isIconOnly
                        variant="secondary"
                        aria-label={t("Browse for prefix", "浏览 prefix")}
                        onPress={() => setBrowse({mode: "directory", field: "prefix_path"})}
                      >
                        <FolderIcon className="size-4" />
                      </Button>
                    }
                  />
                  <div className="flex items-start justify-between gap-2">
                    <p className="flex-1 text-xs text-muted">
                      {mode === "add"
                        ? t(
                            "The folder must already be a Wine prefix (it contains drive_c). Use Create game to build a new one.",
                            "该目录必须已经是 Wine prefix（包含 drive_c）。如需新建请使用“创建游戏”。",
                          )
                        : t(
                            "Changing the prefix path only re-points the game; files are not moved.",
                            "修改 prefix 路径只会重新指向，不会移动文件。",
                          )}
                    </p>
                    <Button
                      size="sm"
                      variant="secondary"
                      isDisabled={!form.prefix_path}
                      onPress={() => void scanPrefix()}
                    >
                      {t("Scan for programs", "扫描程序")}
                    </Button>
                  </div>

                  <KeySelect
                    label={t("Proton", "Proton")}
                    value={form.proton_path ?? ""}
                    options={protonOptions}
                    onChange={(value) => set("proton_path", value)}
                  />

                  <div className="flex items-center gap-3 rounded-xl border border-border/50 bg-surface/40 p-3">
                    <div className="flex size-20 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-surface-secondary">
                      {form.cover && !coverCleared ? (
                        <img alt="" className="size-full object-cover" src={artworkUrl(form.cover)} />
                      ) : (
                        <span className="text-[10px] text-muted">{t("No cover", "无封面")}</span>
                      )}
                    </div>
                    <div className="flex min-w-0 flex-col gap-1">
                      <span className="text-sm font-medium">{t("Cover image", "封面图片")}</span>
                      <span className="max-w-[280px] truncate text-xs text-muted">
                        {coverSource ??
                          (form.cover && !coverCleared
                            ? t("Saved cover", "已保存的封面")
                            : t("PNG, JPEG, WebP or AVIF", "PNG、JPEG、WebP 或 AVIF"))}
                      </span>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="secondary"
                          onPress={() => setBrowse({mode: "file", field: "cover"})}
                        >
                          {t("Choose…", "选择…")}
                        </Button>
                        {mode === "edit" && game && (
                          <Button size="sm" variant="secondary" onPress={() => setSgdbOpen(true)}>
                            <SearchIcon className="size-3.5" />
                            SteamGridDB
                          </Button>
                        )}
                        {(form.cover || coverSource) && (
                          <Button
                            size="sm"
                            variant="tertiary"
                            onPress={() => {
                              setCoverSource(null);
                              setCoverCleared(true);
                              set("cover", "");
                            }}
                          >
                            {t("Remove", "移除")}
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                </Tabs.Panel>

                <Tabs.Panel className="flex flex-col gap-4 pt-4" id="programs">
                  <LaunchOrder
                    gamePath={form.path ?? ""}
                    entries={withGameRow(form.extra_programs ?? [], form.path ?? "")}
                    onChange={(entries) => set("extra_programs", entries)}
                  />
                  <div className="h-px bg-border/60" />
                  <MountDirs
                    dirs={form.mount_dirs ?? []}
                    onChange={(dirs) => set("mount_dirs", dirs)}
                  />
                </Tabs.Panel>

                <Tabs.Panel className="flex flex-col gap-4 pt-4" id="launch">
                  <div className="flex flex-col gap-1.5">
                    <Field
                      label={t("Game arguments", "游戏参数")}
                      value={form.args ?? ""}
                      placeholder="--windowed -novid"
                      onChange={(value) => set("args", value)}
                    />
                    <span className="text-xs text-muted">
                      {t(
                        "Passed to the game itself, after the executable.",
                        "追加在可执行文件之后，直接传给游戏本身。",
                      )}
                    </span>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>{t("Environment variables", "环境变量")}</Label>
                    <TextArea
                      aria-label={t("Environment variables", "环境变量")}
                      className="min-h-24 w-full font-mono text-xs"
                      placeholder={"DXVK_HUD=fps\nMANGOHUD_CONFIG=cpu_temp"}
                      value={form.env ?? ""}
                      onChange={(event) => set("env", event.target.value)}
                    />
                    <span className="text-xs text-muted">
                      {t(
                        "One KEY=VALUE per line. These are applied before the launcher runs the game.",
                        "每行一个 KEY=VALUE，启动器运行游戏前会应用这些变量。",
                      )}
                    </span>
                  </div>
                  <Field
                    label={t("Working directory", "工作目录")}
                    value={form.working_dir ?? ""}
                    placeholder={t("Defaults to the executable folder", "默认使用可执行文件所在目录")}
                    onChange={(value) => set("working_dir", value)}
                    action={
                      <Button
                        isIconOnly
                        variant="secondary"
                        aria-label={t("Browse for working directory", "浏览工作目录")}
                        onPress={() => setBrowse({mode: "directory", field: "working_dir"})}
                      >
                        <FolderIcon className="size-4" />
                      </Button>
                    }
                  />
                  <Field
                    label={t("Pre-launch command", "启动前命令")}
                    value={form.pre_launch ?? ""}
                    placeholder={t("Optional shell command", "可选的 shell 命令")}
                    onChange={(value) => set("pre_launch", value)}
                  />
                  <Field
                    label={t("Post-exit command", "退出后命令")}
                    value={form.post_launch ?? ""}
                    placeholder={t("Optional shell command", "可选的 shell 命令")}
                    onChange={(value) => set("post_launch", value)}
                  />
                </Tabs.Panel>

                <Tabs.Panel className="flex flex-col gap-2 pt-4" id="advanced">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <ToolToggle
                      label="MangoHud"
                      available={Boolean(dependencies?.optional.mangohud?.available)}
                      hint={t("MangoHud is not installed", "MangoHud 未安装")}
                      selected={Boolean(form.mangohud)}
                      onChange={(value) => set("mangohud", value)}
                    />
                    <ToolArguments
                      label={t("MangoHud arguments", "MangoHud 参数")}
                      description={t(
                        "Passed to mangohud, for example --dlsym.",
                        "传给 mangohud 的参数，例如 --dlsym。",
                      )}
                      value={form.mangohud_args ?? ""}
                      placeholder="--dlsym"
                      disabled={!form.mangohud}
                      disabledHint={t(
                        "Enable MangoHud to configure its arguments.",
                        "启用 MangoHud 后才能配置参数。",
                      )}
                      onChange={(value) => set("mangohud_args", value)}
                    />
                    <ToolToggle
                      label="GameMode"
                      available={Boolean(dependencies?.optional.gamemoderun?.available)}
                      hint={t("GameMode is not installed", "GameMode 未安装")}
                      selected={Boolean(form.gamemode)}
                      onChange={(value) => set("gamemode", value)}
                    />
                    <ToolToggle
                      label="Gamescope"
                      available={Boolean(dependencies?.optional.gamescope?.available)}
                      hint={t("Gamescope is not installed", "Gamescope 未安装")}
                      selected={Boolean(form.gamescope)}
                      onChange={(value) => set("gamescope", value)}
                    />
                    <ToolArguments
                      label={t("Gamescope arguments", "Gamescope 参数")}
                      description={t(
                        "Defaults to -f when left empty.",
                        "留空时使用 -f。",
                      )}
                      value={form.gamescope_args ?? ""}
                      placeholder="-f -W 1920 -H 1080 -r 60"
                      disabled={!form.gamescope}
                      disabledHint={t(
                        "Enable Gamescope to configure its arguments.",
                        "启用 Gamescope 后才能配置参数。",
                      )}
                      onChange={(value) => set("gamescope_args", value)}
                    />
                    <ToolToggle
                      label={t("Prevent sleep", "阻止休眠")}
                      available={Boolean(dependencies?.optional.systemd_inhibit?.available)}
                      hint={t("systemd-inhibit is not available", "systemd-inhibit 不可用")}
                      selected={Boolean(form.no_sleep)}
                      onChange={(value) => set("no_sleep", value)}
                    />
                    <Toggle
                      label={t("SDL input", "SDL 输入")}
                      description="PROTON_PREFER_SDL=1"
                      mono
                      selected={Boolean(form.sdl)}
                      onChange={(value) => set("sdl", value)}
                    />
                    <Toggle
                      label={t("Wayland driver", "Wayland 驱动")}
                      description="PROTON_ENABLE_WAYLAND=1"
                      mono
                      selected={Boolean(form.wayland)}
                      onChange={(value) => set("wayland", value)}
                    />
                    <Toggle
                      label="WOW64"
                      description="PROTON_USE_WOW64=1"
                      mono
                      selected={Boolean(form.wow64)}
                      onChange={(value) => set("wow64", value)}
                    />
                  </div>
                </Tabs.Panel>
              </Tabs>
            </Modal.Body>
            <Modal.Footer>
              <Button variant="secondary" slot="close">
                {t("Cancel", "取消")}
              </Button>
              <Button isDisabled={missingPath || missingPrefix || saving} onPress={() => void save()}>
                {saving
                  ? t("Saving…", "正在保存…")
                  : mode === "edit"
                    ? t("Save changes", "保存修改")
                    : t("Add game", "添加游戏")}
              </Button>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>

      <Modal.Backdrop
        isOpen={scan.open}
        onOpenChange={(value) => !value && setScan((current) => ({...current, open: false}))}
      >
        <Modal.Container size="md">
          <Modal.Dialog className="max-h-[80vh]">
            <Modal.CloseTrigger />
            <Modal.Header>
              <Modal.Heading>{t("Programs in this prefix", "此 prefix 中的程序")}</Modal.Heading>
            </Modal.Header>
            <Modal.Body className="overflow-y-auto">
              {scan.loading ? (
                <p className="py-8 text-center text-sm text-muted">{t("Scanning…", "扫描中…")}</p>
              ) : scan.entries.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted">
                  {t(
                    "No programs found. Browse for the executable instead.",
                    "未找到程序，请手动浏览选择可执行文件。",
                  )}
                </p>
              ) : (
                <div className="flex flex-col gap-1">
                  {scan.entries.map((entry) => (
                    <button
                      key={entry.path}
                      type="button"
                      className="flex flex-col rounded-lg px-3 py-2 text-start hover:bg-surface-secondary"
                      onClick={() => {
                        setForm((current) => ({
                          ...current,
                          path: entry.path,
                          title: current.title || entry.name,
                        }));
                        setScan((current) => ({...current, open: false}));
                      }}
                    >
                      <span className="text-sm">{entry.name}</span>
                      <span className="break-all font-mono text-[10px] text-muted">{entry.path}</span>
                    </button>
                  ))}
                </div>
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

      <SgdbPicker
        open={sgdbOpen}
        game={mode === "edit" ? game : null}
        onClose={() => setSgdbOpen(false)}
        onApplied={(updated) => {
          setCoverSource(null);
          setCoverCleared(false);
          set("cover", updated.cover);
          set("icon", updated.icon);
        }}
      />

      <PathBrowser
        open={browse !== null}
        mode={browse?.mode ?? "file"}
        initialPath={
          browse && typeof form[browse.field] === "string" ? String(form[browse.field]) : undefined
        }
        onClose={() => setBrowse(null)}
        onSelect={(path) => {
          const field = browse?.field;
          if (!field) return;
          if (field === "cover") {
            setCoverSource(path);
            setCoverCleared(false);
            return;
          }
          setForm((current) => ({...current, [field]: path}));
          if (field === "path") autoTitle(path);
        }}
      />
    </>
  );
}
