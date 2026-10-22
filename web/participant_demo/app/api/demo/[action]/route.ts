import { env } from "cloudflare:workers";
import { ConflictError, current, exportRecord, payload, save, start, evidence, researchCatalog } from "../../../../lib/store";
import { InputError } from "../../../../lib/protocol";
import { cookie, digest, readCookie, recoveryPattern } from "../../../../lib/credentials";
export const dynamic = "force-dynamic";
const headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"};
function reply(value: unknown, status = 200, extra = {}) { return Response.json(value, {status, headers: {...headers, ...extra}}); }
async function invited(request: Request, value = readCookie(request, "sf_demo_invite")) {
  if (!/^[A-Za-z0-9_-]{32,100}$/.test(value)) return false;
  const configured = (env as typeof env & {DEMO_INVITE_SHA256?: string}).DEMO_INVITE_SHA256;
  return !!configured && await digest(value) === configured;
}
async function identity(request: Request) {
  const code = readCookie(request, "sf_demo_recovery");
  return recoveryPattern.test(code) ? await digest(code) : "";
}
type Context = {params: Promise<{action: string}>};
export async function GET(request: Request, context: Context) {
  const {action} = await context.params;
  if (!["status", "export"].includes(action)) return reply({error: "没有这个接口。"}, 404);
  try {
    const id = await identity(request), row = id ? await current(id) : undefined;
    if (action === "export") {
      if (!row) return reply({error: "请先开始或恢复标注。"}, 401);
      return reply(exportRecord(row), 200, {"Content-Disposition": 'attachment; filename="socialflux-annotation.json"'});
    }
    return reply(row ? {...payload(row), invited: true} : {session: null, invited: await invited(request), catalog: researchCatalog()});
  } catch { return reply({error: "暂时无法读取记录，请稍后重试。"}, 503); }
}
export async function POST(request: Request, context: Context) {
  const {action} = await context.params;
  if (!["access", "start", "recover", "logout", "draft", "submit", "lock", "gate2-lock", "evidence"].includes(action)) return reply({error: "没有这个接口。"}, 404);
  const origin = request.headers.get("origin");
  if ((origin && origin !== new URL(request.url).origin) || !request.headers.get("content-type")?.startsWith("application/json")) return reply({error: "请求来源或格式无效。"}, 403);
  try {
    const raw = await request.text(); if (raw.length > 1000000) return reply({error: "内容过长。"}, 413);
    let data: Record<string, unknown>;
    try { data = JSON.parse(raw); } catch { return reply({error: "请求格式无效。"}, 400); }
    if (!data || typeof data !== "object" || Array.isArray(data)) return reply({error: "请求格式无效。"}, 400);
    if (action === "access") {
      if (typeof data.invite !== "string" || !await invited(request, data.invite)) return reply({error: "邀请链接无效或已更新，请向研究者索取新的链接。"}, 403);
      return reply({ok: true}, 200, {"Set-Cookie": cookie(request, "sf_demo_invite", data.invite)});
    }
    if (action === "logout") return reply({ok: true}, 200, {"Set-Cookie": cookie(request, "sf_demo_recovery", "", true)});
    if (action === "start" || action === "recover") {
      if (typeof data.recoveryCode !== "string" || !recoveryPattern.test(data.recoveryCode)) throw new InputError("恢复码格式不正确，请复制完整恢复码。");
      const id = await digest(data.recoveryCode), existing = await current(id);
      if (action === "recover") {
        if (!existing || typeof data.alias !== "string" || existing.alias !== data.alias.trim()) return reply({error: "编号或恢复码不匹配，请检查后重试。"}, 401);
        return reply({...payload(existing), invited: true}, 200, {"Set-Cookie": cookie(request, "sf_demo_recovery", data.recoveryCode)});
      }
      if (!await invited(request)) return reply({error: "请从研究者提供的邀请链接开始。"}, 403);
      if (existing && existing.alias !== data.alias) throw new ConflictError("这份记录已存在，请使用原编号恢复。");
      return reply({...await start(id, data), invited: true}, 200, {"Set-Cookie": cookie(request, "sf_demo_recovery", data.recoveryCode)});
    }
    const id = await identity(request);
    if (!id || !await current(id)) return reply({error: "请使用编号和恢复码重新进入。"}, 401);
    if (action === 'evidence') return reply(evidence((await current(id))!, data.instanceId));
    return reply({...await save(id, data, action === "submit", action), invited: true});
  } catch (error) {
    if (error instanceof InputError) return reply({error: error.message}, 400);
    if (error instanceof ConflictError) return reply({error: error.message}, 409);
    return reply({error: "暂时无法保存，请保留此页面并稍后重试。"}, 503);
  }
}
