// Credentials live in sessionStorage: they disappear when the tab closes. Logging in with an
// auth provider (Supabase, Clerk, Auth0...) will store the provider's access token here too.
const CREDENTIAL_KEY = "unmeet.apiKey";
const WORKSPACE_KEY = "unmeet.workspaceId";

function read(key: string): string {
  try {
    return window.sessionStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function write(key: string, value: string) {
  try {
    if (value) window.sessionStorage.setItem(key, value);
    else window.sessionStorage.removeItem(key);
  } catch {
    // Storage can be unavailable (private mode): the user simply has to reconnect.
  }
}

export function getCredential(): string {
  return typeof window === "undefined" ? "" : read(CREDENTIAL_KEY);
}

export function getWorkspaceId(): string {
  return typeof window === "undefined" ? "" : read(WORKSPACE_KEY);
}

export function saveCredential(credential: string, workspaceId = "") {
  write(CREDENTIAL_KEY, credential.trim());
  write(WORKSPACE_KEY, workspaceId.trim());
}

export function clearCredential() {
  write(CREDENTIAL_KEY, "");
  write(WORKSPACE_KEY, "");
}
