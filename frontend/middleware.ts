import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

function isTokenValid(token: string): boolean {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return false;
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const jsonStr = atob(base64);
    const payload = JSON.parse(jsonStr);
    // 15-second buffer before hard expiry to trigger background refresh in time
    return Boolean(payload?.exp && payload.exp > Math.floor(Date.now() / 1000) + 15);
  } catch {
    return false;
  }
}

function hasValidSessionCookie(request: NextRequest): boolean {
  const allCookies = request.cookies.getAll();
  const authCookies = allCookies.filter(
    (c) => c.name.startsWith("sb-") && c.name.includes("-auth-token")
  );
  if (authCookies.length === 0) return false;

  authCookies.sort((a, b) => a.name.localeCompare(b.name));
  let rawValue = authCookies.map((c) => c.value).join("");
  if (rawValue.startsWith("base64-")) {
    try {
      rawValue = atob(rawValue.slice(7));
    } catch {
      return false;
    }
  }

  try {
    const session = JSON.parse(rawValue);
    const token = Array.isArray(session)
      ? session[0]
      : session.access_token || session[0];
    if (typeof token === "string") {
      return isTokenValid(token);
    }
  } catch {
    return false;
  }
  return false;
}

export async function middleware(request: NextRequest) {
  const isDashboardRoute = request.nextUrl.pathname.startsWith("/dashboard");

  // Fast-path 1: If user has a valid, unexpired session token, skip the
  // remote Supabase network call entirely (~150-250ms latency savings per navigation).
  if (hasValidSessionCookie(request)) {
    return NextResponse.next({ request });
  }

  // Fast-path 2: If requesting a protected route and has zero auth cookies,
  // redirect immediately to /login without querying Supabase.
  const hasAuthCookies = request.cookies
    .getAll()
    .some((c) => c.name.startsWith("sb-") && c.name.includes("-auth-token"));

  if (!hasAuthCookies && isDashboardRoute) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // Fallback: If auth cookie exists but is close to expiry / expired, invoke
  // Supabase client to perform token refresh and persist updated cookies.
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  const { data: { user } } = await supabase.auth.getUser();

  if (!user && isDashboardRoute) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)",
  ],
};
