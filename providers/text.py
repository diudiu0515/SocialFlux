"""Quality-gated retries for free-form model text."""

import re
import unicodedata


def normalize_text(value):
    return "".join(
        character
        for character in str(value)
        if not character.isspace()
        and not unicodedata.category(character).startswith("P")
    )


def _bigrams(value):
    normalized = normalize_text(value)
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index:index + 2] for index in range(len(normalized) - 1)}


def text_similarity(left, right):
    left_grams = _bigrams(left)
    right_grams = _bigrams(right)
    union = left_grams | right_grams
    return len(left_grams & right_grams) / len(union) if union else 1.0


def follows_dialogue_format(value):
    """Reject screenplay directions and explicit speaker labels."""
    text = str(value).strip()
    has_stage_direction = re.search(r"[（(][^）)]{2,}[）)]", text) is not None
    has_speaker_label = re.match(r"^[\w\u4e00-\u9fff·]{1,12}[：:]", text) is not None
    return bool(text) and not has_stage_direction and not has_speaker_label


def avoids_unsupported_offscreen_claim(value, *, environment=False):
    """Reject invented accomplished facts that were not observable this turn."""
    text = str(value).strip()
    if re.search(r"第\s*[一二三四五六七八九十百\d.]+\s*条", text):
        return False
    if re.search(r"(?:申请号|工单号|受理号|编号)\s*(?:为|是|：|:)", text):
        return False
    if re.search(r"[一二三四五六七八九十百\d]+\s*(?:日|天|小时|个?工作日)内", text):
        return False
    if re.search(
        r"(?:我|本人)(?:已经|已|刚刚)\S{0,24}"
        r"(?:提交|发送|上传|转交|通知|联系|完成|签署|批准|登记|备案)",
        text,
    ):
        return False
    if environment and re.search(
        r"(?:系统|人事|HR|合规|法务|委员会|平台)\S{0,16}"
        r"(?:已经|已|自动)\S{0,16}"
        r"(?:锁定|关闭|登记|批准|驳回|收到|转交|通知|生效)",
        text,
        re.IGNORECASE,
    ):
        return False
    return True


def follows_policy_action_format(value):
    """Require one concise in-character action without prompt-facing analysis."""
    text = str(value).strip()
    if len(text) > 180:
        return False
    if "\n" in text or "\r" in text:
        return False
    if re.search(
        r"(?:根据|基于)(?:最新|当前|上述).{0,16}(?:响应|回复|信息|情况).{0,20}"
        r"(?:我将|因此|所以|需要)",
        text,
    ):
        return False
    if re.search(r"(?:我将|下面|以下)(?:提出|给出|列出|说明).{0,8}(?:问题|回答|行动|内容)", text):
        return False
    if re.search(r"(?:^|[：:])\s*[1-9一二三四五六七八九十][.、)]", text):
        return False
    return avoids_unsupported_offscreen_claim(text)


def complete_distinct_text(
    provider,
    messages,
    sampling,
    prior_texts,
    *,
    context,
    max_attempts=5,
    similarity_threshold=0.92,
    validator=None,
):
    """Retry with provider-side seed progression until text is genuinely new."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    prior = [str(value).strip() for value in prior_texts if str(value).strip()]
    for _ in range(max_attempts):
        candidate = provider.complete(messages, **sampling).strip()
        if not follows_dialogue_format(candidate):
            continue
        if validator is not None and not validator(candidate):
            continue
        if all(
            normalize_text(candidate) != normalize_text(previous)
            and text_similarity(candidate, previous) < similarity_threshold
            for previous in prior
        ):
            return candidate
    raise ValueError(
        f"{context} failed distinct-text validation after {max_attempts} attempts"
    )
