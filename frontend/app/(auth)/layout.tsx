import BackgroundAnimation from "@/components/BackgroundAnimation";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#faf8f5] flex items-center justify-center relative overflow-hidden">
      <BackgroundAnimation />
      {children}
    </div>
  );
}
