export const recoveryPattern = /^SF-[A-Za-z0-9_-]{43}$/;
export async function digest(value: string) {
  return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)))).map(x => x.toString(16).padStart(2,"0")).join("");
}
export function readCookie(request: Request, name: string) {
  return (request.headers.get("cookie") || "").split(";").map(x => x.trim()).find(x => x.startsWith(name + "="))?.slice(name.length + 1) || "";
}
export function cookie(request: Request, name: string, value: string, clear = false) {
  return `${name}=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${clear ? 0 : 2592000}${new URL(request.url).protocol === "https:" ? "; Secure" : ""}`;
}
