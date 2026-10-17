import s from "./ChannelFlow.module.css";

const INPUTS = ["WhatsApp", "Web chat", "Phone"] as const;
const OUTPUTS = [
  { label: "Hot · call now", tone: "hot" },
  { label: "Warm · follow up", tone: "warm" },
  { label: "Cold · keep in touch", tone: "cold" },
] as const;

const DESCRIPTION = "WhatsApp, web chat and phone lead into Anril AI, which sorts leads into hot, warm and cold";

// Small travelling squares; hidden entirely when reduced motion is asked for.
const DOTS = [
  { path: "f1", dur: "4s", begin: "-1s", fill: "#038285" },
  { path: "f2", dur: "5s", begin: "-3s", fill: "#038285" },
  { path: "f3", dur: "4.5s", begin: "-2s", fill: "#038285" },
  { path: "o1", dur: "4s", begin: "-2.5s", fill: "#9A5A3C" },
  { path: "o2", dur: "5s", begin: "-1.5s", fill: "#038285" },
  { path: "o3", dur: "6s", begin: "-4s", fill: "#566579" },
] as const;

function Mark({ x, y, scale }: { x: number; y: number; scale: number }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${scale})`}>
      <rect x="0" y="0" width="95" height="95" rx="26" fill="#FFFFFF" />
      <rect x="105" y="0" width="95" height="95" rx="26" fill="#038285" />
      <rect x="0" y="105" width="95" height="95" rx="26" fill="#FFFFFF" />
      <rect x="105" y="105" width="95" height="95" rx="26" fill="#FFFFFF" />
    </g>
  );
}

/** Three channels in, one sorted list out. A wide diagram on desktop, a stacked list on phones. */
export function ChannelFlow() {
  return (
    <div className={s.flow}>
      <svg className={s.wide} viewBox="0 0 900 260" role="img" aria-label={DESCRIPTION}>
        <g fill="none" stroke="#0A1528" strokeOpacity=".35" strokeWidth="1.3">
          <path id="flow-f1" d="M170 50 C290 50 290 130 400 130" />
          <path id="flow-f2" d="M170 130 H400" />
          <path id="flow-f3" d="M170 210 C290 210 290 130 400 130" />
          <path id="flow-o1" d="M500 130 C610 130 610 50 720 50" />
          <path id="flow-o2" d="M500 130 H720" />
          <path id="flow-o3" d="M500 130 C610 130 610 210 720 210" />
        </g>
        <g className={s.text} fontWeight="700" fontSize="16">
          {INPUTS.map((label, i) => (
            <g key={label}>
              <rect x="10" y={26 + i * 80} width="160" height="48" fill="#FFFFFF" />
              <text x="90" y={56 + i * 80} textAnchor="middle" fill="#0A1528">{label}</text>
            </g>
          ))}
          <rect x="400" y="80" width="100" height="100" fill="#0A1528" />
          <Mark x={422} y={102} scale={0.28} />
          {OUTPUTS.map((o, i) => (
            <g key={o.label}>
              <rect x="720" y={26 + i * 80} width="170" height="48" fill={o.tone === "hot" ? "#9A5A3C" : "#FFFFFF"} />
              <text x="805" y={56 + i * 80} textAnchor="middle" fill={o.tone === "hot" ? "#FFFFFF" : o.tone === "warm" ? "#0A1528" : "#566579"}>
                {o.label}
              </text>
            </g>
          ))}
        </g>
        <g className={s.dots}>
          {DOTS.map((d) => (
            <rect key={d.path} x="-5" y="-5" width="10" height="10" fill={d.fill}>
              <animateMotion dur={d.dur} begin={d.begin} repeatCount="indefinite">
                <mpath href={`#flow-${d.path}`} />
              </animateMotion>
            </rect>
          ))}
        </g>
      </svg>

      <div className={s.narrow}>
        <ul className={s.col} aria-label="Channels in">
          {INPUTS.map((label) => <li key={label} className={s.box}>{label}</li>)}
        </ul>
        <div className={s.hub}>
          <svg viewBox="0 0 100 100" width="56" height="56" aria-hidden="true" focusable="false">
            <rect width="100" height="100" fill="#0A1528" />
            <Mark x={22} y={22} scale={0.28} />
          </svg>
          <span>Anril AI sorts every lead</span>
        </div>
        <ul className={s.col} aria-label="Leads out">
          {OUTPUTS.map((o) => <li key={o.label} className={`${s.box} ${s[o.tone]}`}>{o.label}</li>)}
        </ul>
      </div>
    </div>
  );
}
