export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-[100dvh] w-full bg-background relative overflow-x-hidden overflow-y-auto">
      {children}
    </div>
  );
}
