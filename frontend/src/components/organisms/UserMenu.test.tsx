import type {
  AnchorHTMLAttributes,
  ImgHTMLAttributes,
  PropsWithChildren,
  ReactNode,
} from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { UserMenu } from "./UserMenu";

const useUserMock = vi.hoisted(() => vi.fn());
const useAuthMock = vi.hoisted(() => vi.fn());
const clearLocalAuthTokenMock = vi.hoisted(() => vi.fn());
const isLocalAuthModeMock = vi.hoisted(() => vi.fn());
const useOrganizationMembershipMock = vi.hoisted(() => vi.fn());
const usePlatformRoleMock = vi.hoisted(() => vi.fn());
type LinkProps = PropsWithChildren<{
  href: string | { pathname?: string };
}> &
  Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">;

vi.mock("next/image", () => ({
  default: (props: ImgHTMLAttributes<HTMLImageElement>) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img {...props} alt={props.alt ?? ""} />
  ),
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...rest
  }: LinkProps) => (
    <a href={typeof href === "string" ? href : "#"} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock("@/auth/clerk", () => ({
  useUser: useUserMock,
  useAuth: useAuthMock,
  SignOutButton: ({ children }: { children: ReactNode }) => children,
}));

vi.mock("@/auth/localAuth", () => ({
  clearLocalAuthToken: clearLocalAuthTokenMock,
  isLocalAuthMode: isLocalAuthModeMock,
}));

vi.mock("@/lib/use-organization-membership", () => ({
  useOrganizationMembership: useOrganizationMembershipMock,
}));

vi.mock("@/lib/use-platform-role", () => ({
  usePlatformRole: usePlatformRoleMock,
}));

describe("UserMenu", () => {
  beforeEach(() => {
    useUserMock.mockReset();
    useAuthMock.mockReset();
    clearLocalAuthTokenMock.mockReset();
    isLocalAuthModeMock.mockReset();
    useOrganizationMembershipMock.mockReset();
    usePlatformRoleMock.mockReset();
    useAuthMock.mockReturnValue({ isSignedIn: true });
    useOrganizationMembershipMock.mockReturnValue({ isAdmin: false });
    usePlatformRoleMock.mockReturnValue({
      platformRole: null,
      isPlatformOwner: false,
      isPlatformOperator: false,
      isLoading: false,
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders and opens local-mode menu actions", async () => {
    const user = userEvent.setup();
    useUserMock.mockReturnValue({ user: null });
    isLocalAuthModeMock.mockReturnValue(true);

    render(<UserMenu />);

    await user.click(screen.getByRole("button", { name: /open user menu/i }));

    expect(
      screen.getByRole("link", { name: /account settings/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /sign out/i }),
    ).toBeInTheDocument();
  });

  it("shows Admin link only for org admins", async () => {
    const user = userEvent.setup();
    useUserMock.mockReturnValue({ user: null });
    isLocalAuthModeMock.mockReturnValue(true);
    useOrganizationMembershipMock.mockReturnValue({ isAdmin: true });

    render(<UserMenu />);

    await user.click(screen.getByRole("button", { name: /open user menu/i }));

    expect(screen.getByRole("link", { name: /^admin$/i })).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /platform owner/i }),
    ).not.toBeInTheDocument();
  });

  it("shows Platform Owner link only for platform owners", async () => {
    const user = userEvent.setup();
    useUserMock.mockReturnValue({ user: null });
    isLocalAuthModeMock.mockReturnValue(true);
    usePlatformRoleMock.mockReturnValue({
      platformRole: "owner",
      isPlatformOwner: true,
      isPlatformOperator: true,
      isLoading: false,
    });

    render(<UserMenu />);

    await user.click(screen.getByRole("button", { name: /open user menu/i }));

    expect(
      screen.getByRole("link", { name: /platform owner/i }),
    ).toBeInTheDocument();
  });

  it("clears local auth token and reloads on local sign out", async () => {
    const user = userEvent.setup();
    useUserMock.mockReturnValue({ user: null });
    isLocalAuthModeMock.mockReturnValue(true);
    const reloadSpy = vi.fn();
    vi.stubGlobal("location", {
      ...window.location,
      reload: reloadSpy,
    } as Location);

    render(<UserMenu />);

    await user.click(screen.getByRole("button", { name: /open user menu/i }));
    await user.click(screen.getByRole("button", { name: /sign out/i }));

    expect(clearLocalAuthTokenMock).toHaveBeenCalledTimes(1);
    expect(reloadSpy).toHaveBeenCalledTimes(1);
  });
});
