import {useEffect, useRef, useState} from "react";
import {Button, Chip, Modal, ScrollShadow, toast} from "@heroui/react";

import {api, runEventsUrl} from "../lib/api";
import {useT} from "../lib/i18n";
import {statusLabel} from "../lib/status";
import type {RunSnapshot} from "../lib/types";
import {TerminalIcon} from "./icons";

interface RunDrawerProps {
  run: RunSnapshot | null;
  confirmKill: boolean;
  onClose: () => void;
  onExited?: () => void;
}

const statusColor = (status: string): "success" | "warning" | "danger" | "default" => {
  if (status === "running" || status === "starting") return "success";
  if (status === "stopping" || status === "stopped") return "warning";
  if (status === "failed") return "danger";
  return "default";
};

export function RunDrawer({run, confirmKill, onClose, onExited}: RunDrawerProps) {
  const {lang, t} = useT();
  const [lines, setLines] = useState<string[]>([]);
  const [status, setStatus] = useState("starting");
  const [stopping, setStopping] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [hints, setHints] = useState<Array<{key: string; message: string; chinese: string}>>([]);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!run) return;
    setLines(run.lines ?? []);
    setStatus(run.status);
    setStopping(false);
    setHints([]);

    if (run.detached) {
      // The game was started before this window opened; tail its log file instead.
      const timer = setInterval(async () => {
        try {
          const next = await api.getRun(run.run_id);
          setLines(next.lines ?? []);
          setStatus(next.status);
          if (!next.detached) onExited?.();
        } catch {
          clearInterval(timer);
        }
      }, 2000);
      return () => clearInterval(timer);
    }

    const socket = new WebSocket(runEventsUrl(run.run_id));
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data) as {
        type: string;
        line?: string;
        status?: string;
        lines?: string[];
        hints?: Array<{key: string; message: string; chinese: string}>;
      };
      if (data.type === "snapshot") {
        setLines(data.lines ?? []);
        if (data.status) setStatus(data.status);
      } else if (data.type === "log" && data.line !== undefined) {
        setLines((current) => [...current.slice(-1999), data.line as string]);
      } else if (data.type === "status" && data.status) {
        setStatus(data.status);
      } else if (data.type === "exit") {
        if (data.status) setStatus(data.status);
        if (data.hints?.length) setHints(data.hints);
        onExited?.();
      }
    };
    return () => socket.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.run_id]);

  useEffect(() => {
    endRef.current?.scrollIntoView({block: "end"});
  }, [lines]);

  async function stop() {
    if (!run) return;
    setStopping(true);
    try {
      await api.stopRun(run.run_id);
      toast.success(t("Stopping the game", "正在停止游戏"));
    } catch (error) {
      toast.danger(t("Could not stop the game", "无法停止游戏"), {
        description: String((error as Error).message),
      });
    } finally {
      setStopping(false);
    }
  }

  return (
    <Modal.Backdrop isOpen={run !== null} onOpenChange={(value) => !value && onClose()}>
      <Modal.Container size="lg">
        <Modal.Dialog className="max-h-[86vh]">
          <Modal.CloseTrigger />
          <Modal.Header>
            <Modal.Icon className="bg-default text-foreground">
              <TerminalIcon className="size-5" />
            </Modal.Icon>
            <Modal.Heading>{run?.title || t("Game output", "游戏输出")}</Modal.Heading>
            <Chip size="sm" color={statusColor(status)} variant="soft">
              {statusLabel(status, t)}
            </Chip>
            {run?.detached && (
              <Chip size="sm" variant="soft" className="text-[10px]">
                {t("from log file", "来自日志")}
              </Chip>
            )}
          </Modal.Header>
          <Modal.Body className="gap-3">
            {run?.argv && (
              <pre className="overflow-x-auto rounded-xl border border-border/50 bg-surface-secondary/60 p-3 text-[11px] leading-5 text-muted">
                {run.argv.join(" ")}
              </pre>
            )}
            <ScrollShadow className="h-[42vh] rounded-xl border border-border/50 bg-black/60 p-3 font-mono text-[11px] leading-5">
              {lines.length === 0 ? (
                <p className="text-muted">{t("Waiting for output…", "等待输出…")}</p>
              ) : (
                lines.map((line, index) => (
                  <div key={`${index}-${line.slice(0, 16)}`} className="whitespace-pre-wrap break-all">
                    {line}
                  </div>
                ))
              )}
              <div ref={endRef} />
            </ScrollShadow>
            {hints.length > 0 && (
              <div className="flex flex-col gap-1 rounded-xl border border-warning/40 bg-warning-soft/30 p-3">
                <span className="text-sm font-medium text-warning-soft-foreground">
                  {t("What probably went wrong", "可能的原因")}
                </span>
                {hints.map((hint) => (
                  <span key={hint.key} className="text-xs text-warning-soft-foreground">
                    {lang === "zh" ? hint.chinese : hint.message}
                  </span>
                ))}
              </div>
            )}
            <p className="text-xs text-muted">
              {t(
                "Closing this window does not stop the game. Use the stop button to terminate it.",
                "关闭此窗口不会结束游戏；请使用停止按钮结束进程。",
              )}
            </p>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" slot="close">
              {t("Close", "关闭")}
            </Button>
            <Button
              variant="danger-soft"
              isDisabled={stopping || !(status === "running" || status === "starting")}
              onPress={() => (confirmKill ? setConfirmOpen(true) : void stop())}
            >
              {stopping ? t("Stopping…", "正在停止…") : t("Stop game", "停止游戏")}
            </Button>
          </Modal.Footer>
        </Modal.Dialog>
      </Modal.Container>

      <Modal.Backdrop isOpen={confirmOpen} onOpenChange={setConfirmOpen}>
        <Modal.Container size="sm">
          <Modal.Dialog>
            <Modal.Header>
              <Modal.Heading>{t(`Stop ${run?.title}?`, `停止 ${run?.title}？`)}</Modal.Heading>
            </Modal.Header>
            <Modal.Body>
              <p className="text-sm text-muted">
                {t(
                  "The game process and everything it started will be terminated. Unsaved progress may be lost.",
                  "游戏进程及其启动的所有进程都会被结束，未保存的进度可能丢失。",
                )}
              </p>
            </Modal.Body>
            <Modal.Footer>
              <Button variant="secondary" slot="close">
                {t("Keep playing", "继续游戏")}
              </Button>
              <Button
                variant="danger-soft"
                onPress={() => {
                  setConfirmOpen(false);
                  void stop();
                }}
              >
                {t("Stop game", "停止游戏")}
              </Button>
            </Modal.Footer>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </Modal.Backdrop>
  );
}
