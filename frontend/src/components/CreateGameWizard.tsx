import {useEffect, useRef, useState} from "react";
import {
  Button,
  Chip,
  Input,
  Label,
  ListBox,
  Modal,
  ScrollShadow,
  Select,
  Switch,
  toast,
} from "@heroui/react";

import {api, runEventsUrl} from "../lib/api";
import {useT} from "../lib/i18n";
import {logMutedClass, logPaneClass} from "../lib/styles";
import type {Dependencies, DetectionResult, ProtonBuild, ShortcutCandidate} from "../lib/types";
import {FolderIcon, PlayIcon, RefreshIcon, TerminalIcon} from "./icons";
import {PathBrowser} from "./PathBrowser";

interface CreateGameWizardProps {
  open: boolean;
  protons: ProtonBuild[];
  dependencies: Dependencies | null;
  prefixRoot: string;
  onClose: () => void;
  onCreated: () => void;
}

type Source = "installer" | "exe";
type Step = "source" | "options" | "install" | "finish";

const stepTitles: Record<Step, [string, string]> = {
  source: ["Create a new game", "创建新游戏"],
  options: ["Prefix and Proton", "Prefix 与 Proton"],
  install: ["Run the installer", "运行安装程序"],
  finish: ["Finishing touches", "收尾设置"],
};

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function ArgumentField({
  label,
  description,
  placeholder,
  value,
  onChange,
}: {
  label: string;
  description: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Label>{label}</Label>
      <Input
        aria-label={label}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <span className="text-[11px] text-muted">{description}</span>
    </div>
  );
}

function StepDots({step, steps}: {step: Step; steps: Step[]}) {
  const {t} = useT();
  return (
    <div className="flex items-center gap-2">
      {steps.map((entry, index) => (
        <div key={entry} className="flex items-center gap-2">
          <span
            className={`flex size-6 items-center justify-center rounded-full text-[11px] font-semibold ${
              steps.indexOf(step) >= index
                ? "bg-accent text-accent-foreground"
                : "bg-surface-secondary text-muted"
            }`}
          >
            {index + 1}
          </span>
          <span className={`text-xs ${steps.indexOf(step) === index ? "text-foreground" : "text-muted"}`}>
            {t(...stepTitles[entry])}
          </span>
          {index < steps.length - 1 && <span className="text-muted">›</span>}
        </div>
      ))}
    </div>
  );
}

export function CreateGameWizard({
  open,
  protons,
  dependencies,
  prefixRoot,
  onClose,
  onCreated,
}: CreateGameWizardProps) {
  const {t} = useT();
  const [step, setStep] = useState<Step>("source");
  const [source, setSource] = useState<Source | null>(null);
  const [installerPath, setInstallerPath] = useState("");
  const [exePath, setExePath] = useState("");
  const [title, setTitle] = useState("");
  const [prefixName, setPrefixName] = useState("");
  const [protonPath, setProtonPath] = useState("");
  const [browse, setBrowse] = useState<null | "installer" | "exe" | "chosen" | "cover">(null);
  const [coverSource, setCoverSource] = useState<string | null>(null);
  const [toggles, setToggles] = useState({
    mangohud: false,
    gamemode: false,
    gamescope: false,
    no_sleep: false,
    wayland: false,
    wow64: false,
  });
  const [toolArgs, setToolArgs] = useState({gamescope_args: "", mangohud_args: ""});
  const [installId, setInstallId] = useState<string | null>(null);
  const [installPrefix, setInstallPrefix] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<string>("");
  const [lines, setLines] = useState<string[]>([]);
  const [installing, setInstalling] = useState(false);
  const [detection, setDetection] = useState<DetectionResult | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [chosenExe, setChosenExe] = useState("");
  const [saving, setSaving] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  const reset = () => {
    setStep("source");
    setSource(null);
    setInstallerPath("");
    setExePath("");
    setTitle("");
    setPrefixName("");
    setProtonPath("");
    setBrowse(null);
    setCoverSource(null);
    setToggles({
      mangohud: false,
      gamemode: false,
      gamescope: false,
      no_sleep: false,
      wayland: false,
      wow64: false,
    });
    setToolArgs({gamescope_args: "", mangohud_args: ""});
    setInstallId(null);
    setInstallPrefix("");
    setRunId(null);
    setRunStatus("");
    setLines([]);
    setInstalling(false);
    setDetection(null);
    setDetecting(false);
    setChosenExe("");
  };

  useEffect(() => {
    if (open) reset();
  }, [open]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({block: "end"});
  }, [lines]);

  useEffect(() => {
    if (!runId) return;
    const socket = new WebSocket(runEventsUrl(runId));
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data) as {
        type: string;
        line?: string;
        status?: string;
        lines?: string[];
      };
      if (data.type === "snapshot") {
        setLines(data.lines ?? []);
        if (data.status) setRunStatus(data.status);
      } else if (data.type === "log" && data.line !== undefined) {
        setLines((current) => [...current.slice(-999), data.line as string]);
      } else if (data.type === "status" && data.status) {
        setRunStatus(data.status);
      } else if (data.type === "exit") {
        setRunStatus(data.status ?? "exited");
        setInstalling(false);
        void runDetection();
      }
    };
    return () => socket.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  async function runDetection(id = installId) {
    if (!id) return;
    setDetecting(true);
    try {
      const result = await api.detectInstall(id);
      setDetection(result);
      if (result.best) setChosenExe(result.best);
      if (!result.best) {
        toast.warning(t("Could not find the installed program", "未能自动找到安装的程序"), {
          description: t("Pick it manually to finish.", "请手动选择以完成创建。"),
        });
      }
    } catch (error) {
      toast.danger(t("Could not scan the prefix", "无法扫描 prefix"), {
        description: String((error as Error).message),
      });
    } finally {
      setDetecting(false);
    }
  }

  async function startInstall() {
    if (!installerPath) return;
    setInstalling(true);
    setLines([]);
    setDetection(null);
    try {
      const result = await api.startInstaller({
        installer: installerPath,
        title: title || prefixName,
        prefix_name: prefixName,
        proton_path: protonPath,
      });
      setInstallId(result.install_id);
      setInstallPrefix(result.prefix_path);
      setRunId(result.run_id);
      setRunStatus(result.snapshot.status);
    } catch (error) {
      setInstalling(false);
      toast.danger(t("Could not run the installer", "无法运行安装程序"), {
        description: String((error as Error).message),
      });
    }
  }

  async function finish() {
    if (!chosenExe) {
      toast.warning(t("Choose the game executable first", "请先选择游戏可执行文件"));
      return;
    }
    setSaving(true);
    try {
      const game = await api.createGame({
        mode: "create",
        title: title || prefixName,
        path: chosenExe,
        prefix_name: prefixName,
        proton_path: protonPath,
        install_id: installId ?? "",
        ...toggles,
        ...toolArgs,
      });
      if (coverSource) {
        await api.setArtwork(game.id, coverSource);
      }
      toast.success(t("Game created", "已创建游戏"), {description: game.title});
      onCreated();
      setInstallId(null);
      reset();
      onClose();
    } catch (error) {
      toast.danger(t("Could not create the game", "无法创建游戏"), {
        description: String((error as Error).message),
      });
    } finally {
      setSaving(false);
    }
  }

  /** Closing before the game exists throws away the half-finished install. */
  function abandon() {
    const pending = installId;
    setInstallId(null);
    if (pending) {
      void api.deleteInstall(pending, true).catch(() => undefined);
    }
    reset();
    onClose();
  }

  const steps: Step[] = source === "installer" ? ["source", "options", "install", "finish"] : ["source", "options", "finish"];
  const protonOptions = [
    {
      value: "",
      label: protons[0]
        ? t(`Default (${protons[0].name})`, `默认（${protons[0].name}）`)
        : t("Default (none found)", "默认（未找到）"),
    },
    ...protons.map((build) => ({value: build.path, label: `${build.name} · ${build.source}`})),
  ];
  const primaryPath = source === "installer" ? installerPath : exePath;
  const prefixPreview = installPrefix || `${prefixRoot.replace(/\/$/, "")}/${prefixName || slugify(title) || "prefix"}`;

  function applyPath(path: string) {
    const name = path.split("/").filter(Boolean).pop() ?? "";
    const stem = name.replace(/\.(exe|msi|EXE|MSI)$/, "");
    if (source === "installer") {
      setInstallerPath(path);
      if (!title) {
        const cleaned = stem.replace(/[\s._-]+(setup|installer|install)$/i, "").trim();
        setTitle(cleaned || stem);
      }
    } else {
      setExePath(path);
      if (!title) setTitle(stem);
      setChosenExe(path);
    }
    if (!prefixName) setPrefixName(slugify(stem));
  }

  function next() {
    if (step === "source") {
      if (!source) {
        toast.warning(t("Choose how you want to start", "请选择游戏来源"));
        return;
      }
      setStep("options");
      return;
    }
    if (step === "options") {
      if (!primaryPath) {
        toast.warning(
          source === "installer"
            ? t("Choose the installer", "请选择安装程序")
            : t("Choose the executable", "请选择可执行文件"),
        );
        return;
      }
      if (!prefixName) {
        toast.warning(t("Give the prefix a folder name", "请填写 prefix 文件夹名"));
        return;
      }
      if (source === "installer") {
        setStep("install");
      } else {
        setStep("finish");
      }
      return;
    }
    if (step === "install") {
      if (!chosenExe) {
        toast.warning(t("Select the program the installer added", "请选择安装程序添加的游戏"));
        return;
      }
      setStep("finish");
    }
  }

  function back() {
    const index = steps.indexOf(step);
    if (index > 0) setStep(steps[index - 1]);
  }

  const canNext =
    step === "install"
      ? Boolean(chosenExe)
      : step === "options"
        ? Boolean(primaryPath && prefixName)
        : true;

  return (
    <>
      <Modal.Backdrop isOpen={open} onOpenChange={(value) => !value && abandon()}>
        <Modal.Container size="lg">
          <Modal.Dialog className="max-h-[92vh]">
            <Modal.CloseTrigger />
            <Modal.Header className="gap-2">
              <Modal.Heading>{t(...stepTitles[step])}</Modal.Heading>
              <StepDots step={step} steps={steps} />
            </Modal.Header>
            <Modal.Body className="overflow-y-auto">
              {step === "source" && (
                <div className="flex flex-col gap-3">
                  <p className="text-sm text-muted">
                    {t(
                      "A dedicated Wine prefix is created for this game. Choose where the game comes from.",
                      "会为这个游戏创建独立的 Wine prefix。请选择游戏来源。",
                    )}
                  </p>
                  <button
                    type="button"
                    className={`flex items-start gap-4 rounded-2xl border p-4 text-start transition-colors ${
                      source === "installer"
                        ? "border-accent bg-accent-soft/40"
                        : "border-border/60 bg-surface/40 hover:bg-surface-secondary"
                    }`}
                    onClick={() => setSource("installer")}
                  >
                    <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-accent-soft text-accent-soft-foreground">
                      <TerminalIcon className="size-5" />
                    </span>
                    <span className="flex flex-col gap-1">
                      <span className="text-sm font-semibold">
                        {t("Install from an installer", "通过安装程序安装")}
                      </span>
                      <span className="text-xs text-muted">
                        {t(
                          "Pick a setup.exe or .msi. The launcher runs it inside the new prefix, then looks for the program it installed.",
                          "选择 setup.exe 或 .msi。启动器会在新 prefix 中运行它，然后自动寻找安装出的程序。",
                        )}
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    className={`flex items-start gap-4 rounded-2xl border p-4 text-start transition-colors ${
                      source === "exe"
                        ? "border-accent bg-accent-soft/40"
                        : "border-border/60 bg-surface/40 hover:bg-surface-secondary"
                    }`}
                    onClick={() => setSource("exe")}
                  >
                    <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-accent-soft text-accent-soft-foreground">
                      <PlayIcon className="size-5 translate-x-[1px]" />
                    </span>
                    <span className="flex flex-col gap-1">
                      <span className="text-sm font-semibold">
                        {t("I already have the game executable", "我已经有游戏可执行文件")}
                      </span>
                      <span className="text-xs text-muted">
                        {t(
                          "Skip the installer and point straight at the .exe. A fresh prefix is still created so the game gets a clean environment.",
                          "跳过安装步骤，直接选择 .exe。仍会创建全新的 prefix，保证干净的环境。",
                        )}
                      </span>
                    </span>
                  </button>
                </div>
              )}

              {step === "options" && (
                <div className="flex flex-col gap-4">
                  <div className="flex flex-col gap-1.5">
                    <Label>
                      {source === "installer"
                        ? t("Installer", "安装程序")
                        : t("Game executable", "游戏可执行文件")}
                    </Label>
                    <div className="flex gap-2">
                      <Input
                        aria-label={
                          source === "installer"
                            ? t("Installer", "安装程序")
                            : t("Game executable", "游戏可执行文件")
                        }
                        className="flex-1"
                        placeholder={
                          source === "installer"
                            ? "/home/you/Downloads/setup.exe"
                            : "/home/you/Games/Game/game.exe"
                        }
                        value={primaryPath}
                        onChange={(event) =>
                          source === "installer"
                            ? setInstallerPath(event.target.value)
                            : applyPath(event.target.value)
                        }
                      />
                      <Button
                        isIconOnly
                        variant="secondary"
                        aria-label={t("Browse", "浏览")}
                        onPress={() => setBrowse(source === "installer" ? "installer" : "exe")}
                      >
                        <FolderIcon className="size-4" />
                      </Button>
                    </div>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label>{t("Title", "标题")}</Label>
                    <Input
                      aria-label={t("Title", "标题")}
                      placeholder={t("Game title", "游戏名称")}
                      value={title}
                      onChange={(event) => setTitle(event.target.value)}
                    />
                  </div>

                  <div className="flex flex-col gap-2 rounded-xl border border-border/50 bg-surface/40 p-3">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-sm font-medium">
                        {t("New Wine prefix", "新的 Wine prefix")}
                      </span>
                      <span className="text-xs text-muted">
                        {t(
                          "Created for this game only; nothing else uses it.",
                          "仅用于这个游戏，其他游戏不会共用。",
                        )}
                      </span>
                    </div>
                    <div className="flex gap-2">
                      <Input
                        aria-label={t("Prefix folder name", "Prefix 文件夹名")}
                        className="flex-1"
                        placeholder={t("my-game", "my-game")}
                        value={prefixName}
                        onChange={(event) => setPrefixName(event.target.value)}
                      />
                    </div>
                    <div className="rounded-lg bg-surface-secondary/60 px-3 py-2 font-mono text-[11px] text-muted">
                      {prefixPreview}
                    </div>
                  </div>

                  <Select
                    className="w-full"
                    selectedKey={protonPath}
                    onSelectionChange={(key) => setProtonPath(String(key))}
                  >
                    <Label>{t("Proton", "Proton")}</Label>
                    <Select.Trigger>
                      <Select.Value />
                      <Select.Indicator />
                    </Select.Trigger>
                    <Select.Popover>
                      <ListBox>
                        {protonOptions.map((option) => (
                          <ListBox.Item key={option.value} id={option.value} textValue={option.label}>
                            {option.label}
                            <ListBox.ItemIndicator />
                          </ListBox.Item>
                        ))}
                      </ListBox>
                    </Select.Popover>
                  </Select>
                </div>
              )}

              {step === "install" && (
                <div className="flex flex-col gap-3">
                  <div className="flex items-center justify-between gap-3 rounded-xl border border-border/50 bg-surface/40 px-3 py-2">
                    <div className="flex min-w-0 flex-col">
                      <span className="text-sm">{installerPath.split("/").pop()}</span>
                      <span className="truncate font-mono text-[11px] text-muted">{prefixPreview}</span>
                    </div>
                    <Chip size="sm" variant="soft" className="text-[10px]">
                      {runStatus || t("ready", "就绪")}
                    </Chip>
                  </div>

                  <div className="flex gap-2">
                    <Button isDisabled={installing} onPress={() => void startInstall()}>
                      {installing
                        ? t("Installer running…", "安装程序运行中…")
                        : runId
                          ? t("Run installer again", "重新运行安装程序")
                          : t("Run installer", "运行安装程序")}
                    </Button>
                    {installId && (
                      <Button variant="secondary" isDisabled={detecting} onPress={() => void runDetection()}>
                        <RefreshIcon className="size-4" />
                        {t("Scan again", "重新扫描")}
                      </Button>
                    )}
                  </div>

                  <p className="text-xs text-muted">
                    {t(
                      "The installer opens in its own window. Wait until it finishes; the log below shows what the launcher is doing.",
                      "安装程序会弹出独立窗口，请等待其完成；下方日志显示启动器正在做什么。",
                    )}
                  </p>

                  <ScrollShadow className={`h-[26vh] ${logPaneClass}`}>
                    {lines.length === 0 ? (
                      <p className={logMutedClass}>{t("No output yet.", "暂无输出。")}</p>
                    ) : (
                      lines.map((line, index) => (
                        <div key={`${index}-${line.slice(0, 16)}`} className="whitespace-pre-wrap break-all">
                          {line}
                        </div>
                      ))
                    )}
                    <div ref={logEndRef} />
                  </ScrollShadow>

                  {detection && (
                    <div className="flex flex-col gap-2 rounded-xl border border-border/50 bg-surface/40 p-3">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-sm font-medium">
                          {detection.candidates.length > 0
                            ? t("The installer added these programs", "安装程序添加了这些程序")
                            : t("No new shortcuts were found", "没有发现新的快捷方式")}
                        </span>
                        <span className="text-xs text-muted">
                          {detection.candidates.length > 0
                            ? t("Pick the game to launch.", "请选择要启动的游戏。")
                            : t("Choose the executable the installer created.", "请选择安装程序生成的可执行文件。")}
                        </span>
                      </div>
                      <div className="flex flex-col gap-1">
                        {(detection.candidates.length ? detection.candidates : detection.fallback).map(
                          (entry: ShortcutCandidate) => (
                            <button
                              key={entry.path}
                              type="button"
                              className={`flex flex-col rounded-lg px-3 py-2 text-start ${
                                chosenExe === entry.path
                                  ? "bg-accent-soft/60 ring-1 ring-accent"
                                  : "hover:bg-surface-secondary"
                              }`}
                              onClick={() => setChosenExe(entry.path)}
                            >
                              <span className="text-sm">{entry.name}</span>
                              <span className="truncate font-mono text-[10px] text-muted">
                                {entry.path}
                              </span>
                            </button>
                          ),
                        )}
                      </div>
                      <Button size="sm" variant="secondary" onPress={() => setBrowse("chosen")}>
                        {t("Choose file manually…", "手动选择文件…")}
                      </Button>
                      {chosenExe && (
                        <div className="rounded-lg bg-surface-secondary/60 px-3 py-2 font-mono text-[10px]">
                          {chosenExe}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {step === "finish" && (
                <div className="flex flex-col gap-4">
                  <div className="flex flex-col gap-1 rounded-xl border border-border/50 bg-surface/40 p-3">
                    <span className="text-sm font-medium">{title || prefixName}</span>
                    <span className="truncate font-mono text-[11px] text-muted">{chosenExe || exePath}</span>
                    <span className="truncate font-mono text-[11px] text-muted">{prefixPreview}</span>
                  </div>

                  <div className="flex items-center gap-3 rounded-xl border border-border/50 bg-surface/40 p-3">
                    <div className="flex size-20 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-surface-secondary">
                      {coverSource ? (
                        <img alt="" className="size-full object-cover" src={coverSource} />
                      ) : (
                        <span className="text-[10px] text-muted">No cover</span>
                      )}
                    </div>
                    <div className="flex min-w-0 flex-col gap-1">
                      <span className="text-sm font-medium">{t("Cover image", "封面图片")}</span>
                      <span className="truncate text-xs text-muted">
                        {coverSource ?? t("Optional — PNG, JPEG, WebP or AVIF", "可选 — PNG、JPEG、WebP 或 AVIF")}
                      </span>
                      <div className="flex gap-2">
                        <Button size="sm" variant="secondary" onPress={() => setBrowse("cover")}>
                          {t("Choose…", "选择…")}
                        </Button>
                        {coverSource && (
                          <Button size="sm" variant="tertiary" onPress={() => setCoverSource(null)}>
                            {t("Remove", "移除")}
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-2 sm:grid-cols-2">
                    {(
                      [
                        ["mangohud", t("MangoHud", "MangoHud"), t("Performance overlay", "性能浮层"), "mangohud"],
                        ["gamemode", t("GameMode", "GameMode"), t("Request performance mode", "请求性能模式"), "gamemoderun"],
                        ["gamescope", t("Gamescope", "Gamescope"), t("Nested compositor", "嵌套合成器"), "gamescope"],
                        ["no_sleep", t("Prevent sleep", "阻止休眠"), t("Inhibit suspend", "运行期间禁止挂起"), "systemd_inhibit"],
                        ["wayland", t("Wayland driver", "Wayland 驱动"), "PROTON_ENABLE_WAYLAND", null],
                        ["wow64", t("WOW64", "WOW64"), "PROTON_USE_WOW64", null],
                      ] as const
                    ).map(([key, label, description, dependency]) => {
                      const available =
                        dependency === null ||
                        Boolean(dependencies?.optional[dependency]?.available);
                      const hint = available
                        ? description
                        : t(`${label} is not installed`, `${label} 未安装`);
                      return (
                        <div
                          key={key}
                          className={`flex min-w-0 items-center justify-between gap-3 overflow-hidden rounded-xl border px-3 py-2 ${
                            available
                              ? "border-border/50 bg-surface/40"
                              : "border-border/30 bg-surface/20 opacity-70"
                          }`}
                          title={hint}
                        >
                          <div className="flex min-w-0 flex-1 flex-col">
                            <span className="text-sm">{label}</span>
                            <span
                              className={`text-[11px] leading-snug break-all ${
                                available ? "text-muted" : "text-warning"
                              }`}
                            >
                              {hint}
                            </span>
                          </div>
                          <div className="shrink-0">
                            <Switch
                              size="sm"
                              isDisabled={!available}
                              isSelected={available && toggles[key]}
                              onChange={(value) => setToggles((current) => ({...current, [key]: value}))}
                            >
                              <Switch.Content>
                                <Switch.Control>
                                  <Switch.Thumb />
                                </Switch.Control>
                              </Switch.Content>
                            </Switch>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {(toggles.gamescope || toggles.mangohud) && (
                    <div className="flex flex-col gap-2 rounded-xl border border-border/50 bg-surface/40 p-3">
                      <span className="text-sm font-medium">{t("Tool arguments", "工具参数")}</span>
                      {toggles.gamescope && (
                        <ArgumentField
                          label={t("Gamescope arguments", "Gamescope 参数")}
                          placeholder="-f -W 1920 -H 1080"
                          value={toolArgs.gamescope_args}
                          description={t("Defaults to -f.", "留空时使用 -f。")}
                          onChange={(value) =>
                            setToolArgs((current) => ({...current, gamescope_args: value}))
                          }
                        />
                      )}
                      {toggles.mangohud && (
                        <ArgumentField
                          label={t("MangoHud arguments", "MangoHud 参数")}
                          placeholder="--dlsym"
                          value={toolArgs.mangohud_args}
                          description={t("Passed straight to mangohud.", "直接传给 mangohud。")}
                          onChange={(value) =>
                            setToolArgs((current) => ({...current, mangohud_args: value}))
                          }
                        />
                      )}
                    </div>
                  )}
                </div>
              )}
            </Modal.Body>
            <Modal.Footer className="justify-between">
              <span className="text-[11px] text-muted">
                {step === "install" && installId
                  ? t(`Session ${installId}`, `会话 ${installId}`)
                  : step === "finish"
                    ? t("Review the details and create the game", "确认信息后创建游戏")
                    : ""}
              </span>
              <div className="flex gap-2">
                <Button variant="secondary" slot="close">
                  {t("Cancel", "取消")}
                </Button>
                {steps.indexOf(step) > 0 && (
                  <Button variant="secondary" onPress={back}>
                    {t("Back", "上一步")}
                  </Button>
                )}
                {step === "finish" ? (
                  <Button isDisabled={saving} onPress={() => void finish()}>
                    {saving ? t("Creating…", "正在创建…") : t("Create game", "创建游戏")}
                  </Button>
                ) : (
                  <Button isDisabled={!canNext} onPress={next}>
                    {t("Next", "下一步")}
                  </Button>
                )}
              </div>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>

      <PathBrowser
        open={browse !== null}
        mode="file"
        title={
          browse === "cover"
            ? t("Select a cover image", "选择封面图片")
            : browse === "chosen"
              ? t("Select the installed game executable", "选择安装后的游戏可执行文件")
              : browse === "installer"
                ? t("Select the installer", "选择安装程序")
                : t("Select the game executable", "选择游戏可执行文件")
        }
        initialPath={
          browse === "chosen"
            ? `${prefixPreview}/drive_c`
            : browse === "installer"
              ? installerPath
              : browse === "cover"
                ? undefined
                : exePath
        }
        onClose={() => setBrowse(null)}
        onSelect={(path) => {
          if (browse === "cover") {
            setCoverSource(path);
            return;
          }
          if (browse === "chosen") {
            setChosenExe(path);
            if (!title) setTitle(path.split("/").filter(Boolean).pop()?.replace(/\.exe$/i, "") ?? "");
            return;
          }
          applyPath(path);
        }}
      />
    </>
  );
}
