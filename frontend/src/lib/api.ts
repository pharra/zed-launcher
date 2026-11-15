import type {
  BackupEntry,
  BackupResult,
  BrowseResult,
  DetectionResult,
  InstallerRun,
  Game,
  GameInput,
  Info,
  ProtonBuild,
  ProtonJob,
  PrefixToolKind,
  ProtonRelease,
  RunRecord,
  RunSnapshot,
  Settings,
} from "./types";

const params = new URLSearchParams(window.location.search);
const urlToken = params.get("token");
const token = urlToken ?? localStorage.getItem("zed.token") ?? import.meta.env.VITE_ZED_TOKEN ?? "";

if (urlToken) {
  localStorage.setItem("zed.token", urlToken);
  params.delete("token");
  const query = params.toString();
  window.history.replaceState({}, "", window.location.pathname + (query ? `?${query}` : ""));
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Zed-Token", token);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {...init, headers});
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = (await response.json()) as {detail?: string};
      detail = data.detail ?? detail;
    } catch {
      // Keep the status text.
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function json(body: unknown): RequestInit {
  return {body: JSON.stringify(body)};
}

export const api = {
  listGames: (search?: string, sort = "title") => {
    const query = new URLSearchParams({sort});
    if (search) query.set("search", search);
    return request<Game[]>(`/api/v1/games?${query.toString()}`);
  },
  getGame: (id: string) => request<Game>(`/api/v1/games/${id}`),
  createGame: (game: GameInput) => request<Game>("/api/v1/games", {method: "POST", ...json(game)}),
  updateGame: (id: string, patch: GameInput) =>
    request<Game>(`/api/v1/games/${id}`, {method: "PATCH", ...json(patch)}),
  deleteGame: (id: string, removePrefix = false) =>
    request<void>(`/api/v1/games/${id}?remove_prefix=${removePrefix}`, {method: "DELETE"}),
  gameRuns: (id: string, limit = 20) => request<RunRecord[]>(`/api/v1/games/${id}/runs?limit=${limit}`),
  launchGame: (id: string, logs = true) =>
    request<RunSnapshot>(`/api/v1/games/${id}/launch?logs=${logs}`, {method: "POST"}),
  stopRun: (id: string) => request<{ok: boolean}>(`/api/v1/runs/${id}/stop`, {method: "POST"}),
  activeRuns: () => request<RunSnapshot[]>("/api/v1/runs"),
  getRun: (id: string) => request<RunSnapshot>(`/api/v1/runs/${id}`),
  recentRuns: (limit = 20) => request<RunRecord[]>(`/api/v1/runs/recent?limit=${limit}`),
  setArtwork: (id: string, path: string) =>
    request<Game>(`/api/v1/games/${id}/artwork`, {method: "POST", ...json({path})}),
  deleteArtwork: (id: string) => request<void>(`/api/v1/games/${id}/artwork`, {method: "DELETE"}),
  sgdbSearch: (term: string) =>
    request<Array<{id: string; name: string}>>(`/api/v1/sgdb/search?term=${encodeURIComponent(term)}`),
  sgdbGrids: (id: string) =>
    request<Array<{id: string; url: string; thumb: string; width: number | null; height: number | null}>>(
      `/api/v1/sgdb/grids/${encodeURIComponent(id)}`,
    ),
  setSgdbArtwork: (id: string, url: string) =>
    request<Game>(`/api/v1/games/${id}/artwork/sgdb`, {method: "POST", ...json({url})}),
  extractIcon: (id: string) => request<Game>(`/api/v1/games/${id}/icon`, {method: "POST"}),
  deleteIcon: (id: string) => request<void>(`/api/v1/games/${id}/icon`, {method: "DELETE"}),
  createShortcut: (id: string, target: "applications" | "desktop") =>
    request<{path: string}>(`/api/v1/games/${id}/shortcut?target=${target}`, {method: "POST"}),
  deleteShortcut: (id: string, target: "applications" | "desktop") =>
    request<void>(`/api/v1/games/${id}/shortcut?target=${target}`, {method: "DELETE"}),
  info: () => request<Info>("/api/v1/info"),
  autostart: () => request<{enabled: boolean; path: string}>("/api/v1/autostart"),
  setAutostart: (enabled: boolean) =>
    request<{enabled: boolean; path: string}>(`/api/v1/autostart?enabled=${enabled}`, {
      method: "POST",
    }),
  diagnostics: () => request<Record<string, unknown>>("/api/v1/diagnostics"),
  settings: () => request<Settings>("/api/v1/settings"),
  updateSettings: (patch: Partial<Settings>) =>
    request<Settings>("/api/v1/settings", {method: "PUT", ...json(patch)}),
  protons: () =>
    request<{
      builds: ProtonBuild[];
      sources: Array<{path: string; source: string; exists: boolean}>;
      default: string;
      download_dir: string;
      has_token: boolean;
    }>("/api/v1/protons"),
  releases: (limit = 30) => request<ProtonRelease[]>(`/api/v1/protons/releases?limit=${limit}`),
  startProtonDownload: (tag: string, url = "") =>
    request<ProtonJob>("/api/v1/protons/downloads", {method: "POST", ...json({tag, url})}),
  cancelProtonDownload: (id: string) =>
    request<{ok: boolean}>(`/api/v1/protons/downloads/${id}`, {method: "DELETE"}),
  protonJob: (id: string) => request<ProtonJob>(`/api/v1/protons/downloads/${id}`),
  addProtonPath: (path: string) =>
    request<{paths: string[]; builds: ProtonBuild[]}>("/api/v1/protons/paths", {
      method: "POST",
      ...json({path}),
    }),
  removeProtonPath: (path: string) =>
    request<{paths: string[]; builds: ProtonBuild[]}>(
      `/api/v1/protons/paths?path=${encodeURIComponent(path)}`,
      {method: "DELETE"},
    ),
  removeProtonBuild: (path: string) =>
    request<{ok: boolean}>("/api/v1/protons/remove", {method: "POST", ...json({path})}),
  startInstaller: (payload: {
    installer: string;
    title?: string;
    prefix_name?: string;
    prefix_path?: string;
    proton_path?: string;
    args?: string;
  }) => request<InstallerRun>("/api/v1/installers/run", {method: "POST", ...json(payload)}),
  detectInstall: (installId: string) =>
    request<DetectionResult>(`/api/v1/installers/${installId}/detect`),
  deleteInstall: (installId: string, removePrefix = false) =>
    request<void>(`/api/v1/installers/${installId}?remove_prefix=${removePrefix}`, {
      method: "DELETE",
    }),
  prefixPresets: () =>
    request<Array<{id: string; verbs: string; label: string; chinese: string}>>(
      "/api/v1/prefixes/presets",
    ),
  cleanupTemp: (path: string) =>
    request<{freed: number; size: number}>(`/api/v1/prefixes/cleanup-temp`, {
      method: "POST",
      ...json({path}),
    }),
  clonePrefix: (path: string, name: string) =>
    request<{path: string; size: number}>(`/api/v1/prefixes/clone`, {
      method: "POST",
      ...json({path, name}),
    }),
  prefixProcesses: (path: string) =>
    request<{prefix_path: string; processes: Array<{pid: number; command: string}>; count: number}>(
      `/api/v1/prefixes/processes?path=${encodeURIComponent(path)}`,
    ),
  cleanupPrefix: (path: string) =>
    request<{killed: number; remaining: number}>(`/api/v1/prefixes/cleanup`, {
      method: "POST",
      ...json({path}),
    }),
  scanPrefix: (path: string) =>
    request<DetectionResult & {size: number}>("/api/v1/prefixes/scan", {
      method: "POST",
      ...json({path}),
    }),
  listBackups: (destination?: string) => {
    const query = destination ? `?destination=${encodeURIComponent(destination)}` : "";
    return request<{destination: string; backups: BackupEntry[]}>(`/api/v1/backups${query}`);
  },
  createBackup: (destination: string, includeArtwork = true, includeSaves = false) =>
    request<BackupResult>("/api/v1/backups", {
      method: "POST",
      ...json({destination, include_artwork: includeArtwork, include_saves: includeSaves}),
    }),
  savegameEstimate: () =>
    request<{bytes: number; directories: string[]; count: number}>("/api/v1/backups/saves"),
  restoreBackup: (path: string) =>
    request<{restored: string; games: number; artwork_files: number; save_files?: number}>(
      "/api/v1/backups/restore",
      {method: "POST", ...json({path})},
    ),
  deleteBackup: (path: string) =>
    request<{ok: boolean}>(`/api/v1/backups?path=${encodeURIComponent(path)}`, {method: "DELETE"}),
  runPrefixTool: (payload: {
    prefix_path: string;
    kind: PrefixToolKind;
    proton_path?: string;
    target?: string;
    args?: string;
    env?: string;
  }) =>
    request<{run_id: string; snapshot: RunSnapshot; prefix_path: string}>(
      "/api/v1/prefixes/run",
      {method: "POST", ...json(payload)},
    ),
  browse: (path?: string, showHidden = false) => {
    const query = new URLSearchParams();
    if (path) query.set("path", path);
    if (showHidden) query.set("show_hidden", "true");
    return request<BrowseResult>(`/api/v1/browse?${query.toString()}`);
  },
  openPath: (path: string) => request<{ok: boolean}>("/api/v1/open", {method: "POST", ...json({path})}),
};

export function runEventsUrl(runId: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/v1/runs/${runId}/events?token=${encodeURIComponent(token)}`;
}

export function artworkUrl(cover: string): string {
  return /^https?:\/\//.test(cover) ? cover : `/artwork/${cover}`;
}

export function formatPlaytime(seconds: number, zh = false): string {
  if (!seconds) return zh ? "未游玩" : "Not played";
  if (seconds < 60) return "<1m";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function formatSize(bytes: number): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatDate(value: string | null, locale?: string): string {
  if (!value) return locale === "zh" ? "从未" : "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return locale === "zh" ? "从未" : "Never";
  return date.toLocaleDateString(locale, {month: "short", day: "numeric", year: "numeric"});
}
