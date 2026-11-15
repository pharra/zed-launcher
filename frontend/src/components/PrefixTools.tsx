import {useEffect, useRef, useState} from "react";
import {Button, Chip, Input, Label, ListBox, Modal, ScrollShadow, Select, toast} from "@heroui/react";

import {api, formatSize, runEventsUrl} from "../lib/api";
import {useT} from "../lib/i18n";
import {statusLabel} from "../lib/status";
import type {Game, PrefixToolKind, ProtonBuild, ShortcutCandidate} from "../lib/types";
import {FolderIcon, RefreshIcon, TerminalIcon} from "./icons";
import {PathBrowser} from "./PathBrowser";

interface PrefixToolsProps {
  game: Game | null;
  protons: ProtonBuild[];
  onClose: () => void;
}

const toolText: Record<PrefixToolKind, [string, string, string, string]> = {
  exe: ["Run a file", "运行文件", "Run any executable or .reg file inside the prefix", "在 prefix 中运行任意可执行文件或 .reg 文件"],
  winecfg: ["Winecfg", "Winecfg", "Open the Wine configuration panel", "打开 Wine 配置面板"],
  winetricks: ["Winetricks", "Winetricks", "Install runtime components by verb", "按 verb 安装运行时组件"],
  regedit: ["Regedit", "Regedit", "Import a .reg file into the prefix", "将 .reg 文件导入 prefix"],
};

export function PrefixTools({game, protons, onClose}: PrefixToolsProps) {
  const {lang, t} = useT();
  const [kind, setKind] = useState<PrefixToolKind>("exe");
  const [protonPath, setProtonPath] = useState("");
  const [target, setTarget] = useState("");
  const [args, setArgs] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [lines, setLines] = useState<string[]>([]);
  const [candidates, setCandidates] = useState<ShortcutCandidate[]>([]);
  const [prefixSize, setPrefixSize] = useState<number | null>(null);
  const [scanning, setScanning] = useState(false);
  const [leftovers, setLeftovers] = useState<number | null>(null);
  const [cleaning, setCleaning] = useState(false);
  const [presets, setPresets] = useState<Array<{id: string; verbs: string; label: string; chinese: string}>>(
    [],
  );
  const [browseFile, setBrowseFile] = useState<null | "exe" | "regedit">(null);
  const [maintenance, setMaintenance] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!game) return;
    setKind("exe");
    setProtonPath(game.proton_path);
    setTarget("");
    setArgs("");
    setRunId(null);
    setStatus("");
    setLines([]);
    setCandidates([]);
    setPrefixSize(null);
    setLeftovers(null);
  }, [game]);

  useEffect(() => {
    endRef.current?.scrollIntoView({block: "end"});
  }, [lines]);

  useEffect(() => {
    if (!game) return;
    api
      .prefixPresets()
      .then(setPresets)
      .catch(() => setPresets([]));
  }, [game]);

  useEffect(() => {
    if (!runId) return;
    const socket = new WebSocket(runEventsUrl(runId));
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data) as {type: string; line?: string; status?: string; lines?: string[]};
      if (data.type === "snapshot") {
        setLines(data.lines ?? []);
        if (data.status) setStatus(data.status);
      } else if (data.type === "log" && data.line !== undefined) {
        setLines((current) => [...current.slice(-499), data.line as string]);
      } else if (data.type === "exit") {
        setStatus(data.status ?? "exited");
      }
    };
    return () => socket.close();
  }, [runId]);

  async function scan() {
    if (!game) return;
    setScanning(true);
    try {
      const result = await api.scanPrefix(game.prefix_path);
      const unique = new Map<string, ShortcutCandidate>();
      for (const entry of result.candidates.length ? result.candidates : result.fallback) {
        unique.set(entry.path, entry);
      }
      setCandidates([...unique.values()]);
      setPrefixSize(result.size);
    } catch (error) {
      toast.danger(t("Could not scan the prefix", "无法扫描 prefix"), {
        description: String((error as Error).message),
      });
    } finally {
      setScanning(false);
    }
  }

  async function checkLeftovers() {
    if (!game) return;
    try {
      const result = await api.prefixProcesses(game.prefix_path);
      setLeftovers(result.count);
      if (result.count === 0) {
        toast.success(t("No leftover Wine processes", "没有残留的 Wine 进程"));
      }
    } catch (error) {
      toast.danger(t("Could not list Wine processes", "无法列出 Wine 进程"), {
        description: String((error as Error).message),
      });
    }
  }

  async function cleanupLeftovers() {
    if (!game) return;
    setCleaning(true);
    try {
      const result = await api.cleanupPrefix(game.prefix_path);
      setLeftovers(result.remaining);
      toast.success(
        t(`Terminated ${result.killed} processes`, `已结束 ${result.killed} 个进程`),
      );
    } catch (error) {
      toast.danger(t("Could not clean up the prefix", "无法清理该 prefix"), {
        description: String((error as Error).message),
      });
    } finally {
      setCleaning(false);
    }
  }

  async function cleanTemp() {
    if (!game) return;
    setMaintenance(true);
    try {
      const result = await api.cleanupTemp(game.prefix_path);
      setPrefixSize(result.size);
      toast.success(t(`Freed ${formatSize(result.freed)}`, `已释放 ${formatSize(result.freed)}`));
    } catch (error) {
      toast.danger(t("Could not clean the temporary files", "无法清理临时文件"), {
        description: String((error as Error).message),
      });
    } finally {
      setMaintenance(false);
    }
  }

  async function clonePrefix() {
    if (!game) return;
    setMaintenance(true);
    try {
      const result = await api.clonePrefix(game.prefix_path, `${game.title} copy`);
      toast.success(t("Prefix cloned", "Prefix 已克隆"), {description: result.path});
    } catch (error) {
      toast.danger(t("Could not clone the prefix", "无法克隆 prefix"), {
        description: String((error as Error).message),
      });
    } finally {
      setMaintenance(false);
    }
  }

  async function run() {
    if (!game) return;
    try {
      const result = await api.runPrefixTool({
        prefix_path: game.prefix_path,
        kind,
        proton_path: protonPath,
        target: kind === "exe" || kind === "regedit" ? target : "",
        args,
      });
      setRunId(result.run_id);
      setStatus(result.snapshot.status);
      setLines(result.snapshot.lines ?? []);
    } catch (error) {
      toast.danger(t("Could not start the tool", "无法启动工具"), {
        description: String((error as Error).message),
      });
    }
  }

  const protonOptions = [
    {value: "", label: t("Default", "默认")},
    ...protons.map((build) => ({value: build.path, label: `${build.name} · ${build.source}`})),
  ];

  return (
    <Modal.Backdrop isOpen={game !== null} onOpenChange={(value) => !value && onClose()}>
      <Modal.Container size="lg">
        <Modal.Dialog className="max-h-[88vh]">
          <Modal.CloseTrigger />
          <Modal.Header>
            <Modal.Icon className="bg-default text-foreground">
              <TerminalIcon className="size-5" />
            </Modal.Icon>
            <Modal.Heading>
              {game?.title} · {t("prefix tools", "prefix 工具")}
            </Modal.Heading>
          </Modal.Header>
          <Modal.Body className="overflow-y-auto">
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between gap-2 rounded-xl border border-border/50 bg-surface/40 px-3 py-2">
                <span className="truncate font-mono text-[11px] text-muted">{game?.prefix_path}</span>
                <Button
                  size="sm"
                  variant="secondary"
                  onPress={() => void api.openPath(game?.prefix_path ?? "")}
                >
                  <FolderIcon className="size-3.5" />
                  {t("Open", "打开")}
                </Button>
              </div>

              <div className="flex flex-col gap-2">
                <Label>{t("Tool", "工具")}</Label>
                <Select
                  className="w-full"
                  selectedKey={kind}
                  onSelectionChange={(key) => setKind(String(key) as PrefixToolKind)}
                >
                  <Select.Trigger>
                    <Select.Value />
                    <Select.Indicator />
                  </Select.Trigger>
                  <Select.Popover>
                    <ListBox>
                      {(Object.keys(toolText) as PrefixToolKind[]).map((entry) => (
                        <ListBox.Item
                          key={entry}
                          id={entry}
                          textValue={t(toolText[entry][0], toolText[entry][1])}
                        >
                          {t(toolText[entry][0], toolText[entry][1])}
                          <ListBox.ItemIndicator />
                        </ListBox.Item>
                      ))}
                    </ListBox>
                  </Select.Popover>
                </Select>
                <p className="text-xs text-muted">
                  {t(toolText[kind][2], toolText[kind][3])}
                </p>
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

              {(kind === "exe" || kind === "regedit") && (
                <div className="flex flex-col gap-1.5">
                  <Label>{t("File", "文件")}</Label>
                  <div className="flex gap-2">
                    <Input
                      className="flex-1"
                      aria-label={t("File", "文件")}
                      placeholder={
                        kind === "regedit" ? "/path/to/patch.reg" : "/path/inside/prefix.exe"
                      }
                      value={target}
                      onChange={(event) => setTarget(event.target.value)}
                    />
                    <Button
                      isIconOnly
                      variant="secondary"
                      aria-label={t("Browse for file", "浏览文件")}
                      onPress={() => setBrowseFile(kind)}
                    >
                      <FolderIcon className="size-4" />
                    </Button>
                  </div>
                </div>
              )}

              {kind === "winetricks" && presets.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  <Label>{t("Common presets", "常用预设")}</Label>
                  <div className="flex flex-wrap gap-1.5">
                    {presets.map((preset) => (
                      <Button
                        key={preset.id}
                        size="sm"
                        variant="tertiary"
                        onPress={() =>
                          setArgs((current) => {
                            const verbs = preset.verbs.split(" ");
                            const existing = current.split(/\s+/).filter(Boolean);
                            const merged = [...new Set([...existing, ...verbs])];
                            return merged.join(" ");
                          })
                        }
                      >
                        {lang === "zh" ? preset.chinese : preset.label}
                      </Button>
                    ))}
                  </div>
                </div>
              )}

              {(kind === "winetricks" || kind === "exe") && (
                <div className="flex flex-col gap-1.5">
                  <Label>
                    {kind === "winetricks" ? t("Winetricks verbs", "Winetricks verbs") : t("Arguments", "参数")}
                  </Label>
                  <Input
                    aria-label={t("Arguments", "参数")}
                    placeholder={kind === "winetricks" ? "vcrun2022 corefonts" : "--windowed"}
                    value={args}
                    onChange={(event) => setArgs(event.target.value)}
                  />
                  {kind === "winetricks" && (
                    <p className="text-xs text-muted">
                      {t("umu-run needs at least one verb. Use", "umu-run 至少需要一个 verb。使用")}{" "}
                      <code>settings</code> {t("to open the GUI.", "打开图形界面。")}
                    </p>
                  )}
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                <Button onPress={() => void run()}>{t("Run", "运行")}</Button>
                <Button variant="secondary" isDisabled={scanning} onPress={() => void scan()}>
                  <RefreshIcon className="size-4" />
                  {t("Scan for programs", "扫描程序")}
                </Button>
                <Button variant="secondary" onPress={() => void checkLeftovers()}>
                  {t("Check leftover processes", "检查残留进程")}
                  {leftovers !== null ? ` (${leftovers})` : ""}
                </Button>
                {leftovers !== null && leftovers > 0 && (
                  <Button variant="danger-soft" isDisabled={cleaning} onPress={() => void cleanupLeftovers()}>
                    {cleaning
                      ? t("Cleaning up…", "正在清理…")
                      : t("Terminate them", "结束这些进程")}
                  </Button>
                )}
                <Button variant="secondary" isDisabled={maintenance} onPress={() => void cleanTemp()}>
                  {t("Clean temporary files", "清理临时文件")}
                </Button>
                <Button variant="secondary" isDisabled={maintenance} onPress={() => void clonePrefix()}>
                  {t("Clone prefix", "克隆 prefix")}
                </Button>
              </div>

              {candidates.length > 0 && (
                <div className="flex flex-col gap-1 rounded-xl border border-border/50 bg-surface/40 p-2">
                  <span className="px-2 py-1 text-xs text-muted">
                    {t("Programs found in this prefix", "在此 prefix 中找到的程序")}
                  </span>
                  {candidates.map((entry) => (
                    <button
                      key={entry.path}
                      type="button"
                      className="flex flex-col rounded-lg px-2 py-1.5 text-start hover:bg-surface-secondary"
                      onClick={() => {
                        setKind("exe");
                        setTarget(entry.path);
                      }}
                    >
                      <span className="text-sm">{entry.name}</span>
                      <span className="truncate font-mono text-[10px] text-muted">{entry.path}</span>
                    </button>
                  ))}
                </div>
              )}

              {(lines.length > 0 || runId) && (
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted">{t("Output", "输出")}</span>
                    <Chip size="sm" variant="soft" className="text-[10px]">
                      {statusLabel(status || "starting", t)}
                    </Chip>
                  </div>
                  <ScrollShadow className="h-[30vh] rounded-xl border border-border/50 bg-black/60 p-3 font-mono text-[11px] leading-5">
                    {lines.map((line, index) => (
                      <div key={`${index}-${line.slice(0, 16)}`} className="whitespace-pre-wrap break-all">
                        {line}
                      </div>
                    ))}
                    <div ref={endRef} />
                  </ScrollShadow>
                </div>
              )}

              <p className="text-[11px] text-muted">
                {prefixSize !== null
                  ? t(`Prefix size: ${formatSize(prefixSize)}. `, `Prefix 大小：${formatSize(prefixSize)}。`)
                  : ""}
                {t("Wine tools stay open until you close them.", "Wine 工具会一直运行，直到你关闭它。")}
              </p>
            </div>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" slot="close">
              {t("Close", "关闭")}
            </Button>
          </Modal.Footer>

          <PathBrowser
            open={browseFile !== null}
            mode="file"
            title={
              browseFile === "regedit"
                ? t("Select a .reg file", "选择 .reg 文件")
                : t("Select a file", "选择文件")
            }
            onClose={() => setBrowseFile(null)}
            onSelect={(path) => {
              setTarget(path);
              setBrowseFile(null);
            }}
          />
        </Modal.Dialog>
      </Modal.Container>
    </Modal.Backdrop>
  );
}
