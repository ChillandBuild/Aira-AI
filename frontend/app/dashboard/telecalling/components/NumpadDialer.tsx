"use client";
import React from "react";
import { Phone, Delete } from "lucide-react";

interface NumpadDialerProps {
  value: string;
  onChange: (val: string) => void;
  onDial: () => void;
  dialing: boolean;
  disabled?: boolean;
}

export default function NumpadDialer({ value, onChange, onDial, dialing, disabled = false }: NumpadDialerProps) {
  const buttons = [
    { digit: "1", sub: "" },
    { digit: "2", sub: "ABC" },
    { digit: "3", sub: "DEF" },
    { digit: "4", sub: "GHI" },
    { digit: "5", sub: "JKL" },
    { digit: "6", sub: "MNO" },
    { digit: "7", sub: "PQRS" },
    { digit: "8", sub: "TUV" },
    { digit: "9", sub: "WXYZ" },
    { digit: "*", sub: "" },
    { digit: "0", sub: "+" },
    { digit: "#", sub: "" },
  ];

  const handleDigitClick = (digit: string) => {
    onChange(value + digit);
  };

  const handleBackspace = () => {
    onChange(value.slice(0, -1));
  };

  return (
    <div className="w-full max-w-[280px] mx-auto bg-white border border-[#e8e3db]/80 rounded-3xl p-4 shadow-sm flex flex-col gap-3">
      <div className="flex items-center gap-1 bg-[#faf8f5] border border-[#e8e3db]/80 rounded-2xl px-3 py-2.5">
        <input
          type="text"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Enter number to dial..."
          className="flex-1 bg-transparent font-body text-base font-bold text-[#292524] text-center tracking-wider outline-none"
        />
        {value.length > 0 && (
          <button
            onClick={handleBackspace}
            disabled={disabled}
            className="text-[#a8a29e] hover:text-[#57534e] transition-colors p-1"
          >
            <Delete size={16} />
          </button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-2">
        {buttons.map((btn) => (
          <button
            key={btn.digit}
            onClick={() => handleDigitClick(btn.digit)}
            disabled={disabled}
            className="flex flex-col items-center justify-center bg-[#faf8f5] border border-[#e8e3db]/60 hover:bg-[#f5f3ff] hover:border-[#ede9fe] hover:text-[#5b21b6] active:scale-95 rounded-2xl py-2.5 transition-all disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-[#faf8f5] disabled:hover:text-inherit"
          >
            <span className="font-display text-base font-extrabold text-[#292524] hover:text-inherit">{btn.digit}</span>
            <span className="font-label text-[7.5px] text-[#a8a29e] font-bold tracking-wider uppercase mt-0.5">{btn.sub || "\u00A0"}</span>
          </button>
        ))}

        <button
          onClick={onDial}
          disabled={disabled || dialing || !value.trim()}
          className="col-span-3 mt-1 py-3.5 bg-gradient-to-r from-[#5b21b6] to-[#7c3aed] hover:from-[#5b21b6] hover:to-[#6d28d9] text-white rounded-2xl flex items-center justify-center gap-2 font-display text-sm font-extrabold shadow-[0_4px_12px_rgba(99,102,241,0.25)] hover:shadow-[0_6px_16px_rgba(99,102,241,0.4)] disabled:opacity-50 transition-all hover:scale-[1.01] active:scale-[0.99]"
        >
          <Phone size={14} className="fill-white" />
          {dialing ? "Dialing..." : "Call Now"}
        </button>
      </div>
    </div>
  );
}
