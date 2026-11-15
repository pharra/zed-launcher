import {useState} from "react";
import {Button, Input} from "@heroui/react";

import {useT} from "../lib/i18n";
import {FolderIcon, PlusIcon, TrashIcon} from "./icons";
import {PathBrowser} from "./PathBrowser";

interface MountDirsProps {
  dirs: string[];
  onChange: (dirs: string[]) => void;
}

export function MountDirs({dirs, onChange}: MountDirsProps) {
  const {t} = useT();
  const [browse, setBrowse] = useState<number | null>(null);

  function replace(index: number, value: string) {
    onChange(dirs.map((entry, position) => (position === index ? value : entry)));
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-col gap-1">
        <span className="text-sm font-medium">{t("Extra container folders", "容器额外目录")}</span>
        <p className="text-xs leading-snug text-muted">
          {t(
            "The Wine prefix, the folders of the game and of every program on the list above are already visible inside the container. Anything stored elsewhere (another disk such as /game, a mounted drive, a folder outside the prefix) only exists inside it when it is listed here: these folders are bind-mounted read-write into the pressure-vessel container through PRESSURE_VESSEL_FILESYSTEMS_RW. Without an entry the file is simply not there and wine fails without a message.",
            "Wine prefix、游戏所在目录以及上面列表中每个程序所在目录，容器里本来就能看到。存放在别处的程序或数据（另一块磁盘上的 /game、挂载盘、prefix 之外的目录）只有写在这里才存在于容器中：这些目录会以可读写方式通过 PRESSURE_VESSEL_FILESYSTEMS_RW 绑定进 pressure-vessel 容器。没有列出的目录在容器里根本不存在，wine 会静默失败、看不到任何报错。",
          )}
        </p>
        <span className="font-mono text-[11px] text-muted">
          {t(
            "Folders must exist and stay mounted; a missing folder is skipped with a note in the log.",
            "目录必须存在且保持挂载；启动时目录不存在会被跳过，并在日志里提示。",
          )}
        </span>
      </div>

      {dirs.map((dir, index) => (
        <div key={index} className="flex min-w-0 items-center gap-2">
          <Input
            aria-label={t("Container folder", "容器目录")}
            className="min-w-0 flex-1"
            placeholder="/game"
            value={dir}
            onChange={(event) => replace(index, event.target.value)}
          />
          <Button
            isIconOnly
            variant="secondary"
            aria-label={t("Browse for folder", "浏览目录")}
            onPress={() => setBrowse(index)}
          >
            <FolderIcon className="size-4" />
          </Button>
          <Button
            isIconOnly
            variant="ghost"
            aria-label={t("Remove folder", "移除目录")}
            onPress={() => onChange(dirs.filter((_, position) => position !== index))}
          >
            <TrashIcon className="size-4" />
          </Button>
        </div>
      ))}

      <Button className="self-start" variant="secondary" onPress={() => onChange([...dirs, ""])}>
        <PlusIcon className="size-4" />
        {t("Add folder", "添加目录")}
      </Button>

      <PathBrowser
        open={browse !== null}
        mode="directory"
        initialPath={browse === null ? undefined : dirs[browse]}
        onClose={() => setBrowse(null)}
        onSelect={(path) => {
          if (browse !== null) replace(browse, path);
          setBrowse(null);
        }}
      />
    </div>
  );
}
