export default function DashboardLoading() {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#f0ece4]">
      <div className="flex flex-col items-center gap-4">
        <div
          className="h-10 w-10 rounded-full border-[3px] border-[#e8e3db] border-t-[#1c1917]"
          style={{ animation: "spin 0.75s linear infinite" }}
        />
        <span className="text-xs font-medium tracking-widest text-[#78716c] uppercase">
          Aira
        </span>
      </div>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
