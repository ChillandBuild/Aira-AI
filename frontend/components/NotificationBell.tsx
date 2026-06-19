"use client";
import { useState } from "react";
import { Bell, X, Clock, AlertCircle, Info, CheckCircle2, CheckSquare } from "lucide-react";
import { useNotifications } from "@/hooks/useNotifications";
import { useRouter } from "next/navigation";

export function NotificationBell() {
  const router = useRouter();
  const { notifications, callbacks, markRead, markAllRead } = useNotifications();
  const [isOpen, setIsOpen] = useState(false);

  const handleMarkRead = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    markRead(id);
  };

  const handleMarkAllRead = async () => {
    await markAllRead();
  };

  const handleCallbackClick = () => {
    setIsOpen(false);
    router.push("/dashboard/telecalling");
  };

  const totalUnread = notifications.length + callbacks.length;

  const getAlertStyle = (type: string) => {
    switch (type) {
      case "system_error":
      case "missed_callback":
      case "sentiment_critical":
        return {
          bg: "bg-[#faf8f5]/65 hover:bg-[#f0ece4]/65 border-[#e8e3db]/50 border-l-4 border-l-rose-500 dark:bg-[#292524]/30 dark:hover:bg-[#292524]/60 dark:border-[#292524] dark:border-l-rose-500",
          iconBg: "bg-rose-100 text-rose-600 dark:bg-rose-950/60 dark:text-rose-400",
          icon: <AlertCircle size={14} />,
        };
      case "handover_new":
      case "callback_claimable":
      case "break_overtime":
        return {
          bg: "bg-[#faf8f5]/65 hover:bg-[#f0ece4]/65 border-[#e8e3db]/50 border-l-4 border-l-amber-500 dark:bg-[#292524]/30 dark:hover:bg-[#292524]/60 dark:border-[#292524] dark:border-l-amber-500",
          iconBg: "bg-amber-100 text-amber-600 dark:bg-amber-950/60 dark:text-amber-400",
          icon: <Clock size={14} />,
        };
      case "lead_assigned":
      case "lead_reassigned":
      case "callback_taken_over":
      default:
        return {
          bg: "bg-[#faf8f5]/65 hover:bg-[#f0ece4]/65 border-[#e8e3db]/50 border-l-4 border-l-indigo-500 dark:bg-[#292524]/30 dark:hover:bg-[#292524]/60 dark:border-[#292524] dark:border-l-indigo-500",
          iconBg: "bg-indigo-100 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-400",
          icon: <Info size={14} />,
        };
    }
  };

  return (
    <div className="relative">
      {/* Bell Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative flex items-center justify-center w-[34px] h-[34px] rounded-full transition-transform hover:scale-105 group"
        style={{ background: "linear-gradient(135deg, #2e1065, #5b21b6)" }}
        title="Notification Center"
      >
        <Bell size={16} className="text-white" />
        {totalUnread > 0 && (
          <span className="absolute -top-1.5 -right-1.5 min-w-[22px] h-[22px] px-1.5 bg-gradient-to-r from-rose-500 to-pink-600 text-white text-[10px] font-black rounded-full flex items-center justify-center ring-4 ring-[#faf8f5] shadow-sm animate-bounce-short">
            {totalUnread > 99 ? "99+" : totalUnread}
          </span>
        )}
      </button>

      {/* Dropdown Panel */}
      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 top-full mt-3 w-80 md:w-96 bg-white/95 dark:bg-[#1c1917]/95 backdrop-blur-xl border border-[#e8e3db]/60 dark:border-[#292524]/60 rounded-3xl shadow-2xl z-50 overflow-hidden flex flex-col max-h-[80vh] animate-in fade-in slide-in-from-top-4 duration-200">
            {/* Header */}
            <div className="px-5 py-4 bg-gradient-to-br from-indigo-50/65 to-purple-50/65 dark:from-[#1c1917] dark:to-[#1c1917] border-b border-[#f0ece4] dark:border-[#292524]/80 flex items-center justify-between">
              <h3 className="font-display text-sm font-black text-[#292524] dark:text-[#e8e3db] uppercase tracking-wider">
                Notification Center
              </h3>
              <div className="flex items-center gap-2">
                {notifications.length > 0 && (
                  <button
                    onClick={handleMarkAllRead}
                    className="p-1.5 text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-800 hover:bg-indigo-50/50 dark:hover:bg-indigo-950/35 rounded-xl transition-all flex items-center gap-1 font-bold"
                    title="Mark all as read"
                  >
                    <CheckSquare size={13} />
                    Mark all read
                  </button>
                )}
                <button
                  onClick={() => setIsOpen(false)}
                  className="p-1.5 text-[#a8a29e] hover:text-[#44403c] dark:hover:text-[#e8e3db] rounded-xl hover:bg-[#f0ece4]/50 dark:hover:bg-[#292524]/50 transition-colors"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            {/* Combined Content List */}
            <div className="overflow-y-auto flex-1 p-3.5 space-y-3">
              {totalUnread === 0 ? (
                <div className="py-16 text-center text-sm text-[#a8a29e] dark:text-[#78716c] font-body flex flex-col items-center gap-2">
                  <CheckCircle2 size={32} className="text-[#d6cfc9] dark:text-[#44403c]" />
                  All caught up!
                </div>
              ) : (
                <div className="space-y-3.5">
                  {/* Section 1: Due Callbacks */}
                  {callbacks.length > 0 && (
                    <div className="space-y-2">
                      <div className="px-1.5 text-[10px] font-black uppercase tracking-widest text-amber-600 dark:text-amber-400 flex items-center gap-1.5">
                        <Clock size={11} />
                        Due Callbacks ({callbacks.length})
                      </div>
                      <div className="space-y-2">
                        {callbacks.map((cb) => (
                          <div
                            key={cb.id}
                            onClick={handleCallbackClick}
                            className="p-3.5 bg-[#faf8f5]/65 hover:bg-[#f0ece4]/65 border border-[#e8e3db]/50 border-l-4 border-l-amber-500 dark:bg-[#292524]/30 dark:hover:bg-[#292524]/60 dark:border-[#292524] dark:border-l-amber-500 rounded-2xl transition-all flex gap-3 cursor-pointer group"
                          >
                            <div className="mt-0.5 shrink-0">
                              <div className="w-7 h-7 rounded-full bg-amber-100 dark:bg-amber-950/60 text-amber-600 dark:text-amber-400 flex items-center justify-center">
                                <Clock size={13} />
                              </div>
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="font-display text-xs font-black text-[#292524] dark:text-[#f0ece4] truncate">
                                {cb.lead?.name || "Unnamed Lead"}
                              </p>
                              <p className="font-body text-[11px] text-[#78716c] dark:text-[#a8a29e] mt-0.5 truncate">
                                {cb.lead?.phone || "No phone"}
                              </p>
                              {cb.message_preview && (
                                <p className="font-body text-[10px] text-[#78716c]/80 dark:text-[#a8a29e]/85 mt-1 italic line-clamp-1">
                                  &quot;{cb.message_preview}&quot;
                                </p>
                              )}
                            </div>
                            <button
                              onClick={handleCallbackClick}
                              className="shrink-0 self-center px-3 py-1 bg-amber-500 hover:bg-amber-600 text-white font-label text-[10px] font-bold rounded-lg transition-colors shadow-xs"
                            >
                              Call
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Separator Line */}
                  {callbacks.length > 0 && notifications.length > 0 && (
                    <div className="flex items-center py-1.5 px-1">
                      <span className="text-[10px] font-black uppercase tracking-widest text-[#a8a29e] mr-2 shrink-0">
                        Other Alerts
                      </span>
                      <div className="h-[1px] bg-[#f0ece4] dark:bg-[#292524]/80 flex-1" />
                    </div>
                  )}

                  {/* Section 2: Alerts */}
                  {notifications.length > 0 && (
                    <div className="space-y-2">
                      {callbacks.length === 0 && (
                        <div className="px-1.5 text-[10px] font-black uppercase tracking-widest text-[#a8a29e] flex items-center gap-1.5">
                          <Bell size={11} />
                          System & Lead Alerts ({notifications.length})
                        </div>
                      )}
                      <div className="space-y-2">
                        {notifications.map((n) => {
                          const style = getAlertStyle(n.type);
                          // Strip metadata tags for display
                          const cleanMessage = n.message.replace(/\s*\[(lead_id|handover_id):.*?\]/g, "");
                          
                          // Custom deep-linking click behaviour
                          const leadIdMatch = n.message.match(/\[lead_id:(.*?)\]/);
                          const leadId = leadIdMatch ? leadIdMatch[1] : null;
                          const handleAlertClick = () => {
                            if (leadId) {
                              setIsOpen(false);
                              router.push(`/dashboard/conversations?lead_id=${leadId}`);
                            }
                          };

                          return (
                            <div
                              key={n.id}
                              onClick={handleAlertClick}
                              className={`p-3.5 border rounded-2xl transition-all flex gap-3 group relative ${style.bg} ${leadId ? "cursor-pointer" : ""}`}
                            >
                              <div className="mt-0.5 shrink-0">
                                <div className={`w-7 h-7 rounded-full flex items-center justify-center ${style.iconBg}`}>
                                  {style.icon}
                                </div>
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="font-display text-xs font-black text-[#292524] dark:text-[#f0ece4] truncate">
                                  {n.title}
                                </p>
                                <p className="font-body text-[11px] mt-0.5 leading-relaxed text-[#57534e] dark:text-[#d6cfc9]">
                                  {cleanMessage}
                                </p>
                                <p className="font-label text-[8px] text-[#a8a29e] dark:text-[#78716c] mt-1.5">
                                  {new Date(n.created_at).toLocaleString("en-US", {
                                    month: "short",
                                    day: "numeric",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  })}
                                </p>
                              </div>
                              <button
                                onClick={(e) => handleMarkRead(n.id, e)}
                                className="shrink-0 self-center p-1.5 text-[#a8a29e] dark:text-[#78716c] hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-white dark:hover:bg-[#292524] rounded-lg opacity-0 group-hover:opacity-100 transition-all shadow-xs"
                                title="Dismiss"
                              >
                                <CheckCircle2 size={16} />
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
