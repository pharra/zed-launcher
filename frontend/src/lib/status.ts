export type StatusLabels = Record<string, [string, string]>;

const labels: StatusLabels = {
  starting: ["starting", "启动中"],
  running: ["running", "运行中"],
  stopping: ["stopping", "正在停止"],
  stopped: ["stopped", "已停止"],
  closed: ["closed", "已退出"],
  failed: ["failed", "失败"],
  unknown: ["unknown", "未知"],
};

export function statusLabel(status: string, t: (en: string, zh: string) => string): string {
  const pair = labels[status];
  return pair ? t(pair[0], pair[1]) : status;
}

const sources: Record<string, [string, string]> = {
  download: ["Downloaded", "已下载"],
  steam: ["Steam", "Steam"],
  flatpak: ["Steam Flatpak", "Steam Flatpak"],
  system: ["System", "系统"],
  manual: ["Manual", "手动"],
};

export function sourceLabel(source: string, t: (en: string, zh: string) => string): string {
  const pair = sources[source];
  return pair ? t(pair[0], pair[1]) : source;
}
