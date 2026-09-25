import { DealStage } from "@/lib/api";

const STAGE_LABEL: Record<DealStage, string> = {
  quoted: "Quoted",
  awaiting_payment: "Awaiting payment",
  won: "Won",
  lost: "Lost",
};

const STAGE_STYLE: Record<DealStage, string> = {
  quoted: "bg-slate-50 text-slate-600 border-slate-200",
  awaiting_payment: "bg-amber-50 text-amber-700 border-amber-200",
  won: "bg-emerald-50 text-emerald-700 border-emerald-200",
  lost: "bg-rose-50 text-rose-700 border-rose-200",
};

export function StageBadge({ stage, className = "" }: { stage: DealStage; className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 font-label text-[10px] font-bold whitespace-nowrap ${STAGE_STYLE[stage]} ${className}`}
    >
      {STAGE_LABEL[stage]}
    </span>
  );
}
