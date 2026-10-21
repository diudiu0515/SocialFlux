export type Answer = {
  answer: string | null;
  confidence: "high" | "medium" | "low" | "";
  rationale: string;
  issue: "none" | "unclear" | "multiple" | "insufficient";
};
export type Answers = Record<string, Answer>;
export type Question = {instance_id: string; options: Record<string, string>; [key: string]: unknown};
export class InputError extends Error {}

export function validateAnswers(value: unknown, questions: Question[], complete = false): Answers {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new InputError("标注格式无效，请刷新后重试。");
  const source = value as Record<string, unknown>;
  if (Object.keys(source).some(key => !questions.some(q => q.instance_id === key))) throw new InputError("包含本次任务之外的题目。");
  const clean: Answers = {};
  for (const q of questions) {
    const row = source[q.instance_id] as Record<string, unknown> | undefined;
    if (!row) { if (complete) throw new InputError("请完成全部 6 道题后提交。"); continue; }
    if (typeof row !== "object" || Array.isArray(row)) throw new InputError("答案格式无效。");
    if (Object.keys(row).some(key => !["answer", "confidence", "rationale", "issue"].includes(key))) throw new InputError("答案包含不支持的字段。");
    const answer = row.answer ?? null;
    if (answer !== null && (typeof answer !== "string" || !Object.hasOwn(q.options, answer))) throw new InputError("请选择题目中的一个选项。");
    if (complete && answer === null) throw new InputError("请为每道题选择一个答案。");
    const confidence = row.confidence ?? "";
    if (!["", "high", "medium", "low"].includes(confidence as string)) throw new InputError("把握程度无效。");
    if (complete && !confidence) throw new InputError("请补充每道题的把握程度。");
    const rationale = row.rationale ?? "";
    if (typeof rationale !== "string" || rationale.length > 2000) throw new InputError("判断依据请控制在 2000 字以内。");
    const issue = row.issue ?? "none";
    if (!["none", "unclear", "multiple", "insufficient"].includes(issue as string)) throw new InputError("题目反馈无效。");
    clean[q.instance_id] = {answer: answer as string | null, confidence: confidence as Answer["confidence"], rationale, issue: issue as Answer["issue"]};
  }
  return clean;
}

export function validateStart(value: Record<string, unknown>) {
  if (typeof value.alias !== "string" || !value.alias.trim() || value.alias.trim().length > 40) throw new InputError("请填写 1–40 字的匿名标注编号。");
  if (typeof value.priorExposure !== "boolean") throw new InputError("请选择此前是否看过参考答案。");
  if (value.consent !== true) throw new InputError("请先阅读并确认参与说明。");
  return {alias: value.alias.trim(), priorExposure: value.priorExposure};
}

export function validateRevision(value: unknown): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0) throw new InputError("版本信息缺失，请刷新后重试。");
  return value as number;
}
