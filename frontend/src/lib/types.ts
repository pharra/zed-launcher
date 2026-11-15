export interface Game {
  id: string;
  title: string;
  path: string;
  prefix_path: string;
  proton_path: string;
  args: string;
  launch_args: string;
  env: string;
  extra_programs: ExtraProgram[];
  mount_dirs: string[];
  working_dir: string;
  pre_launch: string;
  post_launch: string;
  cover: string;
  icon: string;
  mangohud: boolean;
  gamemode: boolean;
  gamescope: boolean;
  gamescope_args: string;
  kwin: boolean;
  kwin_args: string;
  mangohud_args: string;
  no_sleep: boolean;
  sdl: boolean;
  wayland: boolean;
  wow64: boolean;
  owned_prefix: boolean;
  shortcut: boolean;
  playtime: number;
  last_played: string | null;
  created_at: string;
  updated_at: string;
}

export type GameInput = Partial<
  Omit<Game, "id" | "playtime" | "last_played" | "created_at" | "updated_at">
> & {
  mode?: "create" | "add";
  prefix_name?: string;
  install_id?: string;
};

export type GameMode = "create" | "add" | "edit";

export interface ProtonBuild {
  name: string;
  path: string;
  version: string;
  source: string;
  removable: boolean;
  size?: number;
}

export interface ProtonSource {
  path: string;
  source: string;
  exists: boolean;
}

export interface ProtonRelease {
  tag: string;
  name: string;
  published_at: string | null;
  prerelease: boolean;
  size: number;
  url: string;
}

export interface ProtonJob {
  id: string;
  tag: string;
  status: "queued" | "downloading" | "extracting" | "done" | "failed";
  downloaded: number;
  total: number;
  rate: number;
  eta: number | null;
  path: string;
  error: string;
}

export interface Tools {
  umu_run: string | null;
  mangohud: string | null;
  gamemoderun: string | null;
  gamescope: string | null;
  kwin: string | null;
  systemd_inhibit: string | null;
  notify_send: string | null;
  icoextract: string | null;
}

export interface BackupEntry {
  path: string;
  name: string;
  size: number;
  created_at: string | null;
  games: number | null;
  restorable: boolean;
}

export interface BackupResult extends BackupEntry {
  artwork_files: number;
  prefixes: string[];
}

export interface Settings {
  prefix_root: string;
  backup_dir: string;
  backup_schedule: string;
  language: string;
  proton_paths: string[];
  proton_default: string;
  github_token: string;
  steamgriddb_api_key: string;
  notifications: boolean;
  tray: boolean;
  umu_run: string;
  tool_paths: Record<string, string>;
  confirm_kill: boolean;
  proton_log: boolean;
}

export interface Dependency {
  available: boolean;
  path: string | null;
  hint: string;
  warning?: string;
}

export interface RequiredDependency extends Dependency {
  count?: number;
}

export interface OptionalDependency extends Dependency {
  label: string;
  configured: string;
}

export interface Dependencies {
  required: {
    umu_run: RequiredDependency;
    proton: RequiredDependency;
  };
  optional: Record<string, OptionalDependency>;
  missing_required: string[];
  ready: boolean;
}

export interface Info {
  config: Settings;
  tools: Tools;
  dependencies: Dependencies;
  autostart: boolean;
  tray_host: boolean;
  proton_effective: string | null;
  protons: ProtonBuild[];
  proton_sources: ProtonSource[];
  gpus: Array<{card: string; vendor: string; device: string}>;
  paths: {
    config: string;
    data: string;
    state: string;
    logs: string;
    protons: string;
    web: string;
  };
}

export interface ShortcutCandidate {
  name: string;
  path: string;
  shortcut?: string;
  on_desktop?: boolean;
  in_menu?: boolean;
}

export interface DetectionResult {
  best: string | null;
  candidates: ShortcutCandidate[];
  fallback: ShortcutCandidate[];
  prefix_path: string;
}

export interface InstallerRun {
  install_id: string;
  run_id: string;
  prefix_path: string;
  owned_prefix: boolean;
  proton_path: string;
  snapshot: RunSnapshot;
}

export type PrefixToolKind = "winecfg" | "regedit" | "winetricks" | "exe";

export interface BrowseEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  executable: boolean;
  wine_prefix: boolean;
}

export interface BrowseResult {
  path: string;
  parent: string | null;
  entries: BrowseEntry[];
}

export interface RunSnapshot {
  run_id: string;
  game_id: string;
  title: string;
  status: string;
  argv: string[];
  pid?: number | null;
  started_at?: string | null;
  log_path?: string;
  lines?: string[];
  detached?: boolean;
}

export interface RunRecord {
  id: string;
  game_id: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  duration: number | null;
  exit_code: number | null;
  log_path: string;
}

export interface ExtraProgram {
  kind: "game" | "program";
  path: string;
  args: string;
  delay: number;
}

