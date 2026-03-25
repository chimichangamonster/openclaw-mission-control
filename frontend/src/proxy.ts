import { NextResponse } from "next/server";
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

import { isLikelyValidClerkPublishableKey } from "@/auth/clerkKey";
import { AuthMode } from "@/auth/mode";

const isClerkEnabled = () =>
  process.env.NEXT_PUBLIC_AUTH_MODE !== AuthMode.Local &&
  isLikelyValidClerkPublishableKey(
    process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY,
  );

// Public routes include home and sign-in paths to avoid redirect loops.
const isPublicRoute = createRouteMatcher(["/", "/sign-in(.*)", "/sign-up(.*)", "/security", "/compliance"]);

function isClerkInternalPath(pathname: string): boolean {
  // Clerk may hit these paths for internal auth/session refresh flows.
  return pathname.startsWith("/_clerk") || pathname.startsWith("/v1/");
}

function requestOrigin(req: Request): string {
  const forwardedProto = req.headers.get("x-forwarded-proto");
  const forwardedHost = req.headers.get("x-forwarded-host");
  const host = forwardedHost ?? req.headers.get("host");
  const proto = forwardedProto ?? "http";
  if (host) return `${proto}://${host}`;
  return new URL(req.url).origin;
}

function returnBackUrlFor(req: Request): string {
  const { pathname, search, hash } = new URL(req.url);
  return `${requestOrigin(req)}${pathname}${search}${hash}`;
}

// Always register clerkMiddleware so it runs at request time.
// The isClerkEnabled() check happens per-request inside the handler,
// not at module-evaluation time (which happens during `next build`
// when env vars may not be available yet).
const clerkHandler = clerkMiddleware(async (auth, req) => {
  if (!isClerkEnabled()) return NextResponse.next();

  if (isClerkInternalPath(new URL(req.url).pathname)) {
    return NextResponse.next();
  }
  if (isPublicRoute(req)) return NextResponse.next();

  const { userId, redirectToSignIn } = await auth();
  if (!userId) {
    return redirectToSignIn({ returnBackUrl: returnBackUrlFor(req) });
  }

  return NextResponse.next();
});

export default clerkHandler;

export const config = {
  matcher: [
    "/((?!_next|_clerk|v1|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
