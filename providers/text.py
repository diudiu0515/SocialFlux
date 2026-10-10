"""Quality-gated retries for free-form model text."""

import re
import unicodedata


class TextValidationError(ValueError):
    """Validation exhaustion with inspectable candidate-level diagnostics."""

    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = list(diagnostics)


def validation_verdict(validator, candidate):
    if validator is None:
        return True, ""
    result = validator(candidate)
    if isinstance(result, tuple):
        passed, reason = result
        return bool(passed), str(reason or "")
    return bool(result), ""


def normalize_text(value):
    return "".join(
        character
        for character in str(value)
        if not character.isspace()
        and not unicodedata.category(character).startswith("P")
    )


def strip_outer_dialogue_quotes(value):
    """Canonicalize harmless whole-utterance quote wrapping."""
    text = str(value).strip()
    pairs = {"“": "”", '"': '"', "‘": "’"}
    if len(text) >= 2 and pairs.get(text[0]) == text[-1]:
        return text[1:-1].strip()
    return text


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


def dialogue_template_signatures(value):
    """Return discourse templates that become unnatural when repeatedly reused."""
    text = str(value).strip()
    signatures = set()
    if re.match(r"^我(?:接受|同意|理解|确认)", text) and re.search(
        r"(?:但|不过|若|如果|前提)", text
    ):
        signatures.add("acceptance_then_condition")
    if re.search(r"(?:^|[，。！？；])\s*既然", text):
        signatures.add("given_then_condition")
    if re.match(r"^(?:若|如果)", text) and re.search(
        r"(?:我|我们|你)(?:将|就|必须|会)", text
    ):
        signatures.add("conditional_commitment")
    if re.search(
        r"(?:视为无效|自动取消|协议作废|单方面|"
        r"不(?:会)?再(?:接受|容忍|配合|等待|讨论|联系|提供|相信|给.{0,4}机会))",
        text,
    ):
        signatures.add("repeated_ultimatum")
    if re.match(r"^我(?:(?:今天|明天|稍后|之后|届时)?(?:将|会)|可|能)", text):
        signatures.add("future_commitment")
    if re.match(r"^我(?:请求|希望|要求)", text) or "请求" in text:
        signatures.add("repeated_request")
    if re.search(r"(?:^|[，。；])(?:那|所以|鉴于)?我需要", text):
        signatures.add("first_person_need_refrain")
    if re.search(
        r"(?:我需要你|请你|麻烦你).{0,10}(?:说明|明确|确认|解释)|"
        r"我需要.{0,18}(?:说明|明确|确认|解释).{0,14}(?:是否|能否|什么|如何|怎么)",
        text,
    ):
        signatures.add("nested_clarification_refrain")
    if re.match(r"^你(?:试图|企图)", text):
        signatures.add("accusatory_rejection")
    if re.search(r"(?:唯一的?选择|无法改变|彻底无效|即刻失效)", text):
        signatures.add("closed_process_ultimatum")
    if re.search(
        r"(?:再|另行|补充|附上|整理|提交|准备).{0,18}"
        r"(?:一份|表格|清单|报告|草案|目录|记录|文档|材料)",
        text,
    ):
        signatures.add("serial_artifact_offer")
    if re.search(
        r"(?:下周|明天|稍后|届时|到时候).{0,36}"
        r"(?:确认|讨论|审阅|敲定|决定|过一遍|集中对齐|细聊|规划|"
        r"汇报|说明|展示|完善)",
        text,
    ) or re.search(
        r"等.{0,28}(?:后|出来|完成|明确|到).{0,16}(?:再|才).{0,12}"
        r"(?:讨论|细聊|确认|安排|决定|敲定)",
        text,
    ):
        signatures.add("future_review_deferral")
    if re.search(
        r"(?:表格|安排|方案|材料).{0,36}"
        r"(?:确认无误|已确认|按.{0,12}执行|定下来|已备齐)",
        text,
    ):
        signatures.add("reconfirmation_loop")
    artifact_or_plan = (
        r"(?:任务表|分工表|表格|清单|报告|草案|目录|记录|文档|文件|材料|"
        r"副本|附件|存档|提取链接|实验数据|数据格式|格式规范|分工逻辑|分工细节|"
        r"理论部分|提纲|PPT|初稿|资料)"
    )
    handling_move = r"(?:发|发送|查看|看看|确认|调整|讨论|整理|补充|提交|准备|核对|执行|推进|细化|上传|附上)"
    if re.search(
        rf"(?:{artifact_or_plan}.{{0,24}}{handling_move}|"
        rf"{handling_move}.{{0,24}}{artifact_or_plan})",
        text,
    ):
        signatures.add("artifact_or_plan_churn")
    if re.search(
        r"(?:翻篇|已经说定|这事说定|到此为止|不再提|"
        r"往前看|彻底放下|不用总提旧账|这事已经确定)",
        text,
    ):
        signatures.add("resolved_topic_reopening")
    if re.search(
        r"(?:不再|避免|暂停|不会再|不再涉及).{0,16}"
        r"(?:新(?:的)?借款|经济往来|金钱往来|财务往来)|"
        r"只.{0,10}(?:围绕|谈).{0,10}还款.{0,12}"
        r"(?:不再|不涉及).{0,8}(?:其他|经济|借款)",
        text,
    ):
        signatures.add("economic_boundary_refrain")
    if re.search(r"(?:按|照).{0,8}(?:这个|今天的|目前的)?共识.{0,8}(?:执行|推进|来)", text):
        signatures.add("consensus_execution_refrain")
    if re.search(
        r"(?:^|[，。；])(?:明白了?[，,]?)?(?:那)?我先"
        r"(?:联系|对接|协调|确认|落实|处理|完成|整理|跟进|等待)",
        text,
    ):
        signatures.add("serial_task_churn")
    if re.search(
        r"(?:联系|对接|协调).{0,18}"
        r"(?:委员会|秘书|助理|财务|图书馆|部门|成员|场地|办公室)",
        text,
    ):
        signatures.add("serial_external_coordination")
    if re.search(
        r"(?:法务|律师|秘书|助理|委员会|部门).{0,28}"
        r"(?:调取|整理|核查|反馈|发送|存档|准备|安排)|"
        r"(?:让|请|安排|联系|对接|协调).{0,18}"
        r"(?:法务|律师|秘书|助理|委员会|部门)",
        text,
    ):
        signatures.add("third_party_errand_refrain")
    if re.search(r"(?:我方|你方)", text):
        signatures.add("party_pronoun_refrain")
    if re.search(
        r"(?:你只需|你直接|不用特意|专心).{0,40}"
        r"(?:流程|手续|推进|落实|处理|去办|走完|办妥)",
        text,
    ):
        signatures.add("generic_process_push")
    if re.search(r"(?:还款|还钱|第一期|第二期|分期)", text) and re.search(
        r"(?:下周|按时|时间|节点|计划|节奏|执行|到账|完成|安排|期限)",
        text,
    ):
        signatures.add("repayment_schedule_churn")
    if re.search(
        r"(?:等|等待|期待).{0,24}(?:行动|消息|进展|完成|处理|执行|到账|"
        r"情况明朗|之后|再议|再聊)",
        text,
    ):
        signatures.add("future_action_wait")
    if (
        re.search(r"(?:下周|工资|到账|月底|\d+\s*号).{0,28}(?:转账|转给|还款|还钱|还你)", text)
        or re.search(r"(?:转账|转给|还款|还钱|还你).{0,28}(?:下周|工资|到账|月底|\d+\s*号)", text)
    ):
        signatures.add("same_future_transfer")
    if (
        re.search(
            r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)"
            r"\s*(?:元|块|千|万)?",
            text,
        )
        and re.search(
            r"(?:还款|还钱|还你|款项|这笔钱|到账|收到|月底|\d+\s*号)",
            text,
        )
        and re.search(
            r"(?:跟进|确认|落实|执行|安排|收到|到账|按时|确保)",
            text,
        )
    ):
        signatures.add("repayment_followup_refrain")
    if re.search(
        r"(?:书面承诺|转账备注|备注.{0,12}借款归还|担保|第三方|个人账户|"
        r"金额准确|性质和用途)",
        text,
    ):
        signatures.add("transaction_condition_churn")
    settled_object = (
        r"(?:这笔钱|钱的事|还款|欠款|旧账|款项|日期|期限|\d+\s*号|"
        r"安排|方案|分工|边界|决定)"
    )
    settled_move = (
        r"(?:已定|定了|定死|这么定|就按|按.{0,10}执行|照.{0,10}(?:办|走|处理)|"
        r"到此为止|翻篇|不(?:再)?提|别再提|不主动联系|不打扰|"
        r"特殊情况.{0,10}(?:说|告诉|联系)|有变.{0,10}(?:说|告诉|联系))"
    )
    if (
        re.search(rf"{settled_object}.{{0,32}}{settled_move}", text)
        or re.search(rf"{settled_move}.{{0,32}}{settled_object}", text)
    ):
        signatures.add("settled_issue_refrain")
    if re.search(
        r"(?:两清|各自忙各自|各自过好|各自生活|有需要再联系|有事再联系|"
        r"不用再互相|不再互相|只谈是非|只论事不论情|不谈条件|"
        r"回归到最纯粹|再无牵挂)",
        text,
    ):
        signatures.add("relationship_closure_refrain")
    if re.match(
        r"^(?:那好|好的|好[，,]|明白[，,]?|行[，,]?).{0,12}"
        r"(?:我接受|我理解|我尊重|我确认|就这样|就这么)",
        text,
    ):
        signatures.add("acknowledgement_refrain")
    if re.search(
        r"(?:按|照)(?:这个|此|原定|当前)?(?:计划|约定|安排|节奏)"
        r"(?:执行|走|推进|处理|来|办)?",
        text,
    ) or re.search(r"(?:安排已|已经)(?:确认|确定|定下)", text):
        signatures.add("plan_reassurance_loop")
    return signatures


def template_loop_signatures(values, *, max_occurrences=2):
    """Identify rhetorical frames used more than the allowed count."""
    counts = {}
    for value in values:
        for signature in dialogue_template_signatures(value):
            counts[signature] = counts.get(signature, 0) + 1
    return sorted(
        signature
        for signature, count in counts.items()
        if count > (
            1 if signature in {
                "economic_boundary_refrain", "consensus_execution_refrain",
                "repayment_followup_refrain", "third_party_errand_refrain"
            }
            else 3 if signature == "repayment_schedule_churn"
            else max_occurrences
        )
    )


def reused_dialogue_template_signatures(candidate, prior_values, *, allowed_prior=2):
    """Return only templates present in the candidate and already overused."""
    candidate_signatures = dialogue_template_signatures(candidate)
    return sorted(
        signature
        for signature in candidate_signatures
        if sum(
            signature in dialogue_template_signatures(value)
            for value in prior_values
        ) >= (
            1 if signature in {
                "economic_boundary_refrain", "consensus_execution_refrain",
                "repayment_followup_refrain", "third_party_errand_refrain"
            }
            else 3 if signature == "repayment_schedule_churn"
            else allowed_prior
        )
    )


_TEMPLATE_ESCAPE_INSTRUCTIONS = {
    "future_review_deferral": (
        "不要再提下周、稍后、组会或未来再确认；现在直接回答一个尚未解决的实质问题。"
    ),
    "serial_artifact_offer": "不要再提出、补充或发送任何表格、报告、清单、草稿或材料。",
    "artifact_or_plan_churn": "不要再围绕同一文档、数据、提纲、方案做发送、确认、整理或微调。",
    "resolved_topic_reopening": "不要再说翻篇、说定、放心、往前看或以后照此办理；改谈真实未决点。",
    "reconfirmation_loop": "不要再次确认已经确定的安排；直接处理另一个真实未决点。",
    "future_commitment": "不要以“我会/我将”开头或再许诺未来动作；改用现在时作答。",
    "repeated_request": "不要换词重复请求；回应对方刚给出的答案或作出当前选择。",
    "first_person_need_refrain": "不要再用‘我需要……’起句；回应上一答案，提出一个有取舍的方案、边界或当前决定。",
    "nested_clarification_refrain": "不要把已回答内容拆成更小的‘请说明/明确/确认是否’问题；现在综合已有答案并作出选择、提案、保留分歧或收束。",
    "given_then_condition": "不要再使用“既然……那就……”句式。",
    "acceptance_then_condition": "不要再使用“我理解/同意……但是/如果……”句式。",
    "conditional_commitment": "不要再使用条件承诺；给出当前可执行的直接答案。",
    "serial_task_churn": "不要再以“那我先……”领取另一项差事；回到角色的核心目标作出实质选择。",
    "serial_external_coordination": "不要再凭空联系新的部门、秘书、委员会或助理来填充对话。",
    "third_party_errand_refrain": "不要继续把对话外包给法务、律师、助理、秘书或委员会跑腿；由当前角色直接回答可回答的核心问题。",
    "party_pronoun_refrain": "不要再用‘我方/你方’写成法律函件；在这段面对面对话中直接说‘我/你’，并表达当前立场。",
    "generic_process_push": "不要再笼统要求对方走流程或直接去办；明确回答当前核心争议。",
    "repayment_schedule_churn": "还款节点已经讨论充分；不要再确认同一期、同一日期或同一节奏，转向现有的关系边界或责任问题。",
    "future_action_wait": "不要再说等待未来行动、消息或情况明朗；现在回应一个仍未决的实质点。",
    "plan_reassurance_loop": "不要再用按计划、按约定、按节奏执行来安慰性复述；作出新的当前回答或结束该议题。",
    "same_future_transfer": "同一个未来转账承诺已经说清；不要再复述工资到账、下周转账或查收，处理关系边界或结束。",
    "transaction_condition_churn": "不要发明备注、担保、第三方账户、书面承诺等微条件来延长已明确的还款约定。",
    "settled_issue_refrain": "这个议题已经确认过；不要再复述日期、执行、停止联系、特殊情况或已定结论，改谈尚未充分讨论的现有目标面，或只作一次自然收尾。",
    "relationship_closure_refrain": "不要再复述两清、各自生活、有事联系或只论事；若已结束，只在最终轮简短收尾，否则处理另一个现有未决点。",
    "acknowledgement_refrain": "不要再以“那好/明白，我接受/理解/确认”作安慰性回应；直接表达不同的实质判断。",
    "economic_boundary_refrain": "不新增经济往来的边界已经表达过；禁止再次确认、复述或改写，只处理尚未充分讨论的信任/责任问题。",
    "consensus_execution_refrain": "不要再次说按共识执行；共识已在记录中，直接回应一个尚未解决的内容。",
    "repayment_followup_refrain": "同一笔还款的金额、日期和跟进方式已经说清；禁止再次确认、跟进、确保、查收或安排，改谈现有的信任/责任问题。",
}


def template_escape_instructions(signatures):
    """Return concrete Chinese escape moves for rejected discourse frames."""
    return " ".join(
        _TEMPLATE_ESCAPE_INSTRUCTIONS.get(signature, "")
        for signature in signatures
        if _TEMPLATE_ESCAPE_INSTRUCTIONS.get(signature)
    )


def validation_escape_instructions(reason):
    value = str(reason)
    if "same-owner pending commitment was merely renewed" in value:
        return (
            "你已经有尚未履行的承诺；本次禁止再用‘我会/我将/下周/到时候’续诺。"
            "改用现在时直接回答最新问题、说明已经公开的现实约束、承担责任或表达不同意见。"
        )
    if "too many consequential terms" in value:
        return "一次只谈一个实质维度；删除多余比例、期限、权利和工具，不要同时设计整套交易。"
    if "latest open proposal was re-asked" in value:
        return (
            "当前 ledger 中已有待你处置的提案。禁止继续提问或换话题；"
            "先明确说它只能算初步方案、接受、拒绝、提出一个有依据的反方案，"
            "或保留分歧并自然暂停。不要再要求对方重复金额或期限。"
        )
    if "evades the latest obligation" in value:
        return "先直接回答对方刚提出的问题或请求；可以明确接受、拒绝或承认不知道，不能转去另一个议题。"
    if "unprompted coordination actor" in value:
        return "不要新增秘书、助理、法务、委员会或部门代办；由当前角色直接回答，或承认当前无法确认。"
    if "future meeting was reused as dialogue progress" in value:
        return (
            "禁止再提下周、下次见面或到时候再谈；现在就回答一个能当场回答的点，"
            "或明确说明哪个现有问题仍无法确定。"
        )
    if "final turn opened another future cycle" in value:
        return "这是最后一轮；禁止再约未来联系、确认、讨论或执行。用现在时简短回应并自然结束，不复述承诺。"
    if "final turn lacked a natural decision or closure" in value:
        return "这是最后一轮。删除所有问句和问号，不写后续。只输出当前决定或保留的一项分歧，再用‘今天先谈到这里’自然结束。"
    if "future-timed commitment was reported complete" in value:
        return "此前承诺的时间尚未在可观察历史中经过；不得说已完成、已发送或已更新。直接回答当前问题，不虚构时间推进。"
    if "tentative move was upgraded to an agreement" in value:
        return "对方只说了‘尽力/争取/初步考虑’，这不是承诺或约定。明确指出它仍不确定，并要求当场给出可承诺内容，或只讨论当前边界。"
    if "absence of a commitment was rewritten as nonperformance" in value:
        return "公开记录只证明没有形成可核验承诺，不能说承诺未履约、未落地或落空。请原样区分：没有承诺，因此无法判定履约。"
    if "completed-payment amount lacks a public record" in value:
        return "公开记录没有证明某个金额已到账或未到账。删除金额和到账/未到账判断，只回应已明确的事件状态。"
    if "existing obligation was suspended" in value:
        return "可以暂停讨论旧账或拒绝新的经济往来，但既有债务责任仍存在。不要说搁置、暂停、免除或取消经济责任。"
    if "ungrounded institutional procedure or record fact" in value:
        return "公开场景没有给出该协议、条款、会议纪要或系统记录的具体内容；禁止补写规则、步骤或结果。只说明当前角色能确认的边界、承认不知道，或回应关系/取舍。"
    if "untouched public goal" in value:
        return "现在不能收尾或等待未来进展；直接处理一个尚无实质回答的公开维度。"
    if "saturated public goal focus" in value or "same practical focus" in value:
        return "不要再提该焦点；只处理一个尚未讨论的公开维度，且不要借旧焦点过渡。"
    if (
        "other speaker" in value or "ownership" in value
        or "taken over by" in value or "action ownership reversal" in value
        or "contradicts the public evaluated role" in value
        or "contradicts counterparty role ownership" in value
    ):
        return (
            "你写成了另一个人。严格回到 system 指定的当前角色：对方句中的‘我’是对方，"
            "不是你；不要替对方执行、承诺或完成。若对方要求你在两个选项中作决定，"
            "从当前角色直接选择、拒绝或说明无法决定，禁止把同一个选择题再问回对方。"
        )
    return ""


def follows_dialogue_format(value):
    """Reject screenplay directions and explicit speaker labels."""
    text = str(value).strip()
    has_stage_direction = re.search(r"[（(][^）)]{2,}[）)]", text) is not None
    label_match = re.match(r"^([\w\u4e00-\u9fff·]{1,12})[：:]", text)
    # A short clause before a colon is not necessarily a speaker label.  In
    # addition to explicit speech-act verbs, recognize modal/conditional and
    # deictic clause openings such as “不用二选一：” and “两种都要：”.
    # Keep this anchored for the grammatical cues so proper names containing
    # the same character are not broadly exempted.
    label_prefix = label_match.group(1) if label_match else ""
    rhetorical_lead = (
        re.search(
            r"(?:建议|提议|明确|确认|询问|结论|决定|说明|补充|接受|同意|认为|要求|回应)",
            label_prefix,
        )
        or re.match(
            r"^(?:不用|不要|不必|不能|可以|应该|需要|必须|"
            r"先|再|两种|无论|如果|若|具体|现在|眼下|当前|这(?:个|件|里))",
            label_prefix,
        )
    )
    has_speaker_label = bool(label_match and not rhetorical_lead)
    has_quote_framing = (
        (text.startswith(("“", '"')) and text.endswith(("”", '"')))
        or "：“" in text
    )
    has_narrated_delivery = re.match(
        r"^[\w\u4e00-\u9fff·]{1,12}(?:眉头|语气|神情|目光|沉默|"
        r"点头|摇头|叹气|皱眉|看向|低头|抬头)",
        text,
    ) is not None
    return (
        bool(text)
        and not has_stage_direction
        and not has_speaker_label
        and not has_quote_framing
        and not has_narrated_delivery
    )


def addresses_speaker_as_other(value, speaker):
    """Detect a response that addresses its own character name/role."""
    text = str(value).strip()
    labels = {
        str((speaker or {}).get(key, "")).strip()
        for key in ("name", "role")
    } - {""}
    return any(
        re.match(rf"^{re.escape(label)}(?:[，,:：]|您好|您)", text) is not None
        for label in labels
    )
def avoids_unsupported_offscreen_claim(value, *, environment=False):
    """Reject invented accomplished facts that were not observable this turn."""
    text = str(value).strip()
    if re.search(r"第\s*[一二三四五六七八九十百\d.]+\s*条", text):
        return False
    if re.search(r"(?:申请号|工单号|受理号|编号)\s*(?:为|是|：|:)", text):
        return False
    if re.search(
        r"(?:我|本人)(?:已经|已|刚刚|现已)\S{0,24}"
        r"(?:提交|发送|上传|转交|通知|联系|完成|签署|批准|登记|备案|"
        r"整理|更新|查清|获取|撤回|申请)",
        text,
    ):
        return False
    if environment and re.search(
        r"(?:系统|人事|HR|合规|法务|委员会|平台|行政助理|教学办|学院)\S{0,20}"
        r"(?:会|将|准备|打算)\S{0,20}(?:发送|提交|通知|联系|批准|登记|备案)",
        text,
        re.IGNORECASE,
    ):
        return False
    if environment and re.search(
        r"(?:系统|人事|HR|合规|法务|委员会|平台|行政助理|教学办|学院)\S{0,16}"
        r"(?:已经|已|自动)\S{0,16}"
        r"(?:锁定|关闭|登记|批准|驳回|收到|转交|通知|生效|完成|备案)",
        text,
        re.IGNORECASE,
    ):
        return False
    if environment and re.search(
        r"(?:系统|人事|HR|合规|法务|委员会|秘书处|平台|行政助理|教学办|学院|调查组|听证会)"
        r"\S{0,32}(?:已|将|会|自动|直接|即刻)\S{0,24}"
        r"(?:触发|判定|批准|拒绝|冻结|取消|生效|转为|启动|追究|"
        r"受理|剔除|暂停|锁定|失效|退回|封存|裁决|处分)",
        text,
        re.IGNORECASE,
    ):
        return False
    if environment and re.search(
        r"(?:即刻|立即|已经|已|将|会|直接|自动)\S{0,20}"
        r"(?:启动|冻结|暂停|封存|锁定|驳回|裁决|处分|认定|判定)\S{0,24}"
        r"(?:系统|人事|HR|合规|法务|委员会|秘书处|平台|教学办|学院|调查组|听证会|权限|资格|流程|程序)",
        text,
        re.IGNORECASE,
    ):
        return False
    if environment and re.search(
        r"(?:材料|资格|署名|毕业|权限|流程|程序|调查|听证|裁决|处分)\S{0,24}"
        r"(?:直接|自动|即刻|已经|已)\S{0,16}"
        r"(?:判定|视为|作废|终止|取消|冻结|启动|生效|失效|锁定|封存)",
        text,
    ):
        return False
    if environment and re.search(r"(?:法定程序|法定前置|既定的?调查结论|无权再)", text):
        return False
    if environment and re.search(
        r"(?:正在|目前正在).{0,16}(?:整理|准备|发送|提交|上传|协调).{0,16}"
        r"(?:文件|记录|材料|草案|条款|流程|章程|副本)|"
        r"(?:文件|记录|材料|草案|条款|流程|章程|副本).{0,16}(?:正在|目前正在)"
        r".{0,12}(?:整理|准备|发送|提交|上传|协调)",
        text,
    ):
        return False
    if environment and re.search(
        r"(?:文件|记录|材料|草稿|草案|摘要|说明|流程).{0,18}"
        r"(?:还在|仍在).{0,18}(?:汇总|整理|流转|审核)|"
        r"(?:还在|仍在).{0,18}(?:汇总|整理|流转|审核).{0,18}"
        r"(?:文件|记录|材料|草稿|草案|摘要|说明|流程)",
        text,
    ):
        return False
    if environment and re.search(
        r"(?:流程|核验|审查|程序).{0,12}(?:已经|已|现已)(?:开始|启动|完成)|"
        r"(?:已经|已|现已)(?:开始|启动|完成).{0,12}(?:流程|核验|审查|程序)",
        text,
    ):
        return False
    return True


def confirms_unobserved_completion(response, latest_action):
    """Detect treating a promised future action as already completed."""
    action = str(latest_action).strip()
    text = str(response).strip()
    completion_verbs = (
        r"(?:转|转账|发|发送|提交|上传|整理|处理|完成|更新|调整|准备|"
        r"交付|付款|汇款)"
    )
    pending = re.search(
        rf"(?:我(?:今天|现在|马上|稍后|之后|待会|会|将|先|准备|打算|计划)|"
        rf"那我|由我).{{0,28}}{completion_verbs}",
        action,
    )
    already_done = re.search(
        rf"(?:已经|刚刚|现已|已).{{0,18}}{completion_verbs}|"
        rf"{completion_verbs}(?:完|好了|过了|给你了)",
        action,
    )
    receipt_text = re.sub(
        r"(?:未|没|没有|尚未|还没)收到(?:款项|钱|材料|资料|文件)?",
        "",
        text,
    )
    claimed_receipt = re.search(
        r"(?:(?:已经|已)?收到(?:款项|钱|转账|材料|资料|文件|记录|日志|附件)|"
        r"(?:钱|款项|转账|材料|资料|文件|记录|日志|附件).{0,8}收到(?:了)?|"
        r"资料已收悉|款项已到账|确认无误)",
        receipt_text,
    )
    claimed_completion = re.search(
        rf"(?:已经|刚刚|现已|已).{{0,18}}"
        rf"(?:{completion_verbs}|注明|记录|归档)|"
        rf"(?:{completion_verbs}|注明|记录|归档)(?:完|好了|过了)",
        text,
    )
    shared = (_bigrams(action) & _bigrams(text)) - {
        "我会", "我先", "已经", "目前", "可以", "需要", "确认",
        "提交", "记录", "材料", "说明", "安排", "处理",
    }
    return bool(
        pending
        and not already_done
        and (claimed_receipt or (claimed_completion and shared))
    )


def _first_person_move_cores(value):
    cores = []
    for clause in re.split(r"[，。；！？]", str(value)):
        owner = re.search(r"我(?!们)", clause)
        if not owner:
            continue
        prefix = clause[:owner.start()].strip()
        if re.search(r"(?:通知|告诉|告知|提醒|请|让|要求|希望|需要)$", prefix):
            # Here “我” is the recipient/object, not the actor taking ownership.
            continue
        core = clause[owner.end():]
        core = re.sub(
            r"^(?:也|这边|这里|会|将|先|这就|立刻|马上|正在|尽快|"
            r"可以|可|需要|打算|计划)+",
            "",
            core,
        )
        core = normalize_text(core)
        if len(core) >= 4:
            cores.append(core)
    return cores


def mirrors_latest_speaker_move(candidate, latest_other_utterance):
    """Detect silently taking over the other speaker's first-person action."""
    candidate_text = str(candidate)
    non_ownership_question = bool(
        re.search(r"(?:是否|能否|吗|？|\?)", candidate_text)
        and not re.search(
            r"我(?:会|将|先|负责|已经|已|刚刚|现已).{0,16}"
            r"(?:汇报|核实|修改|推进|整理|发送|提交|转账|付款|执行|"
            r"完善|核对|检查|更新|准备|处理|联系|通知|要求|暂停)",
            candidate_text,
        )
    )
    accepts_other_move = bool(
        re.match(r"^我(?:接受|同意|认可)", candidate_text)
        and not re.match(r"^我(?:会|将|先|负责|已经|已)", candidate_text)
    )
    acknowledges_other_move = bool(
        re.match(r"^我(?:确认|理解)(?:你|了你|对方)", candidate_text)
    )
    candidate_cores = _first_person_move_cores(candidate)
    other_cores = _first_person_move_cores(latest_other_utterance)
    move_verbs = (
        r"(?:汇报|核实|修改|推进|整理|发送|提交|确认|转账|付款|执行|"
        r"完善|填充|搭建|复核|核对|检查|更新|准备|处理|联系|通知|要求|暂停|"
        r"同步|标注|还款|偿还)"
    )
    for left in candidate_cores:
        left_grams = _bigrams(left)
        for right in other_cores:
            right_grams = _bigrams(right)
            smaller = min(len(left_grams), len(right_grams))
            if (
                smaller
                and len(left_grams & right_grams) / smaller >= 0.62
                and re.search(move_verbs, left)
                and re.search(move_verbs, right)
                and not (
                    non_ownership_question
                    or accepts_other_move
                    or acknowledges_other_move
                )
            ):
                return True
            shared_verbs = set(re.findall(move_verbs, left)) & set(
                re.findall(move_verbs, right)
            )
            if (
                non_ownership_question
                or accepts_other_move
                or acknowledges_other_move
            ):
                shared_verbs.discard("确认")
                shared_verbs.discard("查看")
            left_objects = _bigrams(re.sub(move_verbs, "", left))
            right_objects = _bigrams(re.sub(move_verbs, "", right))
            if (
                shared_verbs
                and left_objects & right_objects
                and not non_ownership_question
                and not accepts_other_move
            ):
                return True
    return False


def claims_other_speaker_commitment(candidate, ledger, speaker):
    """Reject taking over or prematurely consuming another party's pending move."""
    other = "environment_agent" if speaker == "evaluated_agent" else "evaluated_agent"
    for item in (ledger or {}).get("commitments", []):
        if item.get("speaker") != other or item.get("status") != "pending":
            continue
        if mirrors_latest_speaker_move(candidate, item.get("text", "")):
            return True
        promised = str(item.get("object") or item.get("text", ""))
        artifacts = set(re.findall(
            r"(?:摘要|文件|副本|记录|材料|报告|清单|方案|草稿|结果|反馈)",
            promised,
        ))
        consumed = re.search(
            r"(?:你|对方)(?:(?:已经|已|刚刚|刚)"
            r"(?:提供|发送|提交|整理|给出|发来|交付)的?"
            r".{0,10}(?:摘要|文件|副本|记录|材料|报告|清单|方案|草稿|结果|反馈)|"
            r"(?:提供|发送|提交|整理|给出|发来|交付)的.{0,10}"
            r"(?:摘要|文件|副本|记录|材料|报告|清单|方案|草稿|结果|反馈))",
            str(candidate),
        )
        if consumed and artifacts & set(re.findall(
            r"(?:摘要|文件|副本|记录|材料|报告|清单|方案|草稿|结果|反馈)",
            consumed.group(0),
        )):
            return True
    return False


def contradicts_pending_own_commitment(candidate, ledger, speaker):
    """Reject explicit reversal of the speaker's observable future promise."""
    text = str(candidate)
    strong_withdrawal = re.search(
        r"(?:我)?(?:不会|不再|取消|撤回|拒绝|不能再|无法再)"
        r"[^，,。！？；]{0,14}"
        r"(?:还款|还钱|转账|付款|汇款|联系|告诉|提交|发送|完成|履行|兑现)",
        text,
    )
    weak_withdrawal = re.search(
        r"(?:还得看|取决于|不能保证|无法确定|不确定|再等等|"
        r"暂时.{0,8}(?:不|没|无法|不能))",
        text,
    )
    if not strong_withdrawal and not weak_withdrawal:
        return False
    candidate_focus = _candidate_focus(text)
    candidate_anchors = set(re.findall(
        r"(?:月底|下周|明天|稍后|到时候|届时|半个月后|一旦.{0,8}|\d+\s*号)",
        text,
    ))
    for item in (ledger or {}).get("commitments", []):
        if item.get("speaker") != speaker or item.get("status") != "pending":
            continue
        promised = str(item.get("text", ""))
        if not re.search(r"(?:我会|我将|我答应|我承诺|准时|按约定)", promised):
            continue
        if not candidate_focus or candidate_focus != _candidate_focus(promised):
            continue
        promised_anchors = set(re.findall(
            r"(?:月底|下周|明天|稍后|到时候|届时|半个月后|一旦.{0,8}|\d+\s*号)",
            promised,
        ))
        if strong_withdrawal or candidate_anchors & promised_anchors:
            return True
    return False


def asserts_ungrounded_performance_amount(candidate, observable_history):
    """Reject a precise paid/received amount newly asserted as completed fact."""
    text = str(candidate)
    patterns = (
        r"(?:这次|本次|实际|已经|已).{0,12}(?:履行|支付|还(?:了|款)|到账)"
        r"(?:了|为|是|共计|合计|：|:|\s){0,8}(?P<amount>\d+(?:\.\d+)?)\s*元",
        r"(?P<amount>\d+(?:\.\d+)?)\s*元.{0,12}"
        r"(?:已经|已|实际)?(?:到账|支付|履行|还清)",
    )
    match = next((m for pattern in patterns if (m := re.search(pattern, text))), None)
    if not match:
        return False
    window = text[max(0, match.start() - 24):min(len(text), match.end() + 24)]
    if (
        re.search(
            r"(?:等|等待|如果|若|一旦|尚未|还没|没有|未能|会|将|预计|承诺|"
            r"无法确认|不能确认|暂时无法).{0,32}"
            r"(?:到账|支付|履行|还清)",
            window,
        )
        or re.search(r"(?:到账|支付|履行|还清)(?:记录)?(?:后|以后|之后)", window)
    ):
        return False
    amount = re.escape(match.group("amount"))
    observed = str(observable_history)
    return not bool(any(re.search(pattern.replace(
        r"(?P<amount>\d+(?:\.\d+)?)", amount
    ), observed) for pattern in patterns))


def asserts_ungrounded_remaining_amount(candidate, observable_history):
    """Reject a precise residual balance unless it is already a public fact."""
    text = str(candidate)
    match = re.search(
        r"(?:剩余(?:未还)?(?:金额|欠款)?|尚欠|还欠|还有)"
        r"(?:我确认|确认为|确认|我认为|明确|目前|现在|共计|合计|为|是|有|了|：|:|\s){0,8}"
        r"(?P<amount>\d+(?:\.\d+)?)\s*元",
        text,
    )
    if not match:
        return False
    amount = re.escape(match.group("amount"))
    observed = str(observable_history)
    return not bool(re.search(
        rf"(?:剩余(?:未还)?(?:金额|欠款)?|尚欠|还欠|还有)"
        rf"(?:我确认|确认为|确认|我认为|明确|目前|现在|共计|合计|为|是|有|了|：|:|\s){{0,8}}"
        rf"{amount}\s*元",
        observed,
    ))


def repeats_own_utterance_without_new_challenge(
    candidate, history, speaker, segment_turn_id, latest_other_utterance=""
):
    """Catch reviewed exact self-loops inside one fragment, not cross-event echoes."""
    if int(segment_turn_id or 0) <= 0:
        return False
    value = normalize_text(candidate)
    own = [
        normalize_text(item.get("text", ""))
        for item in history
        if item.get("role") == speaker
    ][-int(segment_turn_id):]
    if not value or value not in own:
        return False
    return not bool(re.search(
        r"(?:再确认|重新确认|仍然|还是|是否仍|你确定|请再说|再说明|改变了?吗)",
        str(latest_other_utterance),
    ))


def copies_latest_other_utterance(candidate, latest_other_utterance):
    """Reject a substantive verbatim or near-verbatim cross-speaker echo."""
    candidate_value = normalize_text(candidate)
    latest_value = normalize_text(latest_other_utterance)
    if not candidate_value or len(candidate_value) < 12:
        return False
    if candidate_value == latest_value:
        return True
    return bool(
        len(candidate_value) >= 20
        and len(latest_value) >= 20
        and text_similarity(candidate_value, latest_value) >= 0.93
    )


def repeats_exactly_without_substantive_public_event(
    candidate, history, speaker, latest_other_utterance=""
):
    """Catch an exact cross-fragment refrain unless new evidence or a challenge warrants it."""
    value = normalize_text(candidate)
    if not value:
        return False
    matching_indexes = [
        index for index, item in enumerate(history)
        if item.get("role") == speaker
        and normalize_text(item.get("text", "")) == value
    ]
    if not matching_indexes:
        return False
    if re.search(
        r"(?:再确认|重新确认|仍然|还是|是否仍|你确定|请再说|再说明|改变了?吗)",
        str(latest_other_utterance),
    ):
        return False
    since_match = history[matching_indexes[-1] + 1:]
    substantive_public_event = any(
        item.get("event_id")
        and not str(item.get("event_id")).endswith((":time", ":opening"))
        for item in since_match
    )
    return not substantive_public_event


def contradicts_explicit_installment_total(candidate, latest_other_utterance):
    """Catch a direct arithmetic contradiction in an explicit two-part split."""
    latest = str(latest_other_utterance)
    text = str(candidate)
    split = re.search(
        r"先.{0,16}?(\d+)\s*元.{0,24}?余下\s*(\d+)\s*元",
        latest,
    )
    comparison = re.search(
        r"(?:之前|原先|原来).{0,8}?(\d+)\s*元.{0,20}?"
        r"(?:总金额|总额).{0,8}?(?:减少|降低|变少)",
        text,
    )
    if not split or not comparison:
        return False
    first, second = (int(split.group(1)), int(split.group(2)))
    return first + second == int(comparison.group(1))


def opens_new_repayment_commitment(candidate):
    """Detect a newly proposed future repayment action, not a past outcome citation."""
    text = str(candidate)
    actor_future = re.search(
        r"(?:我|你|我们)[^。！？]{0,6}"
        r"(?:会|将|要|一定|准备|打算|计划|争取|预计|能|可以)"
        r"[^。！？]{0,16}(?:还款|还钱|补上|转账|付款|汇款|履约|履行(?:还款|承诺))",
        text,
    )
    timed_future = re.search(
        r"(?:今天|明天|后天|接下来|未来|今后|以后|"
        r"(?:\d+|[一二两三四五六七八九十]+)\s*天(?:后|内))"
        r"[^。！？]{0,16}(?:会|将|要|一定|准备|打算|计划|争取|预计)"
        r"[^。！？]{0,10}(?:还款|还钱|补上|转账|付款|汇款|履约|履行(?:还款|承诺))",
        text,
    )
    return bool(actor_future or timed_future)


def violates_role_specific_action(candidate, role):
    """Catch narrow, explicit role inversions supported by the public role card."""
    role_text = " ".join(str((role or {}).get(key, "")) for key in (
        "name", "role", "explicit_goal"
    ))
    text = str(candidate)
    ownership_text = re.sub(
        r"我(?:会|将)?(?:等|待).{0,6}你.{0,16}"
        r"(?:还款|还钱|转账|付款|汇款|提供转账记录)",
        "",
        text,
    )
    if re.search(r"(?:出借|债权|要求.{0,8}还款|落实还款)", role_text):
        if re.search(
            r"我.{0,14}(?:还你|还给你|转账给你|给你转账|准时转账)",
            ownership_text,
        ):
            return True
        if re.search(
            r"(?:我(?:会|将|先|现在|今天|马上|可以)|由我).{0,10}"
            r"(?:还款|还钱|转账|付款|汇款|把钱转给你)",
            ownership_text,
        ):
            return True
        if re.search(
            r"我(?!们)[^你。！？]{0,16}(?:能|可以|准备|打算|计划|先)"
            r"[^你。！？]{0,8}(?:还(?:款|钱|\d)|转账|付款|汇款)",
            ownership_text,
        ):
            return True
        if re.search(
            r"(?:先|暂时)(?:放下|暂停|搁置).{0,12}(?:还款|借款|期限|还款时间)|"
            r"我.{0,8}(?:暂时)?不接电话|"
            r"你希望我怎么做.{0,12}(?:让你|使你)(?:安心|放心)",
            ownership_text,
        ):
            return True
    return False


def violates_environment_counterparty_role(candidate, evaluated_role):
    """Catch role reversal when the public evaluated role uniquely fixes ownership."""
    role_text = " ".join(str((evaluated_role or {}).get(key, "")) for key in (
        "name", "role", "explicit_goal"
    ))
    text = re.sub(
        r"(?:向|给)你(?=.{0,10}(?:发送|提供|说明|告知|展示|附上))",
        "向对方",
        str(candidate),
    )
    if re.search(r"(?:出借|债权|要求.{0,8}还款|落实还款)", role_text):
        if re.search(
            r"你(?:能|可以).{0,12}(?:还款|还钱|转账|付款|汇款)", text
        ):
            return True
        if re.search(
            r"(?:需要|想|希望)(?:先)?(?:知道|确认|明确)你.{0,18}"
            r"(?:能|可以|打算|计划)?还(?:多少|款|钱)",
            text,
        ):
            return True
        if re.search(r"(?:还款|还钱|转账|付款|汇款|\d+(?:\.\d+)?\s*(?:元|块|千|万))", text) and re.search(
            r"(?:希望|要求)你.{0,20}(?:完成|落实|履行)|"
            r"我(?:接受|确认).{0,16}你提出.{0,16}(?:还款|金额)",
            text,
        ):
            return True
        if re.search(
            r"(?:需要|希望|要求|请)你.{0,10}(?:先)?说明.{0,14}"
            r"(?:临时支出|资金困难|手头情况)", text,
        ):
            return True
        if re.search(
            r"(?:(?:请|需要|希望|等|由|让)你|你(?:会|要|得|应|必须))"
            r".{0,16}(?:还款|还钱|转账|付款|汇款|还给我)",
            text,
        ) or re.search(r"你那边.{0,8}(?:资金|钱).{0,6}(?:到位|到账)", text):
            return True
        if re.search(
            r"(?:等|待)你.{0,14}(?:发薪|资金|还款|消息确切|钱到位|宽裕|情况明朗|需要)",
            text,
        ):
            return True
        if re.search(
            r"我理解你(?:目前|现在|最近)?(?:的)?(?:处境|困难|资金压力|手头紧)",
            text,
        ):
            return True
        if re.search(
            r"你.{0,12}(?:告诉|说明|决定|确定|定下).{0,12}"
            r"(?:怎么还|还款|还多少|日期|金额|期限)|"
            r"你.{0,10}(?:首期|第一期).{0,12}(?:承担|金额)",
            text,
        ):
            return True
        if re.search(
            r"(?:还款|欠款|第一期|分期).{0,18}(?:让我安心|让我踏实|给我交代)",
            text,
        ):
            return True
        if re.search(
            r"我(?:会|将|继续|先).{0,10}(?:观察|等待|查看|核验|要求)"
            r".{0,14}(?:实际履约|还款计划|还款记录|转账记录)|"
            r"未来(?:任何)?经济请求.{0,16}我(?:会|将).{0,8}"
            r"(?:要求|查看|核验).{0,12}(?:还款计划|还款记录|转账记录)",
            text,
        ):
            return True
        if re.search(
            r"(?:(?:我)?收到.{0,8}(?:钱|款|转账|\d+\s*块|[一二两三四五六七八九十百千万]+(?:元|块|千|万)?|"
            r"[一二两三四五六七八九十百千万]+\s*块)|"
            r"(?:钱|款|转账|\d+\s*块|[一二两三四五六七八九十百千万]+\s*块)"
            r".{0,8}(?:我)?收到(?:了)?)",
            text,
        ):
            return True
    return False


_CANDIDATE_FOCUS_PATTERNS = (
    (
        "communication_boundary",
        r"边界|沟通|联系|隐瞒|主动说明|提前(?:通知|告诉|说)|"
        r"不(?:再)?提|别提|不打扰|互相确认|特殊情况|有变|当面说|"
        r"绕弯子|问好|保持安静|相处|界限|见面|私人|隐私|个人状况|"
        r"追问|不愿.{0,6}(?:讨论|回应)",
    ),
    ("trust_repair", r"信任|关系|友谊|情谊|情义|朋友|感情|伤害|失望|道歉|体谅|尊重|氛围|轻松"),
    ("economic_boundary", r"经济往来|金钱往来|不再借|不会再借|停止借款|暂停借款|以后不借"),
    ("governance", r"治理|董事|席位|提名|决策权|否决权|执行权|咨询权|意见权|产品委员会|投票权重|预算审批|职能(?:边界|模块)|资源分配(?:权|建议)"),
    ("equity", r"股权|稀释|权益|补偿|融资|持股比例"),
    ("authorization", r"授权|共同签署|共同确认|授权确认|确认流程|关键步骤|书面确认|未经确认|确认环节"),
    (
        "artifact_workflow",
        r"(?:(?:发|发送|查看|调取|整理|提交|准备|核对|上传|附上).{0,18}"
        r"(?:书面|文档|文件|材料|报告|表格|清单|记录|草案|副本|附件)|"
        r"(?:书面|文档|文件|材料|报告|表格|清单|记录|草案|副本|附件).{0,18}"
        r"(?:发|发送|查看|调取|整理|提交|准备|核对|上传|附上))",
    ),
    ("authorship", r"署名|作者|贡献|论文"),
    ("graduation", r"毕业|答辩|学位|学分"),
    ("performance_basis", r"绩效|评级|评分|晋升|反馈"),
    ("care_responsibility", r"照护|照顾|分工|轮班|陪诊|家务"),
    ("responsibility", r"责任|承担|负责|归属"),
    (
        "practical_execution",
        r"还款|还钱|还你|转账|汇款|工资|到账|借款归还|分期|担保|备注|"
        r"时间范围|时间框架|周期|日期|期限|节点|执行计划|大致预期|"
        r"报告|表格|清单|材料|记录|文档|草稿|草案|数据|资金流向|账目|"
        r"方案|具体金额|款项|这笔钱|钱的事|旧账|欠款|账|发薪|"
        r"转过去|一半|月底|[一二三四五六七八九十百\d]+千|"
        r"下周|明天|稍后|组会|会议|到时候|届时|\d+\s*号|"
        r"多久|什么时候|何时|哪天|几天|能还|开始还|具体数字|分几次|"
            r"具体.{0,6}(?:数|多少|时间)|确切.{0,6}(?:时间|日期)|"
            r"\d+\s*(?:元|块|万)|[一二两三四五六七八九十百千万]+\s*(?:元|块|万)",
    ),
)


def _candidate_focus_scores(text):
    value = str(text)
    return {
        focus: len(re.findall(pattern, value))
        for focus, pattern in _CANDIDATE_FOCUS_PATTERNS
        if re.search(pattern, value)
    }


def _candidate_focus(text):
    scores = _candidate_focus_scores(text)
    if not scores:
        return None
    order = {focus: index for index, (focus, _) in enumerate(_CANDIDATE_FOCUS_PATTERNS)}
    return max(scores, key=lambda focus: (scores[focus], -order[focus]))


def _observable_commitment_terms(text):
    patterns = (
        r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)\s*(?:元|块|千|万|成|%)",
        r"(?:今天|明天|后天|今日内|今天内|本周|下周|本月|下月|下个月|月底|月初|每月|每周|分期|"
        r"(?:\d+|[一二两三四五六七八九十]+)\s*(?:分钟|小时|天)(?:后|内))",
        r"(?:提前|有变|变化|延期|收入|工资|到账|困难|手头紧)",
    )
    return {
        match.group(0)
        for pattern in patterns
        for match in re.finditer(pattern, str(text))
    }


def renews_pending_commitment_without_change(
    candidate, ledger, speaker, newest_observable_text=""
):
    """Reject another promise when the same owner's same-focus promise is pending."""
    text = str(candidate)
    promise_wording = re.search(
        r"(?:我(?:今天|明天|后天|稍后|之后|届时|下周|下月|月底)?(?:会|将|先|可以)|"
        r"(?:今天|明天|后天|下周|下月|月底).{0,8}我.{0,8}"
        r"(?:会|将|提交|整理|说明|提出|发送|提供)|"
        r"我(?:今天|明天|后天|下周|下月|月底).{0,18}"
        r"(?:提交|整理|说明|提出|发送|提供).{0,12}(?:会|将|时|后)|"
        r"我答应|我承诺|由我来|我负责)|"
        r"(?:方案|文件|材料|草案|记录|款项).{0,16}"
        r"(?:今天|明天|稍后|之后|届时|会|将).{0,12}"
        r"(?:发|发送|提供|整理|提交|上传|转账|处理)",
        text,
    )
    if not promise_wording or re.search(r"(?:我不会|我不再|我无法|我不能)", text):
        return False
    focus = _candidate_focus(text)
    pending = [
        item for item in (ledger or {}).get("commitments", [])
        if item.get("speaker") == speaker and item.get("status") == "pending"
    ]
    if not pending:
        return False
    same_focus = [
        item for item in pending
        if (
            focus
            and (item.get("focus") or _candidate_focus(item.get("text", ""))) == focus
        ) or len(
            (_bigrams(text) & _bigrams(item.get("object") or item.get("text", "")))
            - {"我会", "我将", "可以", "目前", "之后", "需要", "确认"}
        ) >= 2
    ]
    if not same_focus and re.search(
        r"(?:按(?:之前|原来|计划|约定)|照旧|先行动|推进|落实|说到做到)",
        text,
    ):
        same_focus = pending
    if not same_focus:
        return False
    new_terms = _observable_commitment_terms(text)
    old_terms = {
        term
        for item in same_focus
        for term in (item.get("terms") or _observable_commitment_terms(item.get("text", "")))
    }
    added_terms = new_terms - old_terms
    if added_terms and all(
        term in str(newest_observable_text) for term in added_terms
    ):
        return False
    generic = {
        "我会", "我将", "如果", "之后", "后续", "目前", "需要", "明确",
        "安排", "方案", "执行", "确认", "接受", "要求", "继续", "参与",
    }
    candidate_grams = _bigrams(text) - generic
    for item in same_focus:
        promised = str(item.get("object") or item.get("text", ""))
        shared = candidate_grams & (_bigrams(promised) - generic)
        if len(shared) >= 2:
            return True
    return bool(re.search(
        r"(?:按(?:之前|原来|计划|约定)|照旧|保持承诺|说到做到)", text
    ))


def repeats_future_meeting_deferral(candidate, history, speaker):
    """Reject a second same-speaker use of future review as dialogue progress."""
    pattern = re.compile(
        r"(?:明天|后天|下周|下次|董事会议|董事会|到时候|届时).{0,36}"
        r"(?:再|进一步)(?:具体)?(?:见面|聊|谈|讨论|分析|梳理|说明|明确|确认)|"
        r"(?:等|待).{0,24}(?:文件|材料|记录|结果|条款|流程).{0,12}(?:后|出来|好)"
        r".{0,12}(?:再|进一步)(?:具体)?(?:聊|谈|讨论|分析|梳理|说明|明确|确认)|"
        r"(?:见面).{0,12}(?:再|时).{0,12}(?:聊|谈|讨论|梳理|说明|明确|确认)|"
        r"(?:我会|我将).{0,18}(?:董事会议|董事会|会议).{0,18}"
        r"(?:提出|讨论|评估|协商|确认|重新评估)"
    )
    if not pattern.search(str(candidate)):
        return False
    prior = [
        str(item.get("text", ""))
        for item in history or []
        if item.get("role") == speaker
    ]
    return sum(bool(pattern.search(text)) for text in prior) >= 1


def evades_latest_disposition_request(candidate, latest_other_utterance):
    """Require an explicit accept/refuse answer to a current feasibility check."""
    latest = str(latest_other_utterance)
    asks_disposition = re.search(
        r"(?:你看.{0,12}(?:行吗|可行吗|可以吗)|"
        r"(?:这个|该|上述).{0,12}(?:行吗|可行吗|可以吗)|"
        r"(?:是否|能否|可否).{0,10}(?:接受|同意|认可|可行))",
        latest,
    )
    if not asks_disposition:
        return False
    text = str(candidate).strip()
    answer = re.search(
        r"^(?:那)?(?:我)?(?:同意|接受|认可|不同意|不接受|拒绝|可以|不行|无法确认|不能确认|暂不确认|暂时无法确认)|"
        r"^(?:那)?(?:好|行)[，,]?|"
        r"^(?:那)?[^。！？；]{0,32}(?:按|照)(?:你说的|这个|该|上述)?[^。！？；]{0,20}(?:执行|来|办|走)|"
        r"^(?:那好[，,]?)?(?:我们)?就先确认[^。！？；]{0,28}"
        r"(?:这个|该)?(?:数字|节点|安排)|"
        r"^(?:那)?[^。！？；]{0,20}(?:节点|安排|方案|金额)"
        r"[^。！？；]{0,6}(?:可以|可行|没问题|同意|接受|认可|不行|不能接受)",
        text,
    )
    asks_the_proposer_again = re.search(
        r"(?:你觉得|你认为|你看|是否|能否|可否).{0,16}"
        r"(?:行吗|可以吗|可行吗|接受|同意|认可|可行)|"
        r"(?:行吗|可以吗|可行吗)[？?]?",
        text,
    )
    cannot_confirm = re.search(
        r"^[^。！？；]{0,32}(?:我)?(?:暂时)?(?:无法|不能|不予)确认", text
    )
    question_like = re.search(
        r"[？?]|(?:你能|能否|是否|可否|你觉得|你认为|你看)", text
    )
    first_clause_disposition = re.search(
        r"^(?:(?:那)?(?:我)?(?:同意|接受|认可|不同意|不接受|拒绝|可以|不行|"
        r"无法确认|不能确认|暂不确认|暂时无法确认)|"
        r"[^。！？；]{0,24}我(?:暂时)?(?:同意|接受|认可|不同意|不接受|拒绝|"
        r"无法确认|不能确认)|(?:那)?(?:好|行)[，,]?)",
        text,
    )
    explicit_disposition = re.search(
        r"^(?:那)?(?:我)?(?:同意|接受|认可|不同意|不接受|拒绝|可以|不行|无法确认|不能确认|暂不确认|暂时无法确认)|"
        r"^(?:那)?(?:好|行)[，,]?|"
        r"^(?:那)?[^。！？；]{0,32}(?:按|照)(?:你说的|这个|该|上述)?"
        r"[^。！？；]{0,20}(?:执行|来|办|走)|"
        r"^(?:那好[，,]?)?(?:我们)?就先确认",
        text,
    )
    if question_like and not (first_clause_disposition or cannot_confirm):
        return True
    if asks_the_proposer_again and not (explicit_disposition or cannot_confirm):
        return True
    return not bool(answer or cannot_confirm)


def evades_latest_open_proposal(candidate, latest_proposal):
    """Reject asking for the same decision again instead of disposing an open proposal."""
    text = str(candidate).strip()
    proposal = str(latest_proposal).strip()
    if not proposal:
        return False
    disposition = re.search(
        r"^(?:那)?(?:我)?(?:同意|接受|认可|不同意|不接受|拒绝|可以|不行|无法确认|不能确认|暂不确认|暂时无法确认)|"
        r"(?:只能算|只是|仍是|还只是|不算|不能作为|尚未成为).{0,16}"
        r"(?:初步|意向|方案|安排|承诺|约定)|"
        r"(?:先暂停|暂不接受|暂时不接受|先保留|暂不确定|稍后再谈)",
        text,
    )
    if disposition:
        return False
    return bool(re.search(
        r"(?:请|能否|是否|可否|你能|你愿意|你觉得|你看|[？?])", text
    ))


def directly_answers_latest_proposal(candidate, latest_other_utterance):
    """Allow one plain accept/refuse move even when its topic is saturated."""
    latest = str(latest_other_utterance)
    text = str(candidate).strip()
    offered = re.search(
        r"(?:我建议|我提议|可以|可考虑|不如|要不要|是否愿意|是否可以|"
        r"你若同意|你如果同意)",
        latest,
    )
    disposition = re.search(
        r"^(?:那)?(?:我)?(?:同意|接受|认可|不同意|不接受|拒绝|可以|不行|无法确认|不能确认|暂不确认|暂时无法确认)",
        text,
    )
    adds_condition = re.search(
        r"(?:但|不过|只是|前提|如果|若|除非|要求|需要|能否|是否|[？?])",
        text,
    )
    return bool(offered and disposition and not adds_condition)

def repeats_saturated_goal_focus(candidate, ledger):
    """Reject candidates whose strongest evidence remains in saturated goals."""
    scores = _candidate_focus_scores(candidate)
    if not scores:
        return False
    status_by_focus = {}
    for item in (ledger or {}).get("goal_threads", []):
        focus = _candidate_focus(item.get("text", ""))
        if focus:
            status_by_focus.setdefault(focus, []).append(item.get("status", "open"))
    saturated_scores = [
        score for focus, score in scores.items()
        if focus in status_by_focus
        and all(status == "saturated" for status in status_by_focus[focus])
    ]
    available_scores = [
        score for focus, score in scores.items()
        if focus in status_by_focus
        and any(status != "saturated" for status in status_by_focus[focus])
    ]
    if not saturated_scores:
        return False
    return not available_scores or (
        max(available_scores) < 2
        and max(available_scores) < max(saturated_scores)
    )


def opens_followup_on_saturated_focus(candidate, ledger):
    return bool(re.search(r"[？?]", str(candidate))) and repeats_saturated_goal_focus(
        candidate, ledger
    )


def copies_goal_thread_label(candidate, ledger):
    """Reject prompt-facing output that prefixes a deterministic goal label."""
    text = str(candidate).strip()
    return any(
        label and re.match(rf"^{re.escape(label)}[：:。；]", text)
        for label in (
            str(item.get("text", "")).strip()
            for item in (ledger or {}).get("goal_threads", [])
        )
    )


def collapses_multiple_facets_early(candidate, turn_number):
    """Reject an early all-at-once settlement across three or more public facets."""
    if int(turn_number) > 5:
        return False
    scores = _candidate_focus_scores(candidate)
    if len(scores) < 3:
        return False
    return bool(re.search(
        r"(?:到此为止|彻底翻篇|定死|界限已定|就这么定|"
        r"按.{0,12}(?:安排|约定|界限|边界).{0,8}(?:办|执行|来)|"
        r"不再.{0,10}(?:提|涉及|往来)|只谈.{0,8}不谈)",
        str(candidate),
    ))


def goal_thread_constraints(ledger):
    """Build compact deterministic guidance from public goal-thread status only."""
    threads = list((ledger or {}).get("goal_threads", []))
    available = sorted(
        (item for item in threads if item.get("status", "open") != "saturated"),
        key=lambda item: (
            int(item.get("discussion_rounds", 0)),
            0 if item.get("status", "open") == "open" else 1,
            str(item.get("id", "")),
        ),
    )
    saturated = [item for item in threads if item.get("status") == "saturated"]
    return {
        "available_existing_facets": [item.get("text", "") for item in available],
        "saturated_facets": [item.get("text", "") for item in saturated],
        "instruction": (
            "If no direct answer is owed, make the next substantive move through one "
            "available existing facet. Do not mention a saturated facet merely as a "
            "bridge. This does not authorize a new event, fact, condition, or artifact."
        ),
    }


_AVAILABLE_THREAD_EVIDENCE_RULES = (
    (r"(?:首期|金额|数额)", r"(?:金额|多少|首期|第一期|(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)\s*(?:元|块|千|万|成|%))"),
    (r"(?:现实困难|资金困难|经济困难|延期原因)", r"(?:困难|手头紧|收入|工资|资金|负担|宽裕|周转|原因)"),
    (r"(?:分期|节奏|后续归还)", r"(?:分期|每月|每周|后续|之后|第二期|余款|下个月|年底|剩下)"),
    (r"(?:有变|变化).{0,8}(?:沟通|说明|告知)|沟通.{0,8}(?:变化|安排)", r"(?:有变|变化|提前|通知|告诉|说明|沟通|联系)"),
    (r"(?:信任|关系受损)", r"(?:信任|失望|失约|朋友|友谊|伤害|诚意|道歉|体谅)"),
    (r"(?:经济往来|新的借款|暂停借)", r"(?:经济往来|金钱往来|不再借|不会再借|停止借款|暂停借款|以后不借|新的借款)"),
    (r"(?:关系边界|相处边界)", r"(?:关系|边界|界限|相处|联系|不再提|不打扰)"),
    (r"(?:还款安排|归还安排)", r"(?:还款|还钱|还你|先还|能还|归还|转账|款项|金额|日期|期限|月底|分期)"),
    (r"(?:稀释过程|稀释决策)", r"(?:稀释|融资|股权变化|持股比例)"),
    (r"(?:合理权益|法律权益)", r"(?:权益|权利|持股比例|经济补偿|股权补偿)"),
    (r"(?:过去伤害)", r"(?:过去|伤害|背叛|排除|运营款|共同经历|朋友)"),
    (r"(?:未来合作|合作关系)", r"(?:未来合作|继续合作|合作关系|关系重建|重建合作)"),
    (r"(?:授权链)", r"(?:授权|签署|口头约定|共同确认)"),
    (r"(?:治理角色)", r"(?:治理|董事|席位|提名|决策权|执行权|否决权|咨询权|意见权)"),
    (r"(?:经济补偿)", r"(?:经济补偿|现金补偿|股权补偿|权益.{0,8}补偿|补偿方式|持股比例|期权)"),
)


def _candidate_advances_available_thread(candidate, ledger):
    value = str(candidate)
    for item in (ledger or {}).get("goal_threads", []):
        if (
            item.get("status", "open") == "saturated"
            or int(item.get("discussion_rounds", 0)) > 0
        ):
            continue
        label = str(item.get("text", ""))
        matched_rule = False
        for label_pattern, evidence_pattern in _AVAILABLE_THREAD_EVIDENCE_RULES:
            if not re.search(label_pattern, label):
                continue
            matched_rule = True
            if re.search(evidence_pattern, value):
                return True
        if matched_rule:
            continue
        label_compact = re.sub(r"[^\u4e00-\u9fff]", "", label)
        stop_anchors = {
            "同时", "并且", "双方", "合理", "明确", "具体", "如何",
            "提出", "要求", "讨论", "处理", "当前", "进行", "形成",
            "争取", "保护", "避免", "决定", "方案", "路径", "安排",
        }
        anchors = {
            label_compact[index:index + 2]
            for index in range(max(0, len(label_compact) - 1))
            if label_compact[index:index + 2] not in stop_anchors
        }
        if any(anchor in value for anchor in anchors):
            return True
    return False


def opens_future_cycle_on_final_turn(candidate, turn_number):
    """The exact horizon must close without creating another off-screen cycle."""
    if int(turn_number) != 20:
        return False
    text = str(candidate)
    standing_boundary = re.search(
        r"(?:未来|以后|将来).{0,16}(?:经济请求|借钱|借款).{0,18}"
        r"(?:直接拒绝|拒绝|不接受|不再借)", text,
    )
    scheduled_process = re.search(
        r"(?:下周|下月|下个月|月底|月初|之后|后续|到时候|届时|下次|"
        r"等[^。！？；]{0,16}(?:时|后)).{0,24}"
        r"(?:再|会|将|联系|沟通|确认|讨论|安排|落实|处理|发(?:个)?消息|"
        r"回复|回应|问候|打招呼)", text,
    )
    if standing_boundary and not scheduled_process:
        return False
    return bool(re.search(
        r"(?:下周|下月|下个月|月底|月初|之后|后续|到时候|届时|下次|"
        r"等[^。！？；]{0,16}(?:时|后)).{0,24}"
        r"(?:再|会|将|联系|沟通|确认|讨论|安排|落实|处理|发(?:个)?消息|"
        r"回复|回应|问候|打招呼)|"
        r"(?:再|会|将).{0,20}(?:联系|沟通|确认|讨论|安排|落实|处理)",
        text,
    ))


def premature_closure_with_untouched_goals(candidate, ledger, turn_number):
    """Reject ending the exchange while a public facet has no substantive answer."""
    if int(turn_number) >= 18:
        return False
    text = str(candidate)
    closure = re.search(
        r"(?:(?:各自.{0,10}(?:专注|处理|忙)|(?:专注|处理)各自)|不再(?:主动)?提|到此为止|"
        r"就按.{0,16}(?:执行|推进|处理)|等.{0,24}(?:再确认|再谈|再说|后再)|"
        r"先这样|这件事就这样)",
        text,
    )
    if not closure:
        return False
    untouched = [
        item
        for item in (ledger or {}).get("goal_threads", [])
        if item.get("status", "open") != "saturated"
        and int(item.get("discussion_rounds", 0)) == 0
    ]
    return bool(
        untouched
        and not _candidate_advances_available_thread(
            text, {"goal_threads": untouched}
        )
    )


def repeats_stalled_focus(candidate, ledger, max_utterances=4):
    progress = (ledger or {}).get("progress", {})
    focus = _candidate_focus(candidate)
    return bool(
        focus
        and focus == progress.get("current_focus")
        and int(progress.get("consecutive_focus_utterances", 0)) >= max_utterances
        and not _candidate_advances_available_thread(candidate, ledger)
    )


def claims_pending_commitment_completed(candidate, ledger):
    """Reject claiming settlement while an observable matching promise is pending."""
    text = str(candidate)
    if not re.search(
        r"(?:两清|互不相欠|(?:借款|欠款|债务|账目|这笔钱).{0,10}"
        r"(?:已)?(?:结清|还清|归还完|全部解决)|(?:款项|钱|转账).{0,8}"
        r"(?:已)?到账|(?:\d+|[一二两三四五六七八九十百千万]+)\s*块.{0,8}"
        r"(?:收到|到账)|(?:收到|到账).{0,8}(?:\d+|[一二两三四五六七八九十百千万]+)\s*块|"
        r"经济往来.{0,12}(?:彻底)?翻篇)",
        text,
    ):
        return False
    candidate_focus = _candidate_focus(text)
    economic_closure = bool(re.search(r"经济往来.{0,12}(?:彻底)?翻篇", text))
    return any(
        item.get("status") == "pending"
        and (
            economic_closure
            and _candidate_focus(item.get("object") or item.get("text", ""))
            == "practical_execution"
            or not candidate_focus
            or _candidate_focus(item.get("object") or item.get("text", ""))
            in {None, candidate_focus}
        )
        for item in (ledger or {}).get("commitments", [])
    )


def prematurely_reports_future_commitment_completion(
    candidate, ledger, speaker, public_record_text="",
):
    """Reject future/off-screen promises becoming complete without an event."""
    text = str(candidate)
    completion_pattern = re.compile(
        r"(?:已经|刚刚|现已|已)(?:经)?[^。！？；]{0,24}"
        r"(?:完成|整理|发送|发出|提交|上传|更新|附在|附上|准备好|签署)|"
        r"(?:完成|整理|发送|发出|提交|上传|更新|准备|签署)(?:完|好了)"
    )
    if not completion_pattern.search(text):
        return False
    if public_record_text:
        public_normalized = normalize_text(public_record_text)
        unsupported_clauses = []
        for clause in re.split(r"[，,。！？；;]", text):
            clause = clause.strip()
            if not clause:
                continue
            normalized_clause = normalize_text(clause)
            if (
                completion_pattern.search(clause)
                and len(normalized_clause) >= 4
                and normalized_clause in public_normalized
            ):
                continue
            unsupported_clauses.append(clause)
        text = "。".join(unsupported_clauses)
        if not completion_pattern.search(text):
            return False
    future_pattern = re.compile(
        r"(?:明天|后天|下周|下月|下个月|月底|稍后|之后|届时|到时候|"
        r"\d+\s*号|[一二两三四五六七八九十]+点前|会议前|"
        r"(?:\d+|[一二两三四五六七八九十]+)\s*(?:分钟|小时|天)(?:后|内)|"
        r"(?:今日|今天|本日|本周)内)"
    )
    candidate_focus = _candidate_focus(text)
    candidate_grams = _bigrams(text)
    stop_grams = {
        "我会", "我将", "已经", "现已", "完成", "整理", "发送",
        "提交", "更新", "确认", "可以", "目前", "需要", "进行",
    }
    for item in (ledger or {}).get("commitments", []):
        if item.get("speaker") != speaker or item.get("status") != "pending":
            continue
        promised = " ".join((
            str(item.get("text", "")),
            str(item.get("object", "")),
            str(item.get("context", "")),
        ))
        terms = " ".join(map(str, item.get("terms", [])))
        offscreen_work = re.search(
            r"(?:整理|发送|提供|准备|提交|上传|更新|附上|签署|转账|付款|"
            r"协调|召开|联系|核验|查阅)",
            str(item.get("object") or item.get("text", "")),
        )
        if not (future_pattern.search(promised + " " + terms) or offscreen_work):
            continue
        promised_focus = item.get("focus") or _candidate_focus(promised)
        shared = (candidate_grams & _bigrams(promised)) - stop_grams
        if (candidate_focus and candidate_focus == promised_focus) or shared:
            return True
    return False


def lacks_natural_final_closure(candidate, turn_number):
    """Require a 20-turn budget boundary to end with a decision or explicit stop."""
    if int(turn_number) != 20:
        return False
    text = str(candidate).strip()
    terminal = re.search(
        r"(?:今天|这次|这件事|这个问题).{0,12}(?:先)?(?:谈到这里|到这里|结束)|"
        r"(?:到此为止|保留分歧|没有共识|无法同意|不能接受|不接受|"
        r"我接受|我同意|我的决定是|结论是|不再继续|暂不合作|结束讨论|"
        r"(?:那|好)?(?:我们)?就按(?:这个|这种|现在的).{0,24}(?:方式|节奏|频率|边界|安排)(?:来|保持|相处)?|"
        r"(?:那|就)?先这样|"
        r"各自安好|最终的(?:状态|定位)|安顿在(?:现在|这个).{0,4}位置|"
        r"更像.{0,10}(?:普通朋友|熟人|陌生人)|"
        r"(?:未来|以后|将来).{0,16}(?:经济请求|借钱|借款).{0,18}"
        r"(?:直接拒绝|拒绝|不接受|不再借))",
        text,
    )
    if not terminal:
        return True
    return bool(re.search(
        r"(?:是否|能否|如何|怎么|什么|哪(?:个|一)|吗[？?]?|[？?])|"
        r"(?:之后|后续|下周|届时|到时候).{0,18}(?:再|会|将|讨论|确认|协商)",
        text,
    ))


def overloads_consequential_terms(candidate, turn_number):
    """Keep negotiation to one bounded consequential dimension per move."""
    text = str(candidate)
    numeric_terms = re.findall(
        r"\d+(?:\.\d+)?\s*[:：]\s*\d+(?:\.\d+)?|"
        r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)"
        r"\s*(?:元|块|千|万|亿|%|年|个月|月|季度)",
        text,
    )
    rights = {
        name for name, pattern in (
            ("veto", r"否决权"),
            ("board", r"董事(?:会)?席位|董事提名权"),
            ("consultation", r"咨询权"),
            ("approval", r"审批权|联合审批权"),
            ("information", r"知情权"),
            ("dividend", r"优先分红权"),
            ("convertible", r"可转换债券|可转债"),
            ("option", r"期权(?:池|调整)"),
            ("vesting", r"行权期|成熟期"),
            ("kpi", r"KPI|绩效审核"),
        )
        if re.search(pattern, text, re.IGNORECASE)
    }
    return len(numeric_terms) > 2 or (
        int(turn_number) <= 5
        and (len(numeric_terms) > 1 or len(rights) > 2)
    )


def evades_explicit_amount_question(candidate, latest_action):
    """Reject silently moving past a direct request for a concrete amount."""
    question = str(latest_action)
    if re.search(
        r"(?:你|您).{0,12}(?:心里)?有(?:个)?(?:数|金额)吗|"
        r"(?:你|您).{0,12}(?:实际)?能还多少",
        str(candidate),
    ):
        return False
    if re.search(
        r"(?:怎么|如何).{0,18}(?:通知|告知|说明|沟通|联系|更新)|"
        r"(?:通知|告知|说明|沟通|联系|更新).{0,18}(?:怎么|如何)",
        question,
    ):
        return False
    amount_topic = r"(?:多少|金额|数额|底数|具体数字|这个数)"
    if not re.search(amount_topic, question):
        return False
    monetary_context = re.search(
        r"(?:还款|还钱|能还|愿意还|打算还|欠款|债务|款项|这笔钱|"
        r"金额|数额|底数|具体数字|几\s*(?:元|块|千|万)|"
        r"\d+(?:\.\d+)?\s*(?:元|块|千|万))",
        question,
    )
    if not monetary_context:
        return False
    explicit_request = (
        (
            re.search(r"多少|几\s*(?:元|块|千|万)", question)
            and re.search(r"[？?]", question)
        )
        or re.search(
            r"(?:你|您).{0,24}(?:(?:实际)?能还多少|(?:打算|可以|愿意)还多少|"
            r"能承担多少|(?:能否|是否可以|愿不愿意).{0,10}(?:给出|确定|说明)"
            r".{0,8}(?:金额|数额|数字|底数))",
            question,
        )
        or re.search(rf"(?:请|告诉我|明确给出).{{0,24}}{amount_topic}", question)
        or re.search(rf"{amount_topic}.{{0,16}}(?:告诉我|能否|可以吗|行吗)", question)
    )
    if not explicit_request:
        return False
    answer = str(candidate)
    if re.search(
        r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)\s*(?:元|块|千|万)",
        answer,
    ):
        return False
    explicit_inability = re.search(
        r"(?:无法|不能|没法|给不出|不确定|说不准|尚未确定|还未确定|"
        r"暂时没有).{0,16}(?:金额|数额|数字|底数|能还多少)|"
        r"(?:金额|数额|数字|底数).{0,12}(?:无法|不能|没法|给不出|不确定|说不准)",
        answer,
    )
    return not bool(explicit_inability)


def upgrades_tentative_to_agreement(candidate, latest_other_utterance):
    """Reject converting the other speaker's tentative move into an agreement."""
    source = str(latest_other_utterance)
    text = str(candidate)
    tentative = re.search(
        r"(?:尽力|争取|尝试|初步(?:考虑|意向|估算)|仍需.{0,8}调整|"
        r"要看|取决于|暂时不能确定)",
        source,
    )
    incomplete_repayment = (
        re.search(
            r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)\s*"
            r"(?:元|块|千|万)",
            source,
        )
        and re.search(
            r"(?:今天|明天|后天|本周|下周|本月|下月|月底|月初|"
            r"(?:\d+|[一二两三四五六七八九十]+)\s*(?:小时|天)(?:后|内))",
            source,
        )
        and not re.search(
            r"(?:能还|会还|可以还|可还|还给|还款|还钱|还你|还清|偿还|归还|"
            r"转账|转出|汇款|付款|支付)",
            source,
        )
    )
    if not tentative and not incomplete_repayment:
        return False
    source_accepts_arrangement = re.search(
        r"(?:我|我们)?(?:已经|已)?(?:认可|接受|同意).{0,18}"
        r"(?:暂停|边界|安排|方案|提议)",
        source,
    )
    candidate_accepts_arrangement = re.search(
        r"(?:我|我们)?(?:先)?(?:认可|接受|同意).{0,18}"
        r"(?:暂停|边界|安排|方案|提议)|"
        r"(?:暂停|边界|安排|方案|提议).{0,12}"
        r"(?:我|我们)?(?:先)?(?:认可|接受|同意)",
        text,
    )
    # Accepting an arrangement the other speaker explicitly accepted cannot
    # upgrade a separate tentative effort mentioned in the same utterance.
    if source_accepts_arrangement and candidate_accepts_arrangement:
        return False
    if re.search(
        r"(?:不算|不是|尚未|还没|没有).{0,12}(?:约定|共识|确定|确认|谈妥)|"
        r"(?:尚未|还没|没有).{0,12}(?:成为|形成).{0,6}(?:还款)?承诺|"
        r"(?:约定|共识).{0,8}(?:尚未|还没|没有)(?:形成|达成)|"
        r"(?:无法|不能).{0,10}(?:作为|算作)?.{0,10}(?:约定|共识)|"
        r"(?:而非|并非).{0,12}(?:约定|共识)|"
        r"不(?:认可|接受|同意).{0,14}(?:承诺|保证|安排|方案|约定)",
        text,
    ):
        return False
    return bool(re.search(
        r"(?:双方|我们).{0,10}(?:已经|已)?(?:确定|确认|约定|谈妥|达成共识)|"
        r"(?:已经|已)(?:确定|确认|约定|谈妥|达成共识)|"
        r"(?:按|照)(?:这个|该|上述|现在的)?(?:金额|数字|节点|期限)?"
        r".{0,8}(?:约定|安排)(?:执行|来|处理)|"
        r"(?:这个|该|上述)?(?:金额|数字|节点|期限|安排|方案).{0,8}"
        r"(?:我)?(?:先)?(?:认可|接受|同意)|"
        r"(?:我)?(?:先)?(?:认可|接受|同意).{0,8}"
        r"(?:这个|该|上述)?(?:金额|数字|节点|期限|安排|方案)|"
        r"(?:这次|上述|该|已经|已)(?:还款)?承诺|"
        r"已承诺的?\s*(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)\s*"
        r"(?:元|块|千|万)",
        text,
    ))


def rewrites_absent_commitment_as_nonperformance(candidate, evidence_text):
    """Keep 'no commitment formed' distinct from failure to perform one."""
    evidence = str(evidence_text)
    text = str(candidate)
    if not re.search(
        r"(?:没有|未|尚未).{0,16}(?:形成|存在).{0,16}(?:可核验的?)?"
        r"(?:还款)?(?:承诺|约定)|"
        r"没有可据此.{0,12}(?:判定|确认).{0,8}(?:履约|结果)",
        evidence,
    ):
        return False
    if re.search(
        r"(?:不能|不应|无法|谈不上|不等于|不可).{0,12}"
        r"(?:未履约|未履行|没履约|没履行|承诺未落地|约定未落地)",
        text,
    ):
        return False
    return bool(re.search(
        r"(?:承诺|约定).{0,16}(?:未|没有|没).{0,8}"
        r"(?:落地|履行|履约|兑现|完成)|"
        r"(?:第一笔|这笔|款项).{0,10}(?:未|没有|没).{0,8}"
        r"(?:落地|履行|履约|兑现|完成)|"
        r"(?:第一笔|这笔|款项).{0,16}(?:未能|没有|没).{0,8}"
        r"(?:到账|转入|转出)|"
        r"(?:前|过去).{0,12}(?:没有|未).{0,8}形成(?:实际)?还款|"
        r"(?:未|没有|没)(?:实际)?(?:履行|履约|兑现)|"
        r"(?:承诺|约定)(?:落空|违约)",
        text,
    ))


def commitment_evidence_status(evidence_text):
    """Return a compact status only when public wording is unambiguous."""
    text = str(evidence_text)
    if re.search(
        r"(?:没有|未|尚未).{0,16}(?:形成|存在).{0,16}(?:可核验的?)?"
        r"(?:还款)?(?:承诺|约定)|"
        r"没有可据此.{0,12}(?:判定|确认).{0,8}(?:履约|结果)",
        text,
    ):
        return "no_verifiable_commitment"
    if re.search(r"(?:部分履约|部分到账|只到账|仅到账)", text):
        return "partially_fulfilled_by_public_event"
    if re.search(r"(?:明确未履约|到期未履约|未按约履行|承诺未履行)", text):
        return "unfulfilled_by_public_event"
    if re.search(r"(?:已按约履行|已履约|足额到账|承诺已完成)", text):
        return "fulfilled_by_public_event"
    return ""


def current_repayment_commitment_status(ledger, public_timeline, latest_text=""):
    """Summarize the newest observable repayment-record status.

    Ledger evidence takes precedence over older transition records. Only
    practical repayment commitments participate, so a promise to send an
    update cannot erase a public ``precondition_not_met`` record.
    """
    direct = commitment_evidence_status(latest_text)
    if direct:
        return direct
    repayment = re.compile(
        r"(?:还款|还钱|还你|还清|偿还|归还|转账|转出|汇款|付款|支付|"
        r"还\s*(?=(?:\d|[一二两三四五六七八九十百千万])))"
    )
    amount = re.compile(
        r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)\s*"
        r"(?:元|块|千|万)"
    )
    deadline = re.compile(
        r"(?:今天|明天|后天|本周|下周|本月|下月|月底|月初|"
        r"(?:\d+|[一二两三四五六七八九十]+)\s*(?:小时|天)(?:后|内))"
    )
    status_map = {
        "pending": "pending_verifiable_commitment",
        "completed_by_public_event": "fulfilled_by_public_event",
        "partially_fulfilled_by_public_event": "partially_fulfilled_by_public_event",
        "unfulfilled_by_public_event": "unfulfilled_by_public_event",
    }
    for item in reversed((ledger or {}).get("commitments", [])):
        evidence = " ".join((
            str(item.get("object", "")), str(item.get("text", "")),
        ))
        if (
            item.get("focus") != "practical_execution"
            or not repayment.search(evidence)
            or not amount.search(evidence)
            or not deadline.search(evidence)
        ):
            continue
        mapped = status_map.get(item.get("status"))
        if mapped:
            return mapped
    for event in reversed(public_timeline or []):
        status = commitment_evidence_status(event.get("text", ""))
        if status:
            return status
    return ""


def suspends_existing_obligation(candidate):
    """Reject erasing an existing duty while allowing a pause in discussing it."""
    text = str(candidate)
    if re.search(
        r"(?:旧账|债务|经济责任|还款责任).{0,8}(?:仍然?|继续)?(?:存在|不变)|"
        r"(?:责任不变|义务不变)",
        text,
    ):
        return False
    if re.search(
        r"(?:暂不|先不|不再).{0,6}(?:讨论|追问|提起|沟通).{0,8}"
        r"(?:旧账|债务|经济责任|还款责任)|"
        r"(?:旧账|债务|经济责任|还款责任).{0,8}"
        r"(?:暂不|先不|不再).{0,6}(?:讨论|追问|提起|沟通)",
        text,
    ):
        return False
    return bool(re.search(
        r"(?:搁置|暂停|放下|免除|取消|不再处理|先不处理).{0,8}"
        r"(?:经济责任|债务责任|还款责任|旧账)|"
        r"(?:经济责任|债务责任|还款责任|旧账).{0,8}"
        r"(?:搁置|暂停|放下|免除|取消|不再处理|先不处理)|"
        r"(?:旧欠款|旧账|债务|还款责任).{0,36}"
        r"(?:留在过去|留给过去|翻篇|一笔勾销)|"
        r"(?:搁置|放下).{0,8}(?:经济(?:上的)?账|欠款|债务)|"
        r"(?:经济(?:上的)?账|旧账|欠款|债务).{0,16}(?:搁置|放下)",
        text,
    ))


def evades_latest_obligation(candidate, latest_action, latest_social_act):
    """Reject changing domains instead of answering the current request/question."""
    surface_request = re.search(
        r"(?:请(?:立即|立刻|同步|先|直接|具体)?(?:发送|提供|说明|确认|解释|告知|列出|明确|回答)|"
        r"能否|是否|可否|为什么|怎么|如何|哪(?:个|些|种|一)|谁|[？?])",
        str(latest_action),
    )
    if latest_social_act not in {"question", "request", "challenge"} and not surface_request:
        return False
    obligation_segments = [
        segment.strip()
        for segment in re.split(
            r"[。！？!?；]|(?<=[，,])(?=(?:那|那么|所以|因此|请问))",
            str(latest_action),
        )
        if segment.strip()
    ]
    obligation_segments = [
        segment for segment in obligation_segments
        if re.search(
            r"(?:请|能否|是否|可否|为什么|怎么|如何|哪(?:个|些|种|一)|谁|[？?])",
            segment,
        )
    ] or obligation_segments
    obligation_text = (
        obligation_segments[-1] if obligation_segments else str(latest_action)
    )
    action_focus = _candidate_focus(obligation_text)
    response_focus = _candidate_focus(candidate)
    if not action_focus or not response_focus:
        return False
    object_terms = re.compile(
        r"材料|文件|记录|摘要|草稿|授权链|流程|责任人|权限|补偿|"
        r"股权|权益|治理|参与权|还款|金额|日期|关系|合作"
    )
    if (
        set(object_terms.findall(obligation_text))
        & set(object_terms.findall(str(candidate)))
        and re.search(
            r"(?:^|[。；，,])(?:关于.{0,18}[，,])?.{0,12}"
            r"(?:可以|不需要|需要|不能|无法|没有|有|同意|不同意|拒绝)",
            str(candidate),
        )
    ):
        return False
    strict_request = re.search(
        r"请(?:立即|立刻|同步|先|直接|具体)?"
        r"(?:发送|提供|说明|确认|解释|告知|列出|明确|回答)",
        str(latest_action),
    )
    if strict_request and action_focus != response_focus:
        return True
    family = {
        "governance": "institutional", "equity": "institutional",
        "authorization": "institutional", "responsibility": "institutional",
        "artifact_workflow": "execution", "practical_execution": "execution",
        "trust_repair": "relationship", "communication_boundary": "relationship",
        "economic_boundary": "relationship",
    }
    return family.get(action_focus, action_focus) != family.get(response_focus, response_focus)


def bounces_latest_stance_request(candidate, latest_utterance):
    """Reject immediately returning a request for one's own stance to the asker."""
    latest = str(latest_utterance)
    text = str(candidate)
    asks_for_stance = re.compile(
        r"(?:你认为|你希望|你的(?:方案|立场|要求|选择)|你能接受|你倾向)"
    )
    if not (asks_for_stance.search(latest) and asks_for_stance.search(text)):
        return False
    if re.search(
        r"(?:我的(?:方案|立场|要求|选择)是|我认为|我希望|我要求|"
        r"我能接受|我倾向|我不同意|我接受)",
        text,
    ):
        return False
    return True


def follows_latest_invited_scope(candidate, latest_utterance):
    """Allow one follow-up only when the proposal explicitly invited that facet."""
    latest = str(latest_utterance)
    text = str(candidate)
    if not re.search(r"(?:同步讨论|例如|是否希望|希望优先|哪(?:一|个|项))", latest):
        return False
    bounded_terms = re.compile(
        r"(?:百分之[一二两三四五六七八九十百]+|\d+(?:\.\d+)?\s*(?:%|元|万|天|日)|"
        r"每(?:季度|月|周)|季度|咨询权|决策权|审议权|表决权|否决权|"
        r"建议书|文件|材料|协议)"
    )
    latest_terms = set(bounded_terms.findall(latest))
    if any(term not in latest_terms for term in bounded_terms.findall(text)):
        return False
    domains = (
        r"未来合作|合作边界|继续合作|终止合作|参与(?:特定|具体)?项目",
        r"治理|咨询权|决策权|审议权|表决权|董事|项目参与",
        r"经济补偿|一次性补偿|阶段性补偿|股权回购|补偿方式",
    )
    return any(
        re.search(pattern, latest) and re.search(pattern, text)
        for pattern in domains
    )


def introduces_unrequested_artifact(candidate, observable_text):
    """Reject a new write/send/check artifact workflow absent from public context."""
    text = str(candidate)
    artifact_move = re.search(
        r"(?:(?:写|整理|准备|发送|发|提交|提供|补充|草拟|拟定).{0,12}"
        r"(?:书面|文档|文件|材料|报告|表格|清单|记录|草稿|备忘录|模板|计划)|"
        r"(?:书面|文档|文件|材料|报告|表格|清单|记录|草稿|备忘录|模板)"
        r".{0,12}(?:确认|发送|提交|补充|签))",
        text,
    )
    if not artifact_move:
        return False
    observed = str(observable_text)
    return not re.search(
        r"(?:书面|文档|文件|材料|报告|表格|清单|记录|草稿|备忘录|模板|"
        r"写.{0,6}计划|发.{0,6}计划)",
        observed,
    )


def _declarative_evidence_text(public_context):
    """Drop questions/proposals that cannot ground a later asserted fact."""
    clauses = re.split(r"[。！？!?；\n]", str(public_context))
    return " ".join(
        clause for clause in clauses
        if clause.strip()
        and not re.search(r"(?:是否|能否|可否|什么|哪(?:个|一)|如何|怎么|吗)", clause)
        and not re.search(r"(?:建议|提议|可以考虑|可设定|希望|假设|如果|若)", clause)
    )


def _assertive_claim_clauses(text, pattern):
    """Return matched factual clauses without laundering via a later proposal."""
    clauses = re.split(
        r"[。！？!?；]|(?:但是|但|不过)|"
        r"[，,](?=[^，,。！？!?；]{0,16}(?:我|我们)(?:会|将|可以|能|稍后|之后|随后|届时))",
        str(text),
    )
    nonfactual = re.compile(
        r"(?:能否|可否|吗|无法确认|不能确认|尚不清楚|"
        r"可以考虑|可设定|假设|如果|若)"
    )
    return [
        clause for clause in clauses
        if re.search(pattern, clause)
        and not nonfactual.search(clause)
        and not (
            re.search(r"是否", clause)
            and not re.search(
                r"(?:明确|显示|表明|确认|说明).{0,6}(?:你)?是否", clause
            )
        )
        and not re.match(r"\s*(?:我|我们)(?:建议|提议|要求|主张)", clause)
    ]


def asserts_ungrounded_institutional_procedure(candidate, public_context):
    """Reject excessive or high-specificity institutional invention.

    One unnamed, nonnumeric, low-specificity plausible elaboration is allowed per
    utterance. Exact records, rules, actors, rounds, locations, or multiple new
    factual clauses still require declarative observable evidence.
    """
    text = str(candidate)
    authored = _declarative_evidence_text(public_context)
    if not re.search(r"(?:假设|假如|如果|若)", text):
        for exact_reference in (
            r"投决会", r"法律顾问", r"合规调取", r"审批责任人",
            r"权限范围", r"口头约定",
        ):
            if re.search(exact_reference, text) and not re.search(
                exact_reference, authored
            ):
                return True
    unsupported = set()
    generic_pattern = (
        r"(?:根据|按照|按).{0,16}(?:协议|条款|章程).{0,24}"
        r"(?:均需|必须|已经|已|由|未|没有|允许|规定|执行|主导)|"
        r"(?:协议|条款|章程)(?:中|里|下|内|框架内).{0,24}"
        r"(?:赋予|规定|要求|允许|未赋予|没有|执行|主导|生效|包含|存在|明确|设置)|"
        r"关键步骤(?:包括|指|是)|"
        r"(?:文件|邮件记录|系统记录|会议纪要|存档记录).{0,12}"
        r"(?:显示|表明|确认|记载)|"
        r"(?:董事会决议|工商变更|投后文件).{0,18}"
        r"(?:通过|签署|备案|确认|完成)|"
        r"(?:治理角色|治理调整).{0,18}(?:需要|需|必须).{0,18}"
        r"(?:董事会|投资人会议|章程|协议)|"
        r"(?:协议|条款|章程).{0,4}(?:要求|规定).{0,24}"
        r"(?:董事会|签署|确认|表决|授权)"
    )
    generic_evidence = (
        r"(?:协议|条款|章程).{0,24}(?:规定|要求|允许|赋予|未赋予|包含|存在|明确|设置)|"
        r"(?:文件|邮件记录|系统记录|会议纪要|存档记录).{0,12}(?:显示|表明|确认|记载)|"
        r"关键步骤(?:包括|指|是)|"
        r"(?:董事会决议|工商变更|投后文件).{0,18}(?:通过|签署|备案|确认|完成)|"
        r"(?:治理角色|治理调整).{0,18}(?:需要|需|必须).{0,18}"
        r"(?:董事会|投资人会议|章程|协议)|"
        r"(?:协议|条款|章程).{0,4}(?:要求|规定).{0,24}"
        r"(?:董事会|签署|确认|表决|授权)"
    )
    if not re.search(generic_evidence, authored):
        unsupported.update(
            normalize_text(clause)
            for clause in _assertive_claim_clauses(text, generic_pattern)
        )

    detail_rules = (
        (r"初始协议", r"初始协议"),
        (r"最早.{0,6}授权文件", r"最早.{0,6}授权文件"),
        (r"由.{1,16}(?:签署|拟定)", r"由.{1,16}(?:签署|拟定)"),
        (r"(?:决策依据|签署人)(?:是|为)", r"(?:决策依据|签署人)(?:是|为)"),
        (r"(?:这次)?(?:稀释|股权调整).{0,24}(?:由.{0,8}发起|通过.{0,14}完成|目的是|为了)", r"(?:这次)?(?:稀释|股权调整).{0,24}(?:由.{0,8}发起|通过.{0,14}完成|目的是|为了)"),
        (r"(?:没有|未)经过.{0,6}(?:你|双方|共同)?确认", r"(?:没有|未)经过.{0,6}(?:你|双方|共同)?确认"),
        (r"(?:稀释过程|融资).{0,14}(?:涉及)?[一二两三四五六七八九十\d]+轮", r"(?:稀释过程|融资).{0,14}(?:涉及)?[一二两三四五六七八九十\d]+轮"),
        (r"(?:每次|创始团队|团队内部).{0,18}(?:口头)?投票", r"(?:每次|创始团队|团队内部).{0,18}(?:口头)?投票"),
        (r"(?:决策|稀释).{0,16}基于.{0,18}(?:投票|投资人协议)", r"(?:决策|稀释).{0,16}基于.{0,18}(?:投票|投资人协议)"),
        (r"稀释过程中.{0,18}(?:没有|未).{0,12}(?:评估|考虑)", r"稀释过程中.{0,18}(?:没有|未).{0,12}(?:评估|考虑)"),
        (r"(?:从|在)法律文件中.{0,10}(?:找到|有|存在).{0,6}依据", r"(?:从|在)法律文件中.{0,10}(?:找到|有|存在).{0,6}依据"),
        (r"融资协议", r"融资协议"),
        (r"投资人协议", r"投资人协议"),
        (r"投资协议", r"投资协议"),
        (r"(?:所有|相关)?(?:融资)?条款.{0,18}(?:经过|由|通过).{0,24}(?:敲定|签署|确定|确认)", r"(?:所有|相关)?(?:融资)?条款.{0,18}(?:经过|由|通过).{0,24}(?:敲定|签署|确定|确认)"),
        (r"(?:未|没有|并未).{0,12}(?:设|设置|经过|要求).{0,16}(?:董事会)?(?:授权|表决|流程|签字|同意)", r"(?:未|没有|并未).{0,12}(?:设|设置|经过|要求).{0,16}(?:董事会)?(?:授权|表决|流程|签字|同意)"),
        (r"(?:邮件|投资协议).{0,16}(?:敲定|签署|确认|记载)", r"(?:邮件|投资协议).{0,16}(?:敲定|签署|确认|记载)"),
        (r"(?:目前)?(?:没有|无).{0,8}(?:新)?(?:文件|事实).{0,12}支持", r"(?:目前)?(?:没有|无).{0,8}(?:新)?(?:文件|事实).{0,12}支持"),
        (r"(?:每次|各轮)?融资.{0,14}(?:有|存在|经过).{0,14}董事会决议", r"(?:每次|各轮)?融资.{0,14}(?:有|存在|经过).{0,14}董事会决议"),
        (r"(?:治理角色|治理权|知情权|决策权).{0,18}(?:应|需|必须|可|可以).{0,18}(?:基于|通过|由).{0,16}(?:协议|董事会决议|贡献)", r"(?:治理角色|治理权|知情权|决策权).{0,18}(?:应|需|必须|可|可以).{0,18}(?:基于|通过|由).{0,16}(?:协议|董事会决议|贡献)"),
        (r"(?:最终|相关)?决策.{0,12}(?:仍)?由.{0,12}董事会(?:作出|决定|表决)", r"(?:最终|相关)?决策.{0,12}(?:仍)?由.{0,12}董事会(?:作出|决定|表决)"),
        (r"(?:具体安排|具体条款|执行方式)(?:是|为|包括)", r"(?:具体安排|具体条款|执行方式)(?:是|为|包括)"),
        (r"(?:每个季度|董事会前).{0,24}(?:提交|通报|提供).{0,24}(?:建议书|结果|摘要)", r"(?:每个季度|董事会前).{0,24}(?:提交|通报|提供).{0,24}(?:建议书|结果|摘要)"),
        (r"(?:每次|各轮)?融资.{0,18}授权链.{0,18}(?:涉及|包括).{0,18}(?:董事会|投资条款)", r"(?:每次|各轮)?融资.{0,18}授权链.{0,18}(?:涉及|包括).{0,18}(?:董事会|投资条款)"),
        (r"(?:你|早期合伙人).{0,10}(?:可以|可).{0,16}(?:保留|拥有).{0,36}(?:董事会席位|否决权|审批权|知情权)", r"(?:你|早期合伙人).{0,10}(?:可以|可).{0,16}(?:保留|拥有).{0,36}(?:董事会席位|否决权|审批权|知情权)"),
        (r"(?:具体|当前|目前)?治理安排.{0,16}(?:基于|依据).{0,20}(?:投资人要求|董事会决议|章程|协议)", r"(?:具体|当前|目前)?治理安排.{0,16}(?:基于|依据).{0,20}(?:投资人要求|董事会决议|章程|协议)"),
        (r"(?:补充协议|动议).{0,24}(?:通常|需要|需|必须|符合).{0,24}(?:章程|协议|议事规则)", r"(?:补充协议|动议).{0,24}(?:通常|需要|需|必须|符合).{0,24}(?:章程|协议|议事规则)"),
        (r"股东协议中.{0,10}一致行动人条款", r"股东协议中.{0,10}一致行动人条款"),
        (r"(?:早期合伙人).{0,16}(?:通常|一般).{0,12}(?:保留|拥有).{0,20}(?:权益|权利)", r"(?:早期合伙人).{0,16}(?:通常|一般).{0,12}(?:保留|拥有).{0,20}(?:权益|权利)"),
        (r"投资人席位.{0,8}(?:已)?占多数", r"投资人席位.{0,8}(?:已)?占多数"),
        (r"(?:文件|股东协议|条款清单|授权记录).{0,20}(?:会|将|能够|可以).{0,20}(?:明确|显示).{0,20}(?:否决权|审批权|权益|决策权)", r"(?:文件|股东协议|条款清单|授权记录).{0,20}(?:会|将|能够|可以).{0,20}(?:明确|显示).{0,20}(?:否决权|审批权|权益|决策权)"),
        (r"融资结构.{0,12}(?:已成定局|已经确定|无法.{0,8}重新定义)", r"融资结构.{0,12}(?:已成定局|已经确定|无法.{0,8}重新定义)"),
        (r"(?:你|早期合伙人).{0,10}(?:可以|可).{0,24}(?:参与|推荐).{0,24}(?:产品战略|预算|人事|岗位|人选)", r"(?:你|早期合伙人).{0,10}(?:可以|可).{0,24}(?:参与|推荐).{0,24}(?:产品战略|预算|人事|岗位|人选)"),
        (r"(?:融资条款|最终决策权|最终任命).{0,18}(?:仍)?由董事会(?:保留|决定|审议|作出)", r"(?:融资条款|最终决策权|最终任命).{0,18}(?:仍)?由董事会(?:保留|决定|审议|作出)"),
        (r"(?:提名|推荐).{0,12}(?:需|需要|必须).{0,12}董事会(?:审议|决定|通过)", r"(?:提名|推荐).{0,12}(?:需|需要|必须).{0,12}董事会(?:审议|决定|通过)"),
        (r"章程中.{0,18}治理调整.{0,18}需要", r"章程中.{0,18}治理调整.{0,18}需要"),
        (r"(?:当前)?融资模型", r"(?:当前)?融资模型"),
        (r"估值(?:区间|基准)?(?:是|为|在)?", r"估值(?:区间|基准)?(?:是|为|在)?"),
        (r"反稀释保护", r"反稀释保护"),
        (r"独立兑现权", r"独立兑现权"),
        (r"优先级不受", r"优先级不受"),
        (r"(?:Pre-?[A-D]|[A-D])轮.{0,20}(?:融资|董事会决议)", r"(?:Pre-?[A-D]|[A-D])轮.{0,20}(?:融资|董事会决议)"),
        (r"签字人(?:是|为)", r"签字人(?:是|为)"),
        (r"(?:法务|法律|公司|内部).{0,4}(?:存档|档案(?:室|库)|系统(?:中|内))", r"(?:法务|法律|公司|内部).{0,4}(?:存档|档案(?:室|库)|系统(?:中|内))"),
        (r"(?:没有|无).{0,8}联系方式", r"(?:没有|无).{0,8}联系方式"),
        (r"(?:融资|协议|授权)?文件.{0,8}(?:已经|已).{0,4}生效", r"(?:融资|协议|授权)?文件.{0,8}(?:已经|已).{0,4}生效"),
        (r"董事会.{0,12}(?:批准|通过).{0,16}(?:融资|条款|方案)", r"董事会.{0,12}(?:批准|通过).{0,16}(?:融资|条款|方案)"),
        (r"(?:未|没有).{0,14}(?:形成|作出).{0,12}(?:独立)?决议", r"(?:未|没有).{0,14}(?:形成|作出).{0,12}(?:独立)?决议"),
        (r"(?:你|早期合伙人).{0,8}有权.{0,24}(?:了解|要求|参与|获得)", r"(?:你|早期合伙人).{0,8}有权.{0,24}(?:了解|要求|参与|获得)"),
        (r"授权链.{0,24}(?:涉及|包括|成员|权限)", r"授权链.{0,24}(?:涉及|包括|成员|权限)"),
        (r"(?:最终签署权|独立董事.{0,12}合规审核)", r"(?:最终签署权|独立董事.{0,12}合规审核)"),
        (r"决策链.{0,18}(?:需|需要|必须).{0,18}(?:董事会|重新授权)", r"决策链.{0,18}(?:需|需要|必须).{0,18}(?:董事会|重新授权)"),
        (r"(?:正式提交|正式提案).{0,24}(?:独立董事|合规审核)", r"(?:正式提交|正式提案).{0,24}(?:独立董事|合规审核)"),
        (r"完整文件.{0,18}(?:需|需要|必须).{0,18}(?:董事会|合规审核|获取)", r"完整文件.{0,18}(?:需|需要|必须).{0,18}(?:董事会|合规审核|获取)"),
        (r"(?:这版|这份|该).{0,12}(?:草稿|草案|摘要|文件|记录)", r"(?:草稿|草案|摘要|文件|记录)"),
        (r"董事会席位.{0,18}(?:投资人).{0,12}(?:主导|控制)", r"董事会席位.{0,18}(?:投资人).{0,12}(?:主导|控制)"),
        (r"产品委员会.{0,24}(?:投票权|投票权重|预算审批|职责范围|职能边界)", r"产品委员会.{0,24}(?:投票权|投票权重|预算审批|职责范围|职能边界)"),
        (r"投决会", r"投决会"),
        (r"(?:没有|未).{0,10}(?:提前)?.{0,6}(?:与你|由你|你).{0,6}确认", r"(?:没有|未).{0,10}(?:提前)?.{0,6}(?:与你|由你|你).{0,6}确认"),
        (r"(?:文件|记录).{0,18}(?:需|需要|必须).{0,18}(?:合规流程|调取)", r"(?:文件|记录).{0,18}(?:需|需要|必须).{0,18}(?:合规流程|调取)"),
        (r"授权链.{0,24}(?:审批责任人|权限范围|各环节)", r"授权链.{0,24}(?:审批责任人|权限范围|各环节)"),
        (r"董事会.{0,18}授权.{0,18}(?:融资|条款|稀释)", r"董事会.{0,18}授权.{0,18}(?:融资|条款|稀释)"),
        (r"决策路径.{0,18}(?:经|由).{0,12}(?:我方|创始人|法律顾问).{0,12}(?:主导|确认)", r"决策路径.{0,18}(?:经|由).{0,12}(?:我方|创始人|法律顾问).{0,12}(?:主导|确认)"),
        (r"(?:没有|无).{0,12}(?:其他|中间).{0,10}授权环节", r"(?:没有|无).{0,12}(?:其他|中间).{0,10}授权环节"),
        (r"(?:这次)?融资.{0,12}(?:属于|在).{0,12}董事会授权范围", r"(?:这次)?融资.{0,12}(?:属于|在).{0,12}董事会授权范围"),
        (r"(?:未|没有).{0,10}触发.{0,12}(?:确认|授权|调整)流程", r"(?:未|没有).{0,10}触发.{0,12}(?:确认|授权|调整)流程"),
        (r"(?:权益|股权).{0,10}调整.{0,12}(?:需|需要|必须).{0,12}触发条件", r"(?:权益|股权).{0,10}调整.{0,12}(?:需|需要|必须).{0,12}触发条件"),
    )
    for claim_pattern, evidence_pattern in detail_rules:
        if not re.search(evidence_pattern, authored):
            unsupported.update(
                normalize_text(clause)
                for clause in _assertive_claim_clauses(text, claim_pattern)
            )

    for clause in re.split(r"[。！？!?；，]|(?:但是|但|不过)", text):
        numeric_terms = set(re.findall(
            r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)"
            r"(?:元|块|千|万|亿|号|日|月|年|轮|成|%|名|位|人)",
            clause,
        ))
        if not numeric_terms or not re.search(
            r"(?:估值|融资|股权|权益|持股|增长|比例|条款|份额|"
            r"董事会|授权|决策|成员|同意|审核)", clause
        ):
            continue
        if not _assertive_claim_clauses(clause, r"."):
            continue
        compact_authored = re.sub(r"\s+", "", authored)
        if any(
            re.sub(r"\s+", "", term) not in compact_authored
            for term in numeric_terms
        ):
            return True
    unsupported.discard("")
    if not unsupported:
        return False
    if len(unsupported) > 1:
        return True

    clause = next(iter(unsupported))
    hard_specificity = re.compile(
        r"(?:根据|按照|按).{0,16}(?:协议|条款|章程)|"
        r"(?:初始协议|最早.{0,6}授权文件).{0,18}(?:由|签署|拟定)|"
        r"(?:融资|协议|授权)?文件.{0,8}(?:已经|已).{0,4}生效|"
        r"(?:这版|这份|该).{0,12}(?:草稿|草案|摘要|文件|记录)|"
        r"(?:投决会|合规调取|审批责任人|权限范围)|"
        r"(?:权益|股权).{0,10}调整.{0,12}(?:需|需要|必须).{0,12}触发条件|"
        r"(?:文件|记录).{0,18}(?:合规流程|调取)|"
        r"由.{1,16}(?:签署|拟定)|"
        r"(?:首轮|第[一二三四五六七八九十\d]+轮|(?:Pre-?[A-D]|[A-D])轮)|"
        r"(?:文件|邮件记录|系统记录|会议纪要|存档记录|授权文件|"
        r"董事会决议|投后文件).{0,18}(?:显示|表明|确认|记载|通过|"
        r"签署|备案|完成|存在|存放|明确)|"
        r"(?:协议|条款|章程).{0,18}(?:存在|明确|设置|规定|要求|包含)|"
        r"(?:从|在)法律文件中.{0,12}(?:找到|存在|有).{0,8}依据|"
        r"(?:签署人|签字人|决策依据)(?:是|为)|"
        r"(?:需要|需|必须|均需|通常).{0,24}"
        r"(?:董事会|投资人会议|签署|表决|授权|章程|议事规则)|"
        r"(?:最终决策|最终任命).{0,18}(?:董事会|保留|决定|作出)|"
        r"(?:每个季度|季度战略|具体安排(?:是|为|包括))|"
        r"(?:法务|法律|公司|内部).{0,4}(?:存档|档案(?:室|库)|系统(?:中|内))|"
        r"(?:目前)?(?:没有|无).{0,10}(?:新)?(?:文件|事实)|"
        r"(?:你|早期合伙人).{0,12}(?:保留|拥有).{0,28}"
        r"(?:董事会席位|否决权|审批权|知情权|决策权)|"
        r"产品战略.{0,18}预算.{0,18}(?:人事|任命)|"
        r"(?:产品委员会|投票权重|预算审批).{0,24}(?:职责|职能|资源分配|最终决策)|"
        r"稀释.{0,24}(?:通过.{0,14}完成|没有经过.{0,8}确认)|"
        r"反稀释保护.{0,18}独立兑现权|"
        r"(?:联系方式|一致行动人条款|投资人席位已占多数|已成定局)"
    )
    if hard_specificity.search(clause):
        return True

    detail_markers = (
        r"董事会|协议|章程|条款|融资|授权|签署|表决|决议|"
        r"法务|存档|联系方式|投票|投资人|治理权|决策权|知情权|"
        r"否决权|审批权|反稀释保护|独立兑现权"
    )
    return len(set(re.findall(detail_markers, clause))) >= 2


def introduces_unprompted_coordination_actor(candidate, observable_text):
    """Do not invent a new person/office to carry the conversation off screen."""
    text = str(candidate)
    actor = re.search(
        r"(?:秘书|助理|法务|律师|人事|HR|委员会|秘书处|办公室|部门)",
        text,
        re.IGNORECASE,
    )
    coordination = re.search(
        r"(?:让|请|安排|联系|对接|协调|调取|整理|核查|反馈|发送|召开)",
        text,
    )
    observed = str(observable_text).lower()
    named_actor = re.search(
        r"(?:王|李|张|刘|陈|杨|赵|黄|周|吴|徐|孙|胡|朱|高|林|何|郭|马|"
        r"罗|梁|宋|郑|谢|韩|唐|冯|于|董|程|曹|袁|邓|许|傅|沈|曾|彭|"
        r"吕|苏|卢|蒋|蔡|贾|丁|魏|薛|叶|余|潘|杜|戴|夏|钟|汪|田|"
        r"任|姜|范|方|石|姚|谭|廖|邹|熊|金|陆|郝|孔|白|崔|康|毛|"
        r"邱|秦|江|史|顾|侯|邵|孟|龙|万|段|雷|钱|汤|尹|黎|易|常|"
        r"武|乔|贺|赖|龚|文)[\u4e00-\u9fff]{0,2}"
        r"(?:律师|秘书|经理|主任|顾问)",
        text,
    )
    if named_actor and named_actor.group(0).lower() not in observed:
        return True
    if not (actor and coordination):
        return False
    return actor.group(0).lower() not in observed


def introduces_unprompted_legal_escalation(candidate, observable_text):
    """Legal escalation must be introduced by observable dialogue, not as filler."""
    escalation = re.compile(
        r"(?:法律评估|法律程序|诉讼|起诉|仲裁|法院|司法|报案|举报|"
        r"委托律师|通知律师|律师函)"
    )
    if not escalation.search(str(candidate)):
        return False
    return not escalation.search(str(observable_text))


def confirms_ungrounded_numeric_detail(candidate, observable_text):
    """Reject ungrounded exact numbers and financing-round references."""
    text = str(candidate)
    observed = re.sub(r"\s+", "", str(observable_text))
    round_terms = set(re.findall(
        r"(?:Pre-?[A-D]|[A-D])轮|天使轮|种子轮", text, re.IGNORECASE
    ))
    if (
        round_terms
        and not re.search(r"(?:假设|假如|如果|若)", text)
        and any(re.sub(r"\s+", "", term) not in observed for term in round_terms)
    ):
        return True
    if not re.search(r"确认|接受|同意|就按|说定|定了", text):
        return False
    numeric_terms = set(re.findall(
        r"(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)"
        r"(?:元|块|千|万|号|日|月|成|%)|一半",
        text,
    ))
    if not numeric_terms:
        return False
    proposed_numeric = bool(re.search(
        r"(?:要求|建议|提议|主张|不得|至少|至多|不低于|不高于|不超过|上限|下限)"
        r"[^。！？；]{0,20}(?:\d+(?:\.\d+)?|[一二两三四五六七八九十百千万]+)"
        r"(?:元|块|千|万|号|日|月|成|%)",
        text,
    ))
    if proposed_numeric:
        return False
    return any(re.sub(r"\s+", "", term) not in observed for term in numeric_terms)


def follows_policy_action_format(value, *, allow_reported_claims=False):
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
    return (
        True if allow_reported_claims
        else avoids_unsupported_offscreen_claim(text)
    )


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
    retry_guidance="",
    enforce_repetition=True,
    candidate_transform=None,
):
    """Retry until valid, optionally treating lexical repetition as a hard error."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    prior = list(dict.fromkeys(
        str(value).strip() for value in prior_texts if str(value).strip()
    ))
    base_messages = [dict(item) for item in messages]
    retry_messages = base_messages
    last_rejection_reason = "unknown validation failure"
    diagnostics = []
    for attempt in range(1, max_attempts + 1):
        attempt_sampling = dict(sampling)
        if attempt > 1 and isinstance(attempt_sampling.get("temperature"), (int, float)):
            attempt_sampling["temperature"] = max(
                0.7, float(attempt_sampling["temperature"])
            )
            attempt_sampling["top_p"] = max(
                0.9, float(attempt_sampling.get("top_p", 0.9))
            )
        candidate = provider.complete(
            retry_messages, **attempt_sampling
        ).strip()
        if candidate_transform is not None:
            candidate = str(candidate_transform(candidate)).strip()
        rejection_reason = None
        closest = max(
            prior,
            key=lambda previous: text_similarity(candidate, previous),
            default="",
        )
        if not follows_dialogue_format(candidate):
            rejection_reason = "wrong format or speaker-labelled/stage-directed output"
        else:
            validator_passed, validator_reason = validation_verdict(
                validator, candidate
            )
            if not validator_passed:
                rejection_reason = (
                    validator_reason
                    or "runtime policy or factual-grounding rule violation"
                )
        if rejection_reason is None and enforce_repetition:
            reused = reused_dialogue_template_signatures(candidate, prior)
            if reused:
                templates = ", ".join(reused)
                rejection_reason = f"reused discourse template ({templates})"
            elif any(
                normalize_text(candidate) == normalize_text(previous)
                or text_similarity(candidate, previous) >= similarity_threshold
                for previous in prior
            ):
                rejection_reason = "semantic repetition of an earlier turn"
        if rejection_reason is None:
            return candidate
        diagnostics.append({
            "attempt": attempt,
            "candidate": candidate,
            "reason": rejection_reason,
            "closest_prior": closest,
            "similarity_to_closest": text_similarity(candidate, closest) if closest else 0.0,
            "template_signatures": sorted(dialogue_template_signatures(candidate)),
        })
        last_rejection_reason = rejection_reason
        escape = template_escape_instructions(
            reused_dialogue_template_signatures(candidate, prior)
        )
        reason_escape = validation_escape_instructions(rejection_reason)
        retry_messages = base_messages + [
            {"role": "assistant", "content": candidate},
            {
                "role": "user",
                "content": (
                    "Runtime validation rejected that draft for "
                    f"{rejection_reason}. The closest earlier utterance was: "
                    f"{closest!r}. Do not paraphrase either sentence. Change "
                    "the speech act or conversational move while staying with an already-visible "
                    "unresolved issue, or close the current issue naturally. Do not "
                    "invent another document, condition, deadline, authority, or "
                    "consequence merely to be different. "
                    "Do not reuse a prior opening or conditional frame such as "
                    "'I accept ... but if ...' or 'Since ... then ...'. "
                    f"针对本次命中的具体问题：{reason_escape or escape or '不要改写旧句，改用不同的现实对话动作。'} "
                    f"{retry_guidance} "
                    "Produce one materially different single-speaker turn. "
                    "Do not mention this validation feedback."
                ),
            },
        ]
    raise TextValidationError(
        f"{context} failed distinct-text validation after {max_attempts} attempts: "
        f"{last_rejection_reason}",
        diagnostics,
    )
