"use client";
import { AreaChart, Area, ResponsiveContainer } from "recharts";

interface HeroSparklineProps {
  data: { day: string; count: number }[];
  color: string;
  gradientId: string;
}

export function HeroSparkline({ data, color, gradientId }: HeroSparklineProps) {
  if (data.length === 0) return null;

  return (
    <ResponsiveContainer width={96} height={40}>
      <AreaChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.25} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="count"
          stroke={color}
          fill={`url(#${gradientId})`}
          strokeWidth={2.5}
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
