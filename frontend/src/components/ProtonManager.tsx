import {useCallback, useEffect, useState} from "react";
import {Button, Chip, Input, Modal, ScrollShadow, Spinner, Tabs, toast} from "@heroui/react";

import {api, formatDate, formatSize} from "../lib/api";
import {useT} from "../lib/i18n";
import {sourceLabel} from "../lib/status";
import type {ProtonBuild, ProtonJob, ProtonRelease, ProtonSource} from "../lib/types";
import {AlertIcon, CpuIcon, RefreshIcon, TrashIcon} from "./icons";

interface ProtonManagerProps {
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
}

export function ProtonManager({open, onClose, onChanged}: ProtonManagerProps) {
  const {lang, t} = useT();
  const [builds, setBuilds] = useState<ProtonBuild[]>([]);
  const [sources, setSources] = useState<ProtonSource[]>([]);
  const [releases, setReleases] = useState<ProtonRelease[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [job, setJob] = useState<ProtonJob | null>(null);
  const [busyTag, setBusyTag] = useState<string | null>(null);
  const [token, setToken] = useState("");

  const loadBuilds = useCallback(async () => {
    const data = await api.protons();
    setBuilds(data.builds);
    setSources(data.sources);
    setToken((current) => current);
  }, []);

  const loadReleases = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReleases(await api.releases(25));
    } catch (caught) {
      setError(String((caught as Error).message));
      setReleases([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    setJob(null);
    setBusyTag(null);
    setReleases(null);
    void loadBuilds().catch((caught: Error) =>
      toast.danger(t("Could not read Proton builds", "无法读取 Proton 版本"), {
        description: caught.message,
      }),
    );
    void loadReleases();
  }, [open, loadBuilds, loadReleases]);

  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const timer = setInterval(async () => {
      try {
        const next = await api.protonJob(job.id);
        setJob(next);
        if (next.status === "done") {
          toast.success(t(`${next.tag} installed`, `已安装 ${next.tag}`));
          setBusyTag(null);
          await loadBuilds();
          onChanged();
        } else if (next.status === "failed") {
          toast.danger(t(`Could not install ${next.tag}`, `无法安装 ${next.tag}`), {
            description: next.error,
          });
          setBusyTag(null);
        }
      } catch (caught) {
        setJob(null);
        setBusyTag(null);
        toast.danger(t("Lost track of the download", "下载状态已丢失"), {
          description: String((caught as Error).message),
        });
      }
    }, 700);
    return () => clearInterval(timer);
  }, [job, loadBuilds, onChanged]);

  async function download(release: ProtonRelease) {
    setBusyTag(release.tag);
    try {
      setJob(await api.startProtonDownload(release.tag, release.url));
    } catch (caught) {
      setBusyTag(null);
      toast.danger(t("Could not start the download", "无法开始下载"), {
        description: String((caught as Error).message),
      });
    }
  }

  async function remove(build: ProtonBuild) {
    try {
      await api.removeProtonBuild(build.path);
      toast.success(t(`${build.name} removed`, `已移除 ${build.name}`));
      await loadBuilds();
      onChanged();
    } catch (caught) {
      toast.danger(t("Could not remove the build", "无法移除该版本"), {
        description: String((caught as Error).message),
      });
    }
  }

  async function cancelJob(jobId: string) {
    try {
      await api.cancelProtonDownload(jobId);
      toast.success(t("Download cancelled", "已取消下载"));
      setBusyTag(null);
    } catch (caught) {
      toast.danger(t("Could not cancel the download", "无法取消下载"), {
        description: String((caught as Error).message),
      });
    }
  }

  async function saveToken() {
    try {
      await api.updateSettings({github_token: token});
      toast.success(t("Token saved", "Token 已保存"));
      await loadReleases();
    } catch (caught) {
      toast.danger(t("Could not save the token", "无法保存 Token"), {
        description: String((caught as Error).message),
      });
    }
  }

  const percent = job && job.total > 0 ? Math.min(100, Math.round((job.downloaded / job.total) * 100)) : 0;
  const installedTags = new Set(
    [...builds.map((build) => build.version), ...builds.map((build) => build.name)].map((value) =>
      value.toLowerCase(),
    ),
  );
  const newestRelease = (releases ?? []).find((release) => !release.prerelease);
  const updateAvailable =
    newestRelease && !installedTags.has(newestRelease.tag.toLowerCase()) ? newestRelease : null;

  return (
    <Modal.Backdrop isOpen={open} onOpenChange={(value) => !value && onClose()}>
      <Modal.Container size="lg">
        <Modal.Dialog className="max-h-[88vh]">
          <Modal.CloseTrigger />
          <Modal.Header>
            <Modal.Icon className="bg-default text-foreground">
              <CpuIcon className="size-5" />
            </Modal.Icon>
            <Modal.Heading>{t("Proton manager", "Proton 管理器")}</Modal.Heading>
          </Modal.Header>
          <Modal.Body className="overflow-y-auto">
            <Tabs className="w-full" defaultSelectedKey="installed">
              <Tabs.ListContainer>
                <Tabs.List aria-label={t("Proton manager", "Proton 管理器")}>
                  <Tabs.Tab id="installed">
                    {t("Installed", "已安装")} ({builds.length})
                    <Tabs.Indicator />
                  </Tabs.Tab>
                  <Tabs.Tab id="releases">
                    {t("Downloads", "下载")}
                    <Tabs.Indicator />
                  </Tabs.Tab>
                  <Tabs.Tab id="sources">
                    {t("Sources", "来源")}
                    <Tabs.Indicator />
                  </Tabs.Tab>
                </Tabs.List>
              </Tabs.ListContainer>

              <Tabs.Panel className="flex flex-col gap-2 pt-4" id="installed">
                {builds.length === 0 && (
                  <p className="rounded-xl bg-surface/50 px-4 py-6 text-center text-sm text-muted">
                    {t(
                      "No Proton build found. Download one or add a folder in Settings.",
                      "未找到 Proton，请下载一个或在设置中添加目录。",
                    )}
                  </p>
                )}
                {builds.map((build) => (
                  <div
                    key={build.path}
                    className="flex items-center gap-3 rounded-xl border border-border/50 bg-surface/40 px-3 py-2"
                  >
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-sm">{build.name}</span>
                      <span className="truncate text-[11px] text-muted">{build.path}</span>
                      {build.size ? (
                        <span className="text-[10px] text-muted">{formatSize(build.size)}</span>
                      ) : null}
                    </div>
                    <Chip size="sm" variant="soft" className="shrink-0 text-[10px]">
                      {sourceLabel(build.source, t)}
                    </Chip>
                    {build.removable && (
                      <Button
                        isIconOnly
                        size="sm"
                        variant="secondary"
                        aria-label={t(`Remove ${build.name}`, `移除 ${build.name}`)}
                        onPress={() => void remove(build)}
                      >
                        <TrashIcon className="size-3.5" />
                      </Button>
                    )}
                  </div>
                ))}
              </Tabs.Panel>

              <Tabs.Panel className="flex flex-col gap-3 pt-4" id="releases">
                {job && (
                  <div className="flex flex-col gap-1 rounded-xl border border-border/50 bg-surface/40 p-3">
                    <div className="flex items-center justify-between text-sm">
                      <span>{job.tag}</span>
                      <span className="text-xs text-muted">
                        {job.status === "extracting"
                          ? t("Extracting…", "正在解压…")
                          : job.total
                            ? t(
                                `${percent}% of ${formatSize(job.total)}`,
                                `已完成 ${percent}%，共 ${formatSize(job.total)}`,
                              )
                            : job.status}
                      </span>
                      {job.status === "downloading" && job.rate > 0 && (
                        <span className="text-[11px] text-muted">
                          {formatSize(job.rate)}/s
                          {job.eta !== null ? ` · ${t(`${job.eta}s left`, `剩余 ${job.eta} 秒`)}` : ""}
                        </span>
                      )}
                      {(job.status === "downloading" || job.status === "queued") && (
                        <Button
                          size="sm"
                          variant="tertiary"
                          onPress={() => void cancelJob(job.id)}
                        >
                          {t("Cancel", "取消")}
                        </Button>
                      )}
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-surface-secondary">
                      <div
                        className={`h-full rounded-full transition-all ${
                          job.status === "failed" ? "bg-danger" : "bg-accent"
                        }`}
                        style={{width: `${job.status === "extracting" ? 100 : percent}%`}}
                      />
                    </div>
                    {job.error && <span className="text-xs text-danger">{job.error}</span>}
                  </div>
                )}

                {error && (
                  <div className="flex items-start gap-2 rounded-xl border border-warning/40 bg-warning-soft/40 p-3 text-xs text-warning-soft-foreground">
                    <AlertIcon className="mt-0.5 size-4 shrink-0" />
                    <div className="flex flex-1 flex-col gap-2">
                      <span>{error}</span>
                      <div className="flex gap-2">
                        <Input
                          aria-label={t("GitHub API token", "GitHub API Token")}
                          className="flex-1"
                          placeholder={t("GitHub token", "GitHub Token")}
                          type="password"
                          value={token}
                          onChange={(event) => setToken(event.target.value)}
                        />
                        <Button size="sm" variant="secondary" onPress={() => void saveToken()}>
                          {t("Save", "保存")}
                        </Button>
                      </div>
                    </div>
                  </div>
                )}

                {updateAvailable && (
                  <div className="flex items-center justify-between gap-3 rounded-xl border border-accent/40 bg-accent/10 px-3 py-2">
                    <span className="text-xs">
                      {t(
                        `A newer build is available: ${updateAvailable.tag}`,
                        `发现更新的版本：${updateAvailable.tag}`,
                      )}
                    </span>
                    <Button
                      size="sm"
                      variant="secondary"
                      isDisabled={busyTag !== null}
                      onPress={() => void download(updateAvailable)}
                    >
                      {t("Get it", "获取")}
                    </Button>
                  </div>
                )}

                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted">
                    {t(
                      "GE-Proton releases from GitHub. Downloads go to the launcher data folder.",
                      "来自 GitHub 的 GE-Proton 版本，下载会保存到启动器数据目录。",
                    )}
                  </span>
                  <Button size="sm" variant="secondary" onPress={() => void loadReleases()}>
                    <RefreshIcon className="size-3.5" />
                    {t("Refresh", "刷新")}
                  </Button>
                </div>

                {loading ? (
                  <div className="flex items-center gap-2 py-10 text-sm text-muted">
                    <Spinner size="sm" />
                    {t("Loading releases…", "正在加载版本…")}
                  </div>
                ) : (
                  <ScrollShadow className="h-[42vh] rounded-2xl border border-border/60 bg-surface/40 p-1">
                    <div className="flex flex-col">
                      {(releases ?? []).map((release) => (
                        <div
                          key={release.tag}
                          className="flex items-center gap-3 rounded-xl px-3 py-2 hover:bg-surface-secondary"
                        >
                          <div className="flex min-w-0 flex-1 flex-col">
                            <span className="truncate text-sm">{release.name}</span>
                            <span className="truncate text-[11px] text-muted">
                              {formatDate(release.published_at, lang)} · {formatSize(release.size)}
                            </span>
                          </div>
                          <Button
                            size="sm"
                            variant="secondary"
                            isDisabled={busyTag !== null}
                            onPress={() => void download(release)}
                          >
                            {busyTag === release.tag ? t("Starting…", "正在开始…") : t("Download", "下载")}
                          </Button>
                        </div>
                      ))}
                      {releases !== null && releases.length === 0 && !error && (
                        <p className="p-6 text-center text-sm text-muted">
                          {t("No releases found.", "未找到任何版本。")}
                        </p>
                      )}
                    </div>
                  </ScrollShadow>
                )}
              </Tabs.Panel>

              <Tabs.Panel className="flex flex-col gap-2 pt-4" id="sources">
                <p className="text-xs text-muted">
                  {t(
                    "Proton builds are discovered in these folders, in order.",
                    "启动器会按顺序在这些目录中查找 Proton。",
                  )}
                </p>
                {sources.map((source) => (
                  <div
                    key={`${source.source}:${source.path}`}
                    className="flex items-center gap-3 rounded-xl border border-border/50 bg-surface/40 px-3 py-2"
                  >
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate font-mono text-[11px]">{source.path}</span>
                      <span className="text-[10px] text-muted">
                        {sourceLabel(source.source, t)}
                      </span>
                    </span>
                    <Chip size="sm" variant="soft" className="text-[10px]">
                      {source.exists ? t("found", "存在") : t("missing", "缺失")}
                    </Chip>
                  </div>
                ))}
              </Tabs.Panel>
            </Tabs>
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
