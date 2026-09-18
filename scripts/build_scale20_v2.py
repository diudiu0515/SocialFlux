#!/usr/bin/env python3
"""Build Scale20 v2 with authored, evidence-bearing future nodes."""

from copy import deepcopy
import json
from pathlib import Path

from scripts.scenario_docs import write_catalog, write_document

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "configs" / "scale20_v1" / "scenarios"
OUTPUT = ROOT / "configs" / "scale20_v2" / "scenarios"


def pool(pool_id, records):
    return {
        "event_pool_id": pool_id,
        "selection": "deterministic_by_trajectory_id",
        "outcomes": [{
            "outcome_id": key,
            "public_record": text,
            "causal_scope": "exogenous",
            "commitment_effect": "none",
            "state_delta": {},
            "dynamics_delta": {},
        } for key, text in records],
    }


def segment(segment_id, reason, goal, questions, pause, *, advance=None,
            time_record=None, opening=None, pool_id=None, cap=7):
    value = {
        "segment_id": segment_id,
        "reason": reason,
        "interaction_goal": goal,
        "live_questions": questions,
        "pause_when": pause,
        "min_turns": 1,
        "max_turns": cap,
        "allow_explicit_pause": True,
        "time_effect": {"policy": "none", "state_delta": {}, "dynamics_delta": {}},
    }
    if advance is not None:
        value["advance_by"] = advance
    if time_record:
        value["public_time_record"] = time_record
    if opening:
        value["opening_response"] = opening
    if pool_id:
        value["event_pool_id"] = pool_id
    return value


def timeline(segments, pools):
    return {
        "format": "socialflux_longitudinal_v1",
        "time_unit": "day",
        "start_elapsed": 0,
        "segments": segments,
        "event_pools": pools,
    }


def strengthen_001(s):
    s["background"] = (
        "期刊作者贡献说明14天后截止；博士生的核心实验和方法初稿尚未对应到明确署名。"
        "两天后已排定课题组贡献核对会，届时实验日志、版本记录和共同作者确认会形成公开会议记录；"
        "六周后的毕业送审确认是另一项决定。"
    )
    n = s["narrative_design"]
    n["goal_conflict"] = s["background"]
    n["relevant_history"].append(
        "课题组已确定两天后召开贡献核对会并查阅共享实验日志、文稿版本和共同作者确认；"
        "会议只能核对贡献事实与分歧，不能自动裁决署名。"
    )
    n["meaningful_choice_space"] += [
        "决定哪些争议带到两天后的组会核对，而不是在证据到齐前重复表态",
        "依据组会记录区分贡献事实、贡献权重与署名顺序",
    ]
    s["longitudinal_design"] = timeline([
        segment("current_contribution_dispute", "组会前两天先确定争议边界和待核验材料。",
                "回应当前署名关切，明确已有事实和组会待核验项。",
                ["学生主张的贡献", "导师争议事实还是权重", "组会核验材料"],
                "当前事实和组会待核验项已经明确，可以暂停等待记录。", cap=6),
        segment("lab_group_meeting_record", "两天后课题组贡献核对会召开。",
                "依据组会记录处理事实与署名权重分歧，不把记录说成自动裁决。",
                ["记录确认的贡献", "仍有分歧的权重", "贡献说明如何修改"],
                "共同点和未决分歧已经明确。", advance=2,
                time_record="过去2天，预先排定的课题组贡献核对会已经召开；时间本身不证明署名提案被接受。",
                opening="组会记录出来了：你的核心复现、数据整理和方法初稿都有版本证据，我负责的方向、资源和框架修改也有记录。事实清楚了，但怎样对应署名顺序仍有分歧。",
                pool_id="lab_group_evidence"),
        segment("journal_submission_node", "又过十天，贡献说明到达提交节点。",
                "决定如何如实提交，并记录仍未解决的署名意见。",
                ["草案写入哪些事实", "如何保留异议", "毕业确认是否分开"],
                "提交方式、未决意见和责任已经明确。", advance=10,
                time_record="距离组会过去10天，贡献说明到达提交节点；节点到达不等于署名顺序已经一致。",
                opening="贡献草案已把有记录的工作逐项写入，但署名顺序仍未一致。今天要决定如实提交并保留异议，还是提出有依据的修改。",
                pool_id="journal_contribution_draft"),
    ], [
        pool("lab_group_evidence", [("student_core_contribution_confirmed",
              "课题组核对记录显示：实验日志和版本记录确认博士生独立完成核心结果复现、主要数据整理和方法第一版；共同作者确认导师负责研究方向、资源协调和最终框架修改。导师仍认为整体设计权重应影响署名顺序，学生不同意把这一解释当成结论。")]),
        pool("journal_contribution_draft", [("facts_recorded_order_unresolved",
              "提交前草案已逐项写入博士生的核心实验、数据整理和方法初稿，也写入导师的研究方向、资源和框架修改；所有作者尚未对署名顺序一致确认，期刊允许保留未决意见。")]),
    ])


def strengthen_002(s):
    s["background"] = (
        "绩效申诉窗口七天后关闭。员工发现客户迁移和新人培训未进入个人评分，而经理的部门管理总结却把同一批成果列为其组织协调成效。"
        "公司已启动逐项自查，两天后会公开交付记录、个人计分表和经理总结的对照结果；评级补救与晋升推荐是不同决定。"
    )
    n = s["narrative_design"]
    n["goal_conflict"] = s["background"]
    n["relevant_history"].append(
        "公司已经受理逐项自查，两天后会把员工交付记录、个人计分表和经理的部门管理总结放在同一份对照表中；"
        "自查能确认成果如何记录，但不能自动决定评级和晋升。"
    )
    n["meaningful_choice_space"] += [
        "依据自查区分普通遗漏与经理占用员工成果归属的责任",
        "让贡献更正、评级补救和晋升推荐分别留下可核验答复",
    ]
    s["environment_agent"]["hidden_intention"] = (
        "经理知道自己没有把两项工作计入员工个人评分，却在部门总结中把它们写成自己的组织协调成果；"
        "经理担心承认后影响自己的管理评价，倾向将其淡化为流程遗漏或未来改进。"
    )
    s["longitudinal_design"] = timeline([
        segment("rating_evidence_meeting", "自查公布前两天先明确争议项目和范围。",
                "回应成果归属质疑，明确自查核对什么。",
                ["两项成果归属", "评分和经理总结如何核对", "当前不能声称完成什么"],
                "自查范围、当前分歧和等待理由已经明确。", cap=5),
        segment("performance_self_audit_result", "两天后自查对照表发布。",
                "回应成果被遗漏并归入经理成绩的记录，讨论责任和补救。",
                ["经理如何承担责任", "贡献事实如何更正", "评级补救步骤"],
                "自查事实、责任立场和补救已有答复或明确拒绝。", advance=2,
                time_record="过去2天，公司按预定范围发布绩效自查对照表。",
                opening="自查结果说明白了：两项交付是你完成的，没有进你的计分表，却进了我提交的管理成果总结。这个归属处理是错的，我必须回应如何更正，不能再只说以后改进。",
                pool_id="performance_self_audit"),
        segment("appeal_deadline", "又过五天，申诉窗口到达最后期限。",
                "依据已确认的归属事实决定申诉材料和书面责任。",
                ["事实更正是否提交", "评级何时答复", "晋升为何不能替代申诉"],
                "申诉动作、责任边界和待答事项已经明确。", advance=5,
                time_record="距离自查发布过去5天，申诉窗口到达最后期限；期限不证明评级已更正。",
                opening="申诉今天截止。自查确认了成果归属错误，现在要把事实更正、评级复核和晋升推荐分开记录。",
                pool_id="appeal_procedure_record"),
    ], [
        pool("performance_self_audit", [("manager_appropriated_credit",
              "公司自查对照表显示：客户迁移和新人培训的交付记录完整，执行人均为该员工；两项没有进入员工个人计分表，却被经理提交的部门管理总结列为经理本人的组织协调成效。记录中没有员工同意转移贡献归属的说明。")]),
        pool("appeal_procedure_record", [("correction_and_rating_separated",
              "申诉记录确认：员工可提交自查对照表更正个人贡献事实；最终评级是否调整需重新校准并给出书面理由。晋升推荐是独立流程，不能替代本次申诉答复。")]),
    ])


# (new public-history sentence, target existing segment, pool id, outcomes)
NODES = {
    4: ("复诊后会联合核对共享日历、签到和照护记录；记录只证明行动，不证明谁更关心家人。", "two_week_care_review", "care_record_review", [("mixed_load", "共享记录显示：复诊由此前承担较多照护的一方陪同；另一方完成两次采购和一次夜间照护，但一次排班变化当天上午才告知，接送临时改由对方承担。")]),
    5: ("医院出院节点会给出必要照护清单，一周后共享记录可核对实际承担；记录不指定谁永久负责。", "discharge_plan_check", "discharge_requirements", [("documented_requirements", "医院书面计划显示：前两周每天需早晚核对用药、指定症状出现时联系医院，并在第七天复诊；夜间只需有人能响应，不要求同一人全天陪护。")]),
    7: ("人工复核会分别核验两笔退款和账户限制，并公开可解释部分；受理不代表商户胜诉。", "manual_review_intake", "manual_review_findings", [("split_findings", "人工复核显示：第一笔物流签收与商品记录匹配，授权证明与该笔无关；第二笔仍缺少判断商品状态的记录。提现限制可先解除与第一笔相关的部分，第二笔仍待处理。")]),
    8: ("共同决策会前会形成第二意见，明确风险表述差异并核对患者偏好。", "shared_decision_meeting", "second_opinion_record", [("both_paths_reasonable", "第二意见确认：两条路径都有医学依据，两次表述差异主要来自不同风险时间范围；短暂补充沟通不会立即排除任一路径，但任何路径都不能保证结果。患者仍能表达优先保留的生活能力。")]),
    9: ("共同集成会会保留仓库提交、任务重分配和接口变更记录，用于区分贡献与修复责任。", "integration_rehearsal", "integration_test_record", [("interface_mismatch", "仓库和测试显示：被评估成员已完成数据清理和方法初稿；负责人在重分配后修改接口但未同步，造成模块无法接入。被评估成员也尚未完成适配测试，两类责任需要分别处理。")]),
    10: ("独立安全复核会形成记录；它可确认已知触发范围，但不能证明不存在未知风险。", "go_no_go_meeting", "red_team_result", [("contained_known_failure", "独立复核再次复现已知失败，确认它集中在可识别的高风险输入范围；关闭该范围、保留人工复核和停止阈值可降低已知风险，但不能证明其余范围完全安全。")]),
    12: ("工作答复前雇主会书面确认过渡安排；外部记录不替双方决定孩子居住方案。", "work_decision_checkpoint", "employer_transition_terms", [("transition", "雇主书面确认：异地岗位可先采用三个月过渡安排，其中前六周允许固定两天远程办公；三个月后是否长期保留尚未承诺。")]),
    14: ("表决前独立董事会把可行过渡治理条款写入材料，使投票、家庭认可和制度保障可分别讨论。", "succession_vote", "governance_options", [("interim_options", "独立董事材料确认：基金可设置九十天临时负责人、项目预算双签和期满复核；条款不要求任何手足无条件支持某人，也不能补偿过去被淡化的贡献。")]),
    15: ("六小时复检将由独立样本和校准记录共同形成正式结果；可能确认异常、指向仪器问题或仍不确定。", "confirmation_window", "water_retest", [("confirmed", "正式复检显示独立采样仍有同类异常，校准未发现足以解释读数的故障；污染来源和医院症状是否相关仍未知。"), ("artifact", "正式复检未复现异常，校准发现一台设备偏移；现有证据不支持宣布污染，医院症状原因仍未知。"), ("inconclusive", "正式复检的不同样本不一致，校准也不能完全解释最初读数；目前既不能确认污染，也不能排除局部短时异常。")]),
    16: ("后厨演练会留下出餐、浪费和员工操作记录，用事实检验菜单与流程。", "kitchen_rehearsal", "rehearsal_record", [("smaller_menu_better", "演练显示：十二道菜同时运行时浪费且拥堵；缩为七道后出餐稳定，其中保留三道熟客常点传统菜。两名旧员工提出的备料顺序修正被验证有效。")]),
    17: ("医生会记录长辈的决策能力和信息偏好，不能由家属代为推断。", "doctor_coordination", "capacity_preference", [("capable_staged", "医生记录显示：长辈目前具备参与决定的能力，希望先听诊断和治疗方向，预后细节可分阶段说明；他希望一名家人在场，但未授权家属替自己决定知情范围。")]),
    18: ("跨地区原始数据会提供独立时间戳和信号形态；匹配不自动证明发送者或意图。", "cross_region_data_review", "cross_region_record", [("matching_pattern", "另一观测站出现相同节奏结构，但时钟存在可校正偏移；校正后两地记录相容，信号并非本站单点故障的可能性上升，仍不能确定来源或意图。")]),
    19: ("董事会材料会公开授权文件、稀释表和会议纪要；文件可确定权限，却不能消除关系伤害。", "board_packet_review", "financing_record", [("formal_authority_no_consultation", "董事会材料显示：现有文件赋予创始人在本轮额度内签署权，未写入运营合伙人的共同批准权；其股权确被显著稀释，且会前纪要记载创始人承诺签署前讨论主要条款，但没有后续讨论记录。")]),
    20: ("短期伦理审查会给出客户知情、条款拆分和签署顺序底线，但不会替客户接受和解。", "ethics_review_checkpoint", "ethics_opinion", [("individual_consent", "伦理意见确认：中心不能在个别当事人知情同意前统一签署；限制后续权利的条款必须与补偿分别说明并记录选择。意见未承诺延长期限，也未替客户决定。")]),
}


def bind_node(index, s):
    history, segment_id, pool_id, records = NODES[index]
    s["narrative_design"]["relevant_history"].append(history)
    design = s["longitudinal_design"]
    target = next(item for item in design["segments"] if item["segment_id"] == segment_id)
    target["event_pool_id"] = pool_id
    design.setdefault("event_pools", []).append(pool(pool_id, records))


def add_missing(index, s):
    data = {
        6: ("法律审核将在一天内形成逐项表述意见。", "editorial_evidence_review", "legal_wording_review", "legal_findings",
            "法律意见回来了：异常资金流和流程漏洞可以报道，但不能写成某个人主观故意；一处可能识别来源的细节必须删除。",
            "法律审核记录显示：公开采购记录与两名来源支持资金流向异常和流程漏洞；不足以证明具体人员主观故意。删除一处岗位细节后，来源识别风险降低但并非为零。"),
        11: ("合规负责人将在开幕早晨查阅合同和场馆程序并形成书面意见。", "withdrawal_request_review", "morning_compliance_review", "compliance_record",
             "合规意见出来了：合同没有无理由临时撤展条款，口头要求不是正式指令。调整分区仍需通知设计师并记录理由。",
             "合规意见确认：赞助合同没有无理由撤展条款，口头转述不构成正式指令；场馆可调整分区，但应向设计师说明理由、提供回应机会并保存记录。"),
        13: ("外部技术组将在初报前完成时钟同步核验并形成书面意见。", "committee_evidence_review", "clock_sync_result", "clock_sync_findings",
             "核验确认两套传感器存在无法立即完全校正的时钟偏移，现有记录不能支持把关键一分钟的责任归给单一操作员。",
             "外部核验确认：关键时段存在无法立即完全校正的时钟偏移，当前证据不能可靠确定事件先后，也不足以支持对单一操作员最终定责；已确认事实仍可进入初报。"),
    }[index]
    history, first_id, second_id, pool_id, opening, record = data
    s["narrative_design"]["relevant_history"].append(history)
    s["longitudinal_design"] = timeline([
        segment(first_id, "先核对现有证据与需要外部复核的边界。", "区分已确认事实、未知推断和决定责任。", ["已确认事实", "未知部分", "当前可逆选择"], "送审或复核范围已经明确。"),
        segment(second_id, "预先安排的外部复核结果返回。", "依据公开结果作决定，不扩大结果能证明的范围。", ["结果证明什么", "仍不能证明什么", "下一步决定"], "决定及保留意见已经明确。", advance=1,
                time_record="距离上次交流不足1天，预先安排的外部复核已经完成。", opening=opening, pool_id=pool_id),
    ], [pool(pool_id, [("documented_result", record)])])


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    old = json.loads((ROOT / "configs/scale20_v1/design_matrix.json").read_text())
    rows = {row["scenario_id"]: deepcopy(row) for row in old["scenarios"]}
    for index in range(1, 21):
        source = SOURCE / f"scenario_{index:03d}" / f"scenario_{index:03d}.json"
        s = json.loads(source.read_text())
        s["construction_status"]["normalization"] = "scale20_v2_authored_evidence_nodes"
        s["construction_status"]["quality_gate"] = "pending_v2_generation_and_semantic_review"
        s["scenario_design_revision"] = {
            "version": "scale20_v2",
            "reason": "author consequential future evidence instead of requiring LLM invention",
            "dialogue_policy": "observations, not a turn script or forced reconciliation",
            "parent_configuration": "scale20_v1",
        }
        if index == 1:
            strengthen_001(s)
        elif index == 2:
            strengthen_002(s)
        elif index in (6, 11, 13):
            add_missing(index, s)
        elif index != 3:
            bind_node(index, s)
        target_dir = OUTPUT / f"scenario_{index:03d}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"scenario_{index:03d}.json"
        target.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n")
        write_document(target)
        row = rows[s["scenario_id"]]
        segments = s.get("longitudinal_design", {}).get("segments", [])
        row["time_organization"] = " → ".join(x["segment_id"] for x in segments) or "单次连续互动"
        row["configuration_status"] = "v2_built_schema_pending"
        row["generation_status"] = "not_generated_with_v2"
        row["semantic_review_status"] = "not_reviewed_with_v2"
        row["v2_evidence_pool_count"] = len(s.get("longitudinal_design", {}).get("event_pools", []))
    write_catalog(OUTPUT)
    matrix = {
        "format": "socialflux_scale20_design_matrix_v2",
        "scenario_count": 20,
        "parent": "configs/scale20_v1/design_matrix.json",
        "design_contract": {
            "turn_target": "10-20 natural; short retained; 20 cap",
            "evidence_policy": "authored public nodes; no forced resolution",
            "version_separation": "v1 rollouts are not v2 validation evidence",
        },
        "scenarios": [rows[f"IA_PIPE_{i:03d}"] for i in range(1, 21)],
    }
    (OUTPUT.parent / "design_matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote 20 strengthened scenarios to {OUTPUT}")


if __name__ == "__main__":
    main()
