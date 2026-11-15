import {useEffect, useState} from "react";
import {Button, Input, Label, ListBox, Modal, Select, Switch, toast} from "@heroui/react";

import {api} from "../lib/api";
import {LANGUAGES, useT, type LangChoice} from "../lib/i18n";
import {sourceLabel} from "../lib/status";
import type {Info, ProtonBuild, Settings} from "../lib/types";
import {AlertIcon, CheckIcon, FolderIcon, TrashIcon} from "./icons";
import {PathBrowser} from "./PathBrowser";

interface SettingsModalProps {
  open: boolean;
  info: Info | null;
  onOpenProton: () => void;
  onOpenBackups: () => void;
  onClose: () => void;
  onSaved: () => void;
}

export function SettingsModal({
  open,
  info,
  onOpenProton,
  onOpenBackups,
  onClose,
  onSaved,
}: SettingsModalProps) {
  const {setLang, t} = useT();
  const notifyPath = info?.tools["notify_send"] ?? null;
  const [settings, setSettings] = useState<Settings | null>(null);
  const [browse, setBrowse] = useState<null | {
    mode: "file" | "directory";
    field: keyof Settings | `tool:${string}`;
  }>(null);
  const [addPathOpen, setAddPathOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [autostartEnabled, setAutostartEnabled] = useState(false);

  useEffect(() => {
    if (!open) return;
    api
      .autostart()
      .then((result) => setAutostartEnabled(result.enabled))
      .catch(() => setAutostartEnabled(false));
    api
      .settings()
      .then(setSettings)
      .catch((error: Error) =>
        toast.danger(t("Could not load settings", "无法加载设置"), {description: error.message}),
      );
  }, [open]);

  function setToolPath(key: string, value: string) {
    setSettings((current) =>
      current
        ? {...current, tool_paths: {...(current.tool_paths ?? {}), [key]: value}}
        : current,
    );
  }

  function set<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings((current) => (current ? {...current, [key]: value} : current));
  }

  async function toggleAutostart(value: boolean) {
    try {
      const result = await api.setAutostart(value);
      setAutostartEnabled(result.enabled);
      toast.success(
        result.enabled
          ? t("Autostart enabled", "已启用开机自启")
          : t("Autostart disabled", "已关闭开机自启"),
      );
    } catch (error) {
      toast.danger(t("Could not change autostart", "无法修改自启设置"), {
        description: String((error as Error).message),
      });
    }
  }

  async function save() {
    if (!settings) return;
    setSaving(true);
    try {
      await api.updateSettings({
        prefix_root: settings.prefix_root,
        backup_dir: settings.backup_dir,
        backup_schedule: settings.backup_schedule,
        umu_run: settings.umu_run,
        tool_paths: settings.tool_paths,
        github_token: settings.github_token,
        steamgriddb_api_key: settings.steamgriddb_api_key,
        notifications: settings.notifications,
        tray: settings.tray,
        language: settings.language,
        proton_default: settings.proton_default,
        proton_log: settings.proton_log,
      });
      toast.success(t("Settings saved", "设置已保存"));
      onSaved();
      onClose();
    } catch (error) {
      toast.danger(t("Could not save settings", "无法保存设置"), {
        description: String((error as Error).message),
      });
    } finally {
      setSaving(false);
    }
  }

  async function addProtonPath(path: string) {
    try {
      const result = await api.addProtonPath(path);
      setSettings((current) => (current ? {...current, proton_paths: result.paths} : current));
      toast.success(t("Proton path added", "已添加 Proton 路径"));
      onSaved();
    } catch (error) {
      toast.danger(t("Could not add the Proton path", "无法添加 Proton 路径"), {
        description: String((error as Error).message),
      });
    }
  }

  async function removeProtonPath(path: string) {
    try {
      const result = await api.removeProtonPath(path);
      setSettings((current) => (current ? {...current, proton_paths: result.paths} : current));
      toast.success(t("Proton path removed", "已移除 Proton 路径"));
      onSaved();
    } catch (error) {
      toast.danger(t("Could not remove the Proton path", "无法移除 Proton 路径"), {
        description: String((error as Error).message),
      });
    }
  }

  const protonOptions: ProtonBuild[] = info?.protons ?? [];
  const effectiveProton =
    info?.proton_effective ?? protonOptions[0]?.path ?? "";
  const defaultOptions = protonOptions.map((build) => ({
    value: build.path,
    label: `${build.name} · ${sourceLabel(build.source, t)}`,
  }));

  return (
    <>
      <Modal.Backdrop isOpen={open} onOpenChange={(value) => !value && onClose()}>
        <Modal.Container size="lg">
          <Modal.Dialog className="max-h-[88vh]">
            <Modal.CloseTrigger />
            <Modal.Header>
              <Modal.Heading>{t("Settings", "设置")}</Modal.Heading>
            </Modal.Header>
            <Modal.Body className="overflow-y-auto">
              {!settings ? (
                <p className="py-10 text-center text-sm text-muted">
                  {t("Loading…", "加载中…")}
                </p>
              ) : (
                <div className="flex flex-col gap-5">
                  <div className="flex flex-col gap-1.5">
                    <Label>{t("Prefix folder", "Prefix 目录")}</Label>
                    <div className="flex gap-2">
                      <Input
                        aria-label={t("Prefix folder", "Prefix 目录")}
                        className="flex-1"
                        value={settings.prefix_root}
                        onChange={(event) => set("prefix_root", event.target.value)}
                      />
                      <Button
                        isIconOnly
                        variant="secondary"
                        aria-label={t("Browse for prefix folder", "浏览 Prefix 目录")}
                        onPress={() => setBrowse({mode: "directory", field: "prefix_root"})}
                      >
                        <FolderIcon className="size-4" />
                      </Button>
                    </div>
                    <p className="text-xs text-muted">
                      {t(
                        "New games get their own prefix inside this folder.",
                        "新建的游戏会在此目录下获得独立 prefix。",
                      )}
                    </p>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label>{t("umu-run path", "umu-run 路径")}</Label>
                    <div className="flex gap-2">
                      <Input
                        aria-label={t("umu-run path", "umu-run 路径")}
                        className="flex-1"
                        placeholder={t("Not found — install umu-launcher", "未找到 — 请安装 umu-launcher")}
                        value={settings.umu_run || info?.dependencies.required.umu_run.path || ""}
                        onChange={(event) => set("umu_run", event.target.value)}
                      />
                      <Button
                        isIconOnly
                        variant="secondary"
                        aria-label={t("Browse for umu-run", "浏览 umu-run")}
                        onPress={() => setBrowse({mode: "file", field: "umu_run"})}
                      >
                        <FolderIcon className="size-4" />
                      </Button>
                    </div>
                    {info?.dependencies.required.umu_run.warning ? (
                      <span className="text-xs leading-snug text-warning">
                        {info.dependencies.required.umu_run.warning}
                      </span>
                    ) : null}
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label>{t("Backup folder", "备份目录")}</Label>
                    <div className="flex gap-2">
                      <Input
                        aria-label={t("Backup folder", "备份目录")}
                        className="flex-1"
                        placeholder={t(
                          "Defaults to the launcher data folder",
                          "默认使用启动器数据目录",
                        )}
                        value={settings.backup_dir}
                        onChange={(event) => set("backup_dir", event.target.value)}
                      />
                      <Button
                        isIconOnly
                        variant="secondary"
                        aria-label={t("Browse for backup folder", "浏览备份目录")}
                        onPress={() => setBrowse({mode: "directory", field: "backup_dir"})}
                      >
                        <FolderIcon className="size-4" />
                      </Button>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-xs text-muted">
                        {t(
                          "Library backups (games and covers). Prefixes are listed, not copied.",
                          "备份游戏库与封面；prefix 只记录路径，不会被复制。",
                        )}
                      </p>
                      <Button size="sm" variant="secondary" onPress={onOpenBackups}>
                        {t("Manage backups", "管理备份")}
                      </Button>
                    </div>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label>{t("Automatic backups", "自动备份")}</Label>
                    <Select
                      className="w-full"
                      selectedKey={settings.backup_schedule}
                      onSelectionChange={(key) => set("backup_schedule", String(key))}
                    >
                      <Select.Trigger>
                        <Select.Value />
                        <Select.Indicator />
                      </Select.Trigger>
                      <Select.Popover>
                        <ListBox>
                          {[
                            ["off", t("Off", "关闭")],
                            ["daily", t("Daily", "每天")],
                            ["weekly", t("Weekly", "每周")],
                          ].map(([value, label]) => (
                            <ListBox.Item key={value} id={value} textValue={label}>
                              {label}
                              <ListBox.ItemIndicator />
                            </ListBox.Item>
                          ))}
                        </ListBox>
                      </Select.Popover>
                    </Select>
                    <span className="text-xs text-muted">
                      {t(
                        "Runs while the launcher is open, into the backup folder.",
                        "启动器打开期间执行，写入备份目录。",
                      )}
                    </span>
                  </div>

                  <div className="flex flex-col gap-2 rounded-2xl border border-border/50 bg-surface/40 p-3">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">
                        {t("Additional Proton folders", "额外的 Proton 目录")}
                      </span>
                      <span className="text-xs text-muted">
                        {t(
                          "Steam and Steam Flatpak folders are scanned automatically.",
                          "Steam 与 Steam Flatpak 的目录会自动扫描。",
                        )}
                      </span>
                    </div>
                    {settings.proton_paths.length === 0 && (
                      <p className="text-xs text-muted">{t("No manual folders yet.", "还没有手动添加的目录。")}</p>
                    )}
                    {settings.proton_paths.map((path) => (
                      <div key={path} className="flex items-center gap-2">
                        <span className="flex-1 truncate font-mono text-[11px] text-muted" title={path}>
                          {path}
                        </span>
                        <Button
                          isIconOnly
                          size="sm"
                          variant="secondary"
                          aria-label={`Remove ${path}`}
                          onPress={() => void removeProtonPath(path)}
                        >
                          <TrashIcon className="size-3.5" />
                        </Button>
                      </div>
                    ))}
                    <Button size="sm" variant="secondary" onPress={() => setAddPathOpen(true)}>
                      {t("Add Proton folder", "添加 Proton 目录")}
                    </Button>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label>{t("Default Proton", "默认 Proton")}</Label>
                    {protonOptions.length === 0 ? (
                      <div className="flex items-start gap-3 rounded-xl border border-warning/40 bg-warning-soft/40 px-3 py-2.5">
                        <AlertIcon className="mt-0.5 size-4 shrink-0 text-warning-soft-foreground" />
                        <div className="flex flex-1 flex-col gap-2">
                          <span className="text-xs text-warning-soft-foreground">
                            {t(
                              "No Proton build found. Download one to start playing.",
                              "未找到 Proton，请先下载一个才能开始游戏。",
                            )}
                          </span>
                          <Button size="sm" variant="secondary" onPress={onOpenProton}>
                            {t("Open Proton manager", "打开 Proton 管理器")}
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <Select
                        className="w-full"
                        selectedKey={settings.proton_default || effectiveProton}
                        onSelectionChange={(key) => set("proton_default", String(key))}
                      >
                        <Select.Trigger>
                          <Select.Value />
                          <Select.Indicator />
                        </Select.Trigger>
                        <Select.Popover>
                          <ListBox>
                            {defaultOptions.map((option) => (
                              <ListBox.Item key={option.value} id={option.value} textValue={option.label}>
                                {option.label}
                                <ListBox.ItemIndicator />
                              </ListBox.Item>
                            ))}
                          </ListBox>
                        </Select.Popover>
                      </Select>
                    )}
                  </div>

                  <div className="flex flex-col gap-2">
                    <Label>{t("Language", "语言")}</Label>
                    <Select
                      className="w-full"
                      selectedKey={settings.language}
                      onSelectionChange={(key) => {
                        const next = String(key) as LangChoice;
                        setLang(next);
                        set("language", next);
                      }}
                    >
                      <Select.Trigger>
                        <Select.Value />
                        <Select.Indicator />
                      </Select.Trigger>
                      <Select.Popover>
                        <ListBox>
                          {[
                            ["auto", t("Follow system", "跟随系统")] as [LangChoice, string],
                            ...LANGUAGES.map((entry) => [entry.value, entry.label] as [LangChoice, string]),
                          ].map(([value, label]) => (
                            <ListBox.Item key={value} id={value} textValue={label}>
                              {label}
                              <ListBox.ItemIndicator />
                            </ListBox.Item>
                          ))}
                        </ListBox>
                      </Select.Popover>
                    </Select>
                  </div>

                  <div className="flex flex-col gap-2">
                    <Label>{t("SteamGridDB API key", "SteamGridDB API Key")}</Label>
                    <Input
                      className="w-full"
                      aria-label={t("SteamGridDB API key", "SteamGridDB API Key")}
                      value={settings.steamgriddb_api_key}
                      onChange={(event) => set("steamgriddb_api_key", event.target.value)}
                      placeholder={t("Optional — needed to search cover art", "可选 — 搜索封面时需要")}
                    />
                    <span className="text-xs text-muted">
                      {t(
                        "Create a key at steamgriddb.com/profile/preferences/api.",
                        "在 steamgriddb.com/profile/preferences/api 创建密钥。",
                      )}
                    </span>
                  </div>

                  <div className="flex items-center justify-between gap-4 rounded-2xl border border-border/50 bg-surface/40 p-3">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">
                        {t("Desktop notifications", "桌面通知")}
                      </span>
                      <span className="text-xs text-muted">
                        {notifyPath
                          ? t("Notify me when a game exits.", "游戏退出时通知我。")
                          : t(
                              "notify-send is not installed — notifications are unavailable.",
                              "未安装 notify-send — 通知功能不可用。",
                            )}
                      </span>
                    </div>
                    <Switch
                      aria-label={t("Desktop notifications", "桌面通知")}
                      isSelected={settings.notifications}
                      isDisabled={!notifyPath}
                      onChange={(value) => set("notifications", value)}
                    >
                      <Switch.Content>
                        <Switch.Control>
                          <Switch.Thumb />
                        </Switch.Control>
                      </Switch.Content>
                    </Switch>
                  </div>

                  <div className="flex items-center justify-between gap-4 rounded-2xl border border-border/50 bg-surface/40 p-3">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">
                        {t("Verbose Proton log", "详细 Proton 日志")}
                      </span>
                      <span className="text-xs text-muted">
                        {t(
                          "Also writes Proton's own steam-*.log next to the run log. Useful for debugging, costs disk space and start-up time.",
                          "同时在运行日志旁生成 Proton 自己的 steam-*.log。排查问题有用，但会占用磁盘并拖慢启动。",
                        )}
                      </span>
                    </div>
                    <Switch
                      aria-label={t("Verbose Proton log", "详细 Proton 日志")}
                      isSelected={settings.proton_log}
                      onChange={(value) => set("proton_log", value)}
                    >
                      <Switch.Content>
                        <Switch.Control>
                          <Switch.Thumb />
                        </Switch.Control>
                      </Switch.Content>
                    </Switch>
                  </div>

                  <div className="flex flex-col gap-2 rounded-2xl border border-border/50 bg-surface/40 p-3">
                    <span className="text-sm font-medium">{t("Desktop", "桌面集成")}</span>
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex flex-col">
                        <span className="text-sm">{t("Tray icon", "托盘图标")}</span>
                        <span
                          className={`text-xs ${info && !info.tray_host ? "text-warning" : "text-muted"}`}
                        >
                          {info && !info.tray_host
                            ? t(
                                "This desktop has no StatusNotifierWatcher, so a tray icon cannot be shown. Use the KDE/XFCE panel or the GNOME AppIndicator extension.",
                                "当前桌面没有 StatusNotifierWatcher，无法显示托盘图标。请使用 KDE/XFCE 面板或安装 GNOME AppIndicator 扩展。",
                              )
                            : t(
                                "Keep the launcher in the tray and close the window to it. Takes effect immediately.",
                                "让启动器驻留托盘，关闭窗口时最小化到托盘。切换后立即生效。",
                              )}
                        </span>
                      </div>
                      <Switch
                        aria-label={t("Tray icon", "托盘图标")}
                        isSelected={settings.tray}
                        onChange={(value) => set("tray", value)}
                      >
                        <Switch.Content>
                          <Switch.Control>
                            <Switch.Thumb />
                          </Switch.Control>
                        </Switch.Content>
                      </Switch>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex flex-col">
                        <span className="text-sm">{t("Start with the session", "开机自动启动")}</span>
                        <span className="text-xs text-muted">
                          {t("Adds an autostart entry for your desktop.", "为桌面添加自启动条目。")}
                        </span>
                      </div>
                      <Switch
                        aria-label={t("Start with the session", "开机自动启动")}
                        isSelected={autostartEnabled}
                        onChange={(value) => void toggleAutostart(value)}
                      >
                        <Switch.Content>
                          <Switch.Control>
                            <Switch.Thumb />
                          </Switch.Control>
                        </Switch.Content>
                      </Switch>
                    </div>
                  </div>

                  <div className="flex flex-col gap-2 rounded-2xl border border-border/50 bg-surface/40 p-3">
                    <span className="text-sm font-medium">{t("Detected tools", "检测到的工具")}</span>
                    {(
                      [
                        ["mangohud", "MangoHud"],
                        ["gamemoderun", "GameMode"],
                        ["gamescope", "Gamescope"],
                        ["kwin", "kwin_wayland"],
                        ["systemd_inhibit", "systemd-inhibit"],
                        ["notify_send", "notify-send"],
                        ["icoextract", "icoextract"],
                      ] as const
                    ).map(([key, label]) => {
                      const path = info?.tools[key] ?? null;
                      const configurable = key !== "icoextract";
                      const override = settings.tool_paths?.[key] ?? "";
                      return (
                        <div key={key} className="flex flex-col gap-1 rounded-xl bg-surface-secondary/30 p-2">
                          <div className="flex items-start gap-2 text-xs">
                            {path ? (
                              <CheckIcon className="mt-0.5 size-3.5 shrink-0 text-success" />
                            ) : (
                              <AlertIcon className="mt-0.5 size-3.5 shrink-0 text-warning" />
                            )}
                            <span className="flex min-w-0 flex-1 flex-col">
                              <span className="text-[13px]">{label}</span>
                              <span className="truncate font-mono text-[10px] text-muted">
                                {path === "available"
                                  ? t("available", "可用")
                                  : (path ??
                                    t(
                                      "Not installed — related options are disabled",
                                      "未安装 — 相关选项已禁用",
                                    ))}
                              </span>
                            </span>
                          </div>
                          {configurable && (
                            <div className="flex gap-2">
                              <Input
                                className="flex-1 font-mono text-[11px]"
                                aria-label={t(`${label} path`, `${label} 路径`)}
                                placeholder={t(
                                  "Override path — empty means auto-detect",
                                  "自定义路径 — 留空则自动检测",
                                )}
                                value={override}
                                onChange={(event) => setToolPath(key, event.target.value)}
                              />
                              <Button
                                isIconOnly
                                size="sm"
                                variant="secondary"
                                aria-label={t("Browse for path", "浏览路径")}
                                onPress={() => setBrowse({mode: "file", field: `tool:${key}`})}
                              >
                                <FolderIcon className="size-4" />
                              </Button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label>{t("GitHub API token", "GitHub API Token")}</Label>
                    <Input
                      aria-label={t("GitHub API token", "GitHub API Token")}
                      type="password"
                      placeholder="ghp_… (optional)"
                      value={settings.github_token}
                      onChange={(event) => set("github_token", event.target.value)}
                    />
                    <p className="text-xs text-muted">
                      {t(
                        "Raising the GitHub rate limit is needed when browsing Proton releases.",
                        "浏览 Proton 版本列表时，需要提高 GitHub 的速率限制。",
                      )}
                    </p>
                  </div>
                </div>
              )}
            </Modal.Body>
            <Modal.Footer>
              <Button variant="secondary" slot="close">
                {t("Cancel", "取消")}
              </Button>
              <Button isDisabled={!settings || saving} onPress={() => void save()}>
                {saving ? t("Saving…", "正在保存…") : t("Save", "保存")}
              </Button>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>

      <PathBrowser
        open={browse !== null}
        mode={browse?.mode ?? "directory"}
        initialPath={
          browse && settings
            ? browse.field.startsWith("tool:")
              ? (settings.tool_paths?.[browse.field.slice(5)] ?? "")
              : String(settings[browse.field as keyof Settings] ?? "")
            : undefined
        }
        onClose={() => setBrowse(null)}
        onSelect={(path) => {
          const field = browse?.field;
          if (!field) return;
          if (field.startsWith("tool:")) {
            setToolPath(field.slice(5), path);
          } else {
            setSettings((current) =>
              current ? {...current, [field as keyof Settings]: path} : current,
            );
          }
        }}
      />

      <PathBrowser
        open={addPathOpen}
        mode="directory"
        title={t("Select a Proton build or compatibilitytools folder", "选择 Proton 版本或 compatibilitytools 目录")}
        onClose={() => setAddPathOpen(false)}
        onSelect={(path) => {
          void addProtonPath(path);
        }}
      />
    </>
  );
}
