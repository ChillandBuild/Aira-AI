export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen w-full bg-[#faf8f5] relative overflow-hidden">
      {children}
    </div>
  );
}
