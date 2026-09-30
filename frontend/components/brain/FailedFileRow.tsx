"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { announceApprovalsChanged } from "./approvalsEvent";
import { ROW_BUTTON_CLASS, ROW_LINK_CLASS, WaitingRow } from "./WaitingRow";
import type { FailedFile } from "./types";

const NEEDS_MANAGE = "Needs manage access";

interface FailedFileRowProps {
  file: FailedFile;
  canManage: boolean;
}

export function FailedFileRow({ file, canManage }: FailedFileRowProps) {
  const [isBusy, setIsBusy] = useState(false);
  const reasonId = useId();

  async function resort(): Promise<void> {
    setIsBusy(true);
    try {
      await api.knowledge.resort(file.id);
      toast.success("Sorting this file again. It'll be ready to review in a minute.");
      announceApprovalsChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't start the re-sort. Please try again.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <WaitingRow title={file.name} meta="Aira couldn't sort this file">
      <button
        type="button"
        className={ROW_BUTTON_CLASS}
        disabled={!canManage || isBusy}
        aria-describedby={canManage ? undefined : reasonId}
        onClick={resort}
      >
        {isBusy && <Loader2 size={12} className="mr-1.5 animate-spin" aria-hidden />}
        Re-sort
      </button>
      <Link href="/dashboard/knowledge" className={ROW_LINK_CLASS}>
        Open Knowledge
      </Link>
      {!canManage && (
        <p id={reasonId} className="basis-full font-body text-[11px] text-ink-secondary">
          {NEEDS_MANAGE}
        </p>
      )}
    </WaitingRow>
  );
}
