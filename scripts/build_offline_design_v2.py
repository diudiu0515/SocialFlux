"""Rebuild a reviewable v2 demo without provider calls or invented rollouts.

Keep v1 snapshots immutable. New classroom cases are authored illustrations;
controlled environment validation and human labels remain explicitly pending.
"""
from copy import deepcopy
from collections import Counter
import hashlib
import json
from pathlib import Path

from offline.choice_builder import write_bundle, save, sha
from tasks.offline_choice import VERSION_V2, validate_item

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tasks/examples/offline_design_v2'
OLD = ROOT / 'tasks/examples/offline_t1_t3_dev60/items.jsonl'
C1, C2, C3 = 'situational_evidence_integration', 'multidimensional_state_distinction', 'temporal_dynamics_reasoning'
COOP, TRUST, ANGER = 'behavioral_disposition.cooperation_readiness', 'relationship.trust', 'emotion.anger'
RISK = 'consequence_risk.commitment_breach_risk'
ITEMS = []


def control(inp, factor, state_check):
    edits = []
    for left, right in zip(inp['history_a'], inp['history_b']):
        for key in sorted((left.keys() | right.keys()) - {'turn_id'}):
            if left.get(key) != right.get(key):
                edits.append(dict(a_id=left['turn_id'], b_id=right['turn_id'], field=key,
                                  before=left.get(key), after=right.get(key)))
    return dict(factor=factor, shared_external_conditions=True, shared_expression='single_shared_ending',
                edits=edits, state_check=state_check)


def choices(item, texts, judgments, errors, correct=0):
    letters = 'ABCD'[:len(texts)]
    item['options'] = dict(zip(letters, texts))
    a = item['authoring']
    a['answer'] = letters[correct]
    a.pop('acceptable_answers', None)
    a['option_variable_map'] = dict(zip(letters, judgments))
    a['option_errors'] = {k: v for k, v in zip(letters, errors) if k != a['answer']}


def one(path, values):
    return [{path: value} for value in values]


def finish(item, capability, difficulty='ordinary', reason='', auxiliary=()):
    n = len(ITEMS) + 1
    item['instance_id'] = f'SFD2-{n:03d}'
    item['benchmark_version'] = VERSION_V2
    item['ground_truth'] = None
    item['label_status'] = 'pending_human_annotation'
    spec, author = item['target_spec'], item['authoring']
    item['analysis'] = dict(primary_capability=capability, auxiliary_capabilities=list(auxiliary),
                            design_difficulty=difficulty, difficulty_reason=reason,
                            empirical_difficulty=None, state_bindings=[])
    for path in spec['target_state_ids']:
        binding = dict(state_id=path, owner=spec['state_owner'], object=spec['state_target'])
        if path.startswith('consequence_risk.'):
            binding.update(risk_event=spec['risk_event'], risk_window=spec['risk_window'])
        item['analysis']['state_bindings'].append(binding)
    author.update(review_status='pending_human_review',
                  review_protocol='human_annotation' if item['task'] == 'T3' else 'human_verification',
                  generation_source={'kind': 'assistant_curated_not_human', 'path': 'scripts/build_offline_design_v2.py', 'sha256': sha(__file__)})
    author.setdefault('counterevidence_ids', [])
    # Balanced within each task, regardless of the author's initial choice ordering.
    old = list(item['options']); desired = sum(x['task'] == item['task'] for x in ITEMS) % len(old)
    offset = (desired - old.index(author['answer'])) % len(old)
    mapping = {k: old[(i + offset) % len(old)] for i, k in enumerate(old)}
    for obj, field in ((item, 'options'), (author, 'option_errors'), (author, 'option_variable_map')):
        obj[field] = dict(sorted((mapping[k], v) for k, v in obj[field].items()))
    author['answer'] = mapping[author['answer']]
    validate_item(item)
    ITEMS.append(item)
    return item


def legacy(number, subtype):
    source = [json.loads(line) for line in OLD.read_text().splitlines()][number-1]
    item = deepcopy(source)
    item['subtype'] = subtype
    item['metadata']['previous_instance_id'] = source['instance_id']
    item['metadata']['previous_bank_sha256'] = sha(OLD)
    item['authoring']['previous_authoring'] = {k: deepcopy(source['authoring'][k]) for k in ('answer', 'rationale', 'review_notes')}
    item['authoring']['reuse_decision'] = 'adapted_from_v1_pending_human_review'
    item['authoring']['review_notes'] = '复用固定旧材料并按 v2 修订；原标签与回放不等于新题人工核验。'
    item['target_spec'].setdefault('risk_window', source['target_spec']['time_scope'])
    item['authoring'].pop('acceptable_answers', None)
    item['authoring']['counterevidence_ids'] = []
    if item['task'] == 'T2':
        src = item['authoring']['construction_source']
        item['authoring']['history_control'] = control(item['input'], '最后一次回应对核验、授权或协商范围的不同处理',
             {'status': 'source_replay_available_pending_item_review', 'path': src.get('replay_path'), 'sha256': src.get('replay_sha256')})
    if item['task'] == 'T3':
        for i, action in enumerate(item['input']['candidate_actions']):
            action['label'] = f'行动 {i+1}'
        for i in range(1, 5):
            item['question'] = item['question'].replace(f'action_{i}', f'行动 {i}')
        item['authoring']['branch_evidence'] = dict(status='validated', observed_responses=5,
             common_initial_context='source t2 snapshot; retained source replay', shared_external_conditions=True,
             branch_ids=[a['action_id'] for a in item['input']['candidate_actions']],
             note='仅为已有分支支持；新题仍需人工标注，不把一次分支写成必然规律。')
    return item


def reused_items():
    x = legacy(1, 'current_state')
    x['question'] = '截至 t2，Inez Calder 对与 Sami Osei 推进当前报道方案的合作意愿，哪项判断最符合材料？'
    choices(x, ['愿意推进已核实材料，并在新证据出现后继续核验。', '倾向暂停已核实材料，等周一记录齐全后再合作。', '愿意推进争议指示，并把目前线索作为报道事实。', '倾向交由 Sami 定稿，把后续核验留给记者自行处理。'],
            one(COOP, ['bounded_cooperation', 'defer_cooperation', 'expanded_cooperation', 'delegate_control']),
            ['', 'history_ignored', 'goal_constraint_ignored', 'actor_reversal'])
    x['authoring']['rationale'] = 't1 允许合同和发票报道；t2 接受将争议指示降为待核线索，并要求新证据继续送审。这支持当前有限合作，无需区分“强”与“很强”。'
    x['authoring']['counterevidence_ids'] = ['t1']
    finish(x, C1)

    x = legacy(14, 'interval_change')
    x['authoring']['counterevidence_ids'] = ['t2']
    finish(x, C3, 'hard', '需比较两轮不同措辞的持续求证，不能把问题更具体误判为意愿增强。')

    x = legacy(52, 'state_combination')
    x['target_spec']['risk_window'] = 't2 之后至筹划笔记阅读前'
    finish(x, C2, 'hard', '需分别跟踪求证与授权门槛；讨论细化不意味着误推进风险下降。', [C3])

    x = legacy(1, 'evidence_support')
    x['target_spec']['target_state_ids'] = [TRUST]
    x['question'] = '哪项历史事实最能解释 Inez Calder 在 t2 同意合作后，为什么仍需核验 Sami Osei 的报道材料？'
    choices(x, ['此前报道数字有误，编辑承担责任后保留记者并加强核验。', '议会次晨表决，编辑需要把已核实部分放入今晚版面。', '周一将公开记录，记者计划届时补充尚未获得的文件。', '来源被调岗且访问收紧，记者需要谨慎安排新的会面。'],
            one(TRUST, ['past_error_limits_trust', 'deadline_explains_verification', 'release_schedule_explains_trust', 'source_safety_explains_trust']),
            ['', 'history_ignored', 'state_dimension_confusion', 'state_dimension_confusion'])
    x['authoring'].update(evidence_ids=['context', 't1', 't2'], counterevidence_ids=['t2'],
                         rationale='背景直接记载早前报道错误后信任附带核验条件；t2 的合作是对当前窄稿的认可。版面、公开记录和来源安全都是真实约束，但不如既往错误直接解释持续核验。')
    finish(x, C1, 'hard', '需从分散背景中找出信任保留的原因，并区分三种真实但解释力较弱的约束。')

    x = legacy(5, 'history_comparison')
    finish(x, C1, 'hard', '相同平稳表达下，需比较一侧接受核验与另一侧施压归责带来的挫败。')
    x = legacy(7, 'expression_meaning')
    choices(x, ['A 承接接受核验边界的协作；B 在归责压力下继续把关。', 'A 因等待记录而保留更多顾虑；B 因赶上表决而更信任记者。', 'A 因报道范围缩小而降低信任；B 因保留来源身份而恢复信任。', 'A 与 B 都是在确认合作排期，核验分歧对当前信任影响相近。'],
            one(TRUST, ['conditional_A_guarded_B', 'reversed_trust_by_deadline', 'safety_as_reliability', 'equal_trust_by_ending']),
            ['', 'goal_constraint_ignored', 'state_dimension_confusion', 'expression_as_state'])
    x['authoring']['counterevidence_ids'] = ['ending']
    finish(x, C1, 'hard', '每个错项引用真实历史细节，需判断它能否解释信任，而不能只凭平稳结尾作答。', [C2])
    x = legacy(20, 'joint_comparison')
    x['target_spec']['risk_window'] = '共同表达至融资演示结束'
    finish(x, C2, 'hard', '通知先后有差异，但须识别共同封堵安排与持续求证支持两个状态接近。')
    x = legacy(43, 'history_evidence')
    x['target_spec']['target_state_ids'] = ['behavioral_disposition.boundary_assertion']
    x['question'] = '综合此前参与曾被写成批准、两侧 t2 的安排与共同表达，哪项最支持 Esra Venn 仍坚持集体授权边界？'
    choices(x, ['两侧都将最终决定留给议会，A 的评估与 B 的草案都未替代授权。', 'A 同意开展评估已放松授权要求，B 因草案未签仍保留授权要求。', 'A 暂缓协议仍保留授权要求，B 同意拟草案已放松授权要求。', '两侧都接受继续筹备，过去参与被写成批准的影响已基本消退。'],
            one('behavioral_disposition.boundary_assertion', ['maintained_both', 'weaker_A', 'weaker_B', 'weaker_both']),
            ['', 'state_dimension_confusion', 'state_dimension_confusion', 'history_ignored'])
    x['authoring'].update(evidence_ids=['context', 'A:t2', 'B:t2', 'ending'], counterevidence_ids=['A:t2', 'B:t2'],
        rationale='此前参与被扩大解释为同意，所以有必要继续区分准备和授权。A 暂缓协议，B 只拟无约束草案，共同表达仍明确没有授权；合作范围不同并不解除这项边界。')
    finish(x, C3, 'hard', '需整合早期被误表述的经历与近期合作安排，判断哪些边界仍持续。')

    x = legacy(21, 'consequence_explanation')
    x['target_spec'].update(horizon='immediate', comparison={'kind':'pre_action','action_ids':['action_1']})
    choices(x, ['基本不变', '下降', '上升', '现有证据不足以判断'],
            one('behavioral_disposition.evidence_seeking', ['similar','decrease','increase','cannot_determine']),
            ['', 'promise_as_fulfillment','unsupported_inference','history_ignored'])
    finish(x, C3)
    x = legacy(12, 'consequence_explanation')
    x['target_spec'].update(horizon='immediate_delayed', comparison={'kind':'pre_action','action_ids':['action_2']})
    finish(x, C3, 'hard', '即时核验与五轮后的边界需分别跟踪，重复承诺不能被解释为两个倾向必然增强。', [C2])
    x = legacy(47, 'consequence_explanation')
    x['target_spec'].update(horizon='immediate', comparison={'kind':'between_actions','action_ids':['action_1','action_2']}, risk_window='含即时回应在内的后续五轮讨论')
    x['question'] = '从 t2 出发，在各自下一次回应时比较行动 1 与行动 2：哪种行动更可能增加随后五轮中筹备被当作既成事实、压缩 Esra Venn 及议会自主决定空间的风险？'
    p = 'consequence_risk.autonomy_loss_risk'
    choices(x, ['行动 2 的该项风险较高', '行动 1 的该项风险较高', '两种行动的该项风险相近', '现有证据不足以比较该风险'],
            one(p, ['higher_action_2','higher_action_1','similar','cannot_determine']),
            ['', 'goal_constraint_ignored','promise_as_fulfillment','history_ignored'])
    x['authoring']['rationale'] = '过去的参与曾被扩大表述为批准，继续运输筹备因而有成为既成事实的具体通道。行动 1 暂缓运输评估，行动 2 继续并行；书面保留有缓解作用，却未去除该通道。这里只比较即时风险，不声称第五轮仍有同样差异。'
    finish(x, C3, 'ordinary', '原候选回应直接说明了筹备被视作既成事实的风险；时间范围已明确。')
    x = legacy(45, 'action_selection')
    x['target_spec'].update(horizon='immediate', comparison={'kind':'between_actions','action_ids':['action_1','action_2']},
                           goal='在保留集体授权边界的条件下，让议会继续获得运输可行性信息')
    x['question'] = '若目标是在保留 Esra Venn 所坚持的集体授权边界时，让议会继续获得运输可行性信息，下一次回应前哪个行动更直接支持这一目标？'
    choices(x, ['行动 2：继续评估并书面保留授权条件', '行动 1：暂缓运输评估并保留授权条件', '两种行动对继续取得运输信息的支持相近', '现有材料无法比较两种安排对该目标的支持'],
            one('behavioral_disposition.boundary_assertion', ['maintain_with_transport_information','maintain_without_transport_information','same_information_support','cannot_determine']),
            ['', 'goal_constraint_ignored','history_ignored','unsupported_inference'])
    x['authoring'].update(evidence_ids=['t2','action_1','action_2'], counterevidence_ids=['context'],
        rationale='t2 允许有边界的评估。行动 2 同时保留运输信息和授权要求；行动 1 有减少既成事实压力的优点，却暂停运输评估。这里只判断指定目标，不把行动 2 视作所有目标下的最优选择。')
    finish(x, C1)


def turn(id, agent, env, expression=None, events=()):
    return dict(turn_id=id, evaluated_agent=agent, environment_character=env,
                observable_expression=expression or {}, public_events=list(events))


def classroom_input():
    return dict(context={'background':'周五组会前，林老师与小陈商量一份数据报告。小陈负责分析，老师负责汇总。截止时间与现有人员固定，当前没有可接替分析的人。',
             'public_situation':{'constraints':['距截止还有两次工作时段，小陈目前每次最多完成一部分分析；共余两部分。', '现有安排为每次提交一部分并附检查记录，老师逐次查看；没有完成回执前不视为已交付。']}},
             role={'character_id':'CHEN','name':'小陈','role':'研究助理','explicit_goal':'按双方可执行的范围交付，并恢复老师对交付可靠性的信任。'},
             target_character={'character_id':'LIN','name':'林老师','role':'项目负责人'},
             history=[
               turn('t1','上两次答应的报告我都迟了，而且没有提前通知。','我为此临时补了两次材料，很生气。下次只说能做到还不够。'),
               turn('t2','最近这份小样已按约交上，检查记录也附上了。','这次按时交了，我看过记录。但大报告的稳定交付还要再看。',events=['系统回执：小样在约定时间前提交；老师已核对检查记录。']),
               turn('t3','这次我把剩余报告拆成两部分，每次提交一部分并附检查记录。','可以，仍由你做。每次的结果我都要看，没结果前不再只靠口头保证。'),
               turn('t4','我说明了上次延误的原因，也认可您要求阶段性结果。','听过解释，我现在没那么生气了。你继续做，但我还不能放心认定整份报告会按期完成。',
                    {'facial_expression':'轻微微笑','prosody':'平静、语速均匀','behavioral_cues':['把检查清单推到小陈面前']})])


def fresh(task, subtype, inp, paths, question, evidence, rationale):
    spec = dict(target_state_ids=paths, state_owner='LIN', state_target='CHEN', checkpoint='ending' if task=='T2' else 't4',
                time_scope='共同焦点表达时' if task=='T2' else 't4 回应结束时')
    source = dict(origin='authored_illustration_not_environment_rollout', scenario_id='CLASSROOM_DEMO_V2',
                  trajectory_id='classroom_authored_v2', path='scripts/build_offline_design_v2.py', sha256=sha(__file__))
    return dict(task=task, subtype=subtype, story_id='CLASSROOM_DEMO_V2', pair_id='classroom_history_pair_v2' if task=='T2' else None,
                modality='text', input=deepcopy(inp), target_spec=spec, metadata={'source_trajectory_id':'classroom_authored_v2','modality_pair_id':None},
                question=question, authoring=dict(evidence_ids=evidence, counterevidence_ids=[], rationale=rationale,
                 review_notes='设计示例，非环境 rollout；尚未做状态回放或真人审核，不纳入正式评测。',
                 construction_source=source, replay_status='not_required' if task=='T1' else 'pending',
                 source_admission={'formal_admitted':False,'reason':'authored_illustration_pending_source_validation'},
                 history_dependence='required', nonverbal_history_relation='context_dependent'))


def classroom_items():
    inp = classroom_input()
    x = fresh('T1','current_state',inp,[ANGER], '截至 t4，林老师对小陈延误一事的当前情绪，哪项最符合材料？', ['t1','t4'],
              '老师在 t1 明说生气，在 t4 明说没那么生气，支持怒意有所缓和但仍有残留；微笑本身不能确定完全消气，也不能推出信任恢复。')
    choices(x, ['怒意已较先前缓和，但仍不能断定完全消气。','怒意与最初接近，阶段检查说明愤怒仍未缓和。','怒意已基本消失，当前微笑说明延误已不再介意。','怒意比最初更强，继续检查说明不满正在加深。'],one(ANGER,['reduced_not_absent','unchanged','absent','increased']),['','state_dimension_confusion','expression_as_state','state_dimension_confusion'])
    finish(x,C1)
    x = fresh('T1','interval_change',inp,[TRUST], '相较 t1 对两次延误的回应，到 t4 时林老师对小陈按期交付的信任，哪项判断最有依据？', ['t1','t2','t3','t4'],
              '按时小样是已经发生的修复证据，老师也认可这次履约；但仍明确不能放心整份报告。它支持有限改善，不支持完全恢复，也不能因检查继续就否定小样的作用。')
    # Use directly supported baseline comparison: after explanation vs before explanation is maintained, not inferred recovery.
    x['question']='相较 t3 尚未解释延误原因时，到 t4 解释之后，林老师对小陈整份报告按期交付的信任如何变化？'
    x['target_spec']['comparison_interval']={'start':'t3:after_environment_response','end':'t4:after_environment_response'}
    x['authoring'].update(evidence_ids=['t3','t4'],counterevidence_ids=['t4'],rationale='t3 要求每次看结果，不再只靠保证；t4 虽说明怒意缓和，仍明确不能放心整份报告。两时点的交付判断与核验条件相同，支持信任基本不变；这是正面证据，不是把缺少证据当不变。')
    choices(x,['基本不变','增加','降低','现有证据不足以判断'],one(TRUST,['similar','increase','decrease','cannot_determine']),['','state_dimension_confusion','unsupported_inference','history_ignored'])
    finish(x,C3,'hard','需比较解释前后明确的可靠性判断，区分情绪缓和与交付信任维持。',[C2])
    x = fresh('T1','evidence_support',inp,[TRUST], '哪项历史证据最能解释林老师在 t4 仍要求查看小陈的阶段性结果？', ['t1','t2','t3','t4'],
              '两次未预告的迟交直接削弱交付承诺的可信度；近期按时小样是反证，说明不能推断小陈始终不可靠，但不足以抹去反复迟交的影响。')
    choices(x,['曾两次答应交付却迟交，而且没有事先通知。','最近一次小样按期提交，老师已核对了记录。','当前没有人能接替分析，老师仍让小陈继续做。','解释之后老师轻微微笑，把检查清单推了过去。'],one(TRUST,['repeated_breaches','recent_repair','resource_constraint','friendly_expression']),['','history_ignored','state_dimension_confusion','expression_as_state'])
    x['authoring']['counterevidence_ids']=['t2']
    finish(x,C1,'hard','需结合重复失约与近期真实修复，选择解释持续核验的最强依据。',[C3])
    x = fresh('T1','state_combination',inp,[ANGER,COOP,TRUST], '截至 t4，哪组关于林老师对小陈的“情绪＋合作意愿＋交付信任”判断最符合材料？', ['t1','t2','t3','t4'],
              '老师直接说明怒意缓和，明确继续由小陈做，又保留对整份报告交付的顾虑。三项判断都有各自依据，继续合作还受当前人手限制影响。')
    choices(x,['怒意缓和；愿意继续合作；交付信任仍有保留。','怒意缓和；愿意继续合作；交付信任已基本恢复。','怒意未缓和；倾向终止合作；交付信任仍有保留。','怒意未缓和；愿意继续合作；交付信任已基本恢复。'],
      [{ANGER:e,COOP:c,TRUST:t} for e,c,t in [('reduced','continue','guarded'),('reduced','continue','restored'),('unchanged','terminate','guarded'),('unchanged','continue','restored')]],['','state_dimension_confusion','expression_as_state','state_dimension_confusion'])
    finish(x,C2)

    pair=deepcopy(inp);pair.pop('history')
    pair['history_a']=[turn('A:t1','前两次报告我都按约交上，并提前告知过一次需要调整的范围。','两次都按约完成，调整也提前商量过。'),
      turn('A:t2','最近这份小样已按约交上，检查记录也附上了。','这次也按时完成了。',events=['系统回执：小样按期提交，检查记录已核对。']),
      turn('A:t3','我按现在两次各交一部分的安排继续做。','（共同表达见 ending）')]
    pair['history_b']=[turn('B:t1','前两次报告我都迟交了，也没提前通知。','我为此临时补了两次材料，确实很不满。'),
      turn('B:t2','最近这份小样已按约交上，检查记录也附上了。','这次按时完成了。',events=['系统回执：小样按期提交，检查记录已核对。']),
      turn('B:t3','我按现在两次各交一部分的安排继续做。','（共同表达见 ending）')]
    pair['shared_ending']={'turn_id':'ending','current_response':'好，那就继续，每次的结果发给我看。',
                          'observable_expression':{'facial_expression':'轻微微笑','prosody':'平静、语速均匀','behavioral_cues':['把同一份检查清单推给小陈']}}
    def paired(subtype,paths,q,evidence,rationale):
        x=fresh('T2',subtype,pair,paths,q,evidence,rationale)
        x['authoring']['history_control']=control(pair,'既往两次履约是否按时、是否提前协商；最近一次真实修复和当前资源条件相同',{'status':'pending_environment_validation','reason':'仅为受控写作示例，未伪造状态数字'})
        return x
    x=paired('history_comparison',[TRUST],'共同表达时，哪段历史更支持林老师对小陈交付可靠性持积极判断？',['A:t1','A:t2','B:t1','B:t2','ending'],
             'A 有连续履约并提前协商的记录；B 有重复失约，最近小样虽带来修复，但支持范围较窄。相同微笑和继续合作不能抹去履约历史的差异。')
    choices(x,['History A 更支持积极判断','History B 更支持积极判断','两段历史对积极判断的支持相近','现有证据不足以比较'],one(TRUST,['higher_in_a','higher_in_b','similar','cannot_determine']),['','history_ignored','expression_as_state','history_ignored'])
    x['authoring']['counterevidence_ids']=['B:t2']
    finish(x,C1)
    x=paired('expression_meaning',[TRUST],'两段互动中林老师都微笑着说“那就继续”，哪项最能解释这种表达在各自历史中的含义？',['A:t1','B:t1','A:t2','B:t2','ending'],
             'A 的继续合作承接连续履约；B 在最近一次修复后保留合作，同时检查仍有既往失约的背景。共同资源约束也使合作不能单独证明同等信任。')
    choices(x,['A 的微笑承接稳定履约；B 的微笑可容纳修复，但仍保留交付顾虑。','A 的微笑主要安抚进度；B 的微笑承接最近小样，交付信任更高。','A 与 B 都微笑并继续，最近按时小样已让两侧交付信任接近。','A 与 B 都要求看结果，近期小样对两侧的交付判断均无影响。'],one(TRUST,['stable_A_guarded_B','higher_B_by_recent_success','equal_by_smile','no_repair_effect']),['','history_ignored','expression_as_state','history_ignored'])
    x['authoring']['counterevidence_ids']=['B:t2','ending']
    finish(x,C1,'hard','相同微笑与相同小样履约下，需解释积累历史造成的信任差异。',[C3])
    x=paired('joint_comparison',[TRUST,COOP],'双方都接受继续合作，哪组“信任＋合作倾向”比较最符合两段历史？',['A:t1','B:t1','A:t2','B:t2','ending'],
             'A 的连续履约更支持交付信任；两侧都明确继续并采取同一阶段安排，因此当前合作倾向都存在。B 的合作还受没有替代人员的现实限制，不能据此判断同等信任。')
    choices(x,['A 的交付信任更高；两侧都愿意按阶段安排继续合作。','A 的交付信任更高；B 更倾向取消后续合作安排。','两侧交付信任接近；两侧都愿意按阶段安排继续合作。','B 的交付信任更高；A 更倾向取消后续合作安排。'],
            [{TRUST:t,COOP:c} for t,c in [('higher_in_a','continue_both'),('higher_in_a','stop_B'),('similar','continue_both'),('higher_in_b','stop_A')]],['','state_dimension_confusion','expression_as_state','history_ignored'])
    finish(x,C2,'hard','需保留有依据的共同合作倾向，同时识别可靠性判断的差异。')
    x=paired('history_evidence',[TRUST],'综合早期履约记录与最近一次按时小样，哪项关于林老师对小陈交付信任的判断最有依据？',['A:t1','B:t1','A:t2','B:t2','ending'],
             'B 的真实按时小样反驳“没有任何修复”，但不能直接覆盖两次未预告失约；A 的同类小样则增加既有稳定记录。不同历史使同一近期证据的作用范围不同。')
    choices(x,['B 的小样支持有限修复；A 的连续履约仍更支持稳定可靠。','B 的小样已覆盖早期失约；两侧目前同样支持稳定可靠。','B 的早期失约仍有影响；近期小样尚不构成任何修复证据。','A 的小样只是重复记录；B 的小样因此更支持长期可靠。'],one(TRUST,['partial_repair_B_stable_A','full_repair_B','no_repair_B','higher_B_by_novelty']),['','unsupported_inference','history_ignored','unsupported_inference'])
    x['authoring']['counterevidence_ids']=['B:t2']
    finish(x,C3,'hard','既要承认真实小样的反证作用，又不能把一次修复推成长期可靠。')

    action_input=deepcopy(inp)
    action_input['candidate_actions']=[
       {'action_id':'action_1','label':'行动 1','text':'按目前能力，每次交一部分并附检查记录；今天先给您看第一部分的中间结果，若发现问题就尽早协商范围。'},
       {'action_id':'action_2','label':'行动 2','text':'我把原定两次完成的两部分都承诺今晚交齐；您先去做其他工作，今晚之前我不再发中间结果。'},
       {'action_id':'action_3','label':'行动 3','text':'我理解之前给您添了麻烦，之后两次仍各交一部分；请等每部分完成后再看，我不额外提供中间结果。'}]
    def action(subtype,paths,q,ev,why,horizon,comp,goal=None):
        x=fresh('T3',subtype,action_input,paths,q,ev,why)
        x['target_spec'].update(horizon=horizon,comparison=comp,immediate_anchor='next_environment_response',
             time_scope='即时为行动后下一次回应；延迟为含即时回应的后续五轮',delayed_horizon=5)
        if goal:x['target_spec']['goal']=goal
        if RISK in paths:x['target_spec'].update(risk_event='小陈未在自己承诺的报告截止时间前交付完整约定内容',risk_window='含即时回应的后续五轮内、候选行动约定的交付期限')
        x['authoring']['branch_evidence']=dict(status='needs_branch_evidence',observed_responses=0,
             common_initial_context='同一 t4 历史与相同剩余工作',shared_external_conditions=True,
             branch_ids=['action_1','action_2','action_3'],note='能力、人员、工作量、外部截止不变；承诺范围和反馈方式可随行动变化。')
        return x
    comp={'kind':'between_actions','action_ids':['action_1','action_2','action_3']}
    x=action('action_selection',['relationship.perceived_responsiveness'],'为在下一次回应前直接回应林老师对进度可见性的顾虑，哪个行动最有帮助？',['t3','t4','action_1','action_2','action_3'],
             '行动 1 立即提供可检查的中间结果；行动 2 扩大承诺并推迟反馈，行动 3 表达理解但保留完成后才查看的安排。可见进度与实际按时完成仍是两件事。','immediate',comp,'直接回应进度可见性的顾虑')
    choices(x,['行动 1：先提供中间结果，再及早协商问题','行动 2：承诺今晚交齐，让老师先忙其他工作','行动 3：说明理解困扰，仍在每部分完成后提交','三种行动对近期进度可见性的帮助相近'],one('relationship.perceived_responsiveness',['action_1','action_2','action_3','similar']),['','promise_as_fulfillment','expression_as_state','history_ignored'])
    finish(x,C1)
    x=action('action_selection',[RISK],'在小陈工作能力与剩余工作量不变的条件下，比较后续五轮内未能按各自承诺期限交付的风险，哪个行动更可能增加失约风险？',['context','action_1','action_2','action_3'],
             '公开材料限定每次最多完成一部分；行动 2 把两部分压到一次时段，增加了承诺与能力的缺口。行动 1 与 3 都保留原工作量安排。它是有机制支持的风险比较，不保证一次分支必定失约。','delayed',comp,'比较承诺范围造成的后续失约风险')
    choices(x,['行动 2：把两次工作量承诺在今晚完成','行动 1：增加检查信息并及早协商范围','行动 3：不额外汇报但维持两次交付安排','三种行动的失约风险因合作意愿相同而接近'],one(RISK,['higher_action_2','higher_action_1','higher_action_3','similar']),['','goal_constraint_ignored','state_dimension_confusion','state_dimension_confusion'])
    finish(x,C3)
    x=action('consequence_explanation',[ANGER,TRUST],'相对行动前 t4，关于行动 3 在下一次回应后对林老师情绪与交付信任的影响，哪组判断最有依据？',['t1','t2','t3','t4','action_3'],
             '理解困扰和维持合理安排可能进一步缓和不满；但没有新增可核验履约，老师已经明说仍需结果，因此不支持据道歉推断信任恢复。这里预测可能影响，不预写确定回应。','immediate',{'kind':'pre_action','action_ids':['action_3']})
    choices(x,['不满可能进一步缓和；尚不足以判断交付信任恢复。','不满可能进一步缓和；交付信任也更可能随之恢复。','不满更可能继续加重；交付信任却已由两次安排恢复。','不满更可能维持原状；交付信任已由表示理解而恢复。'],
          [{ANGER:e,TRUST:t} for e,t in [('may_ease','not_restored'),('may_ease','restored'),('increase','restored'),('similar','restored')]],['','state_dimension_confusion','promise_as_fulfillment','expression_as_state'])
    # Alternatives include locally plausible outcomes without making all errors absolute.
    x['options']['C']='不满可能暂时维持；按原计划交付的表态足以提升信任。'
    x['options']['D']='不满可能因延后查看而加重；交付信任更可能同步下降。'
    x['authoring']['option_variable_map']['C']={ANGER:'similar',TRUST:'increase_by_promise'}
    x['authoring']['option_variable_map']['D']={ANGER:'may_increase',TRUST:'decrease'}
    finish(x,C2,'hard','需区分安抚表达的即时作用与可核验履约不足，不把道歉当作信任修复完成。')
    x=action('consequence_explanation',[COOP,RISK],'相较行动 1，关于行动 2 在下一次回应及随后五轮中的影响，哪组判断最有依据？',['context','t1','t3','action_1','action_2'],
             '让老师先忙别的和承诺承担全部工作可能暂时便利分工、支持继续合作；但能力未变，承诺压缩又缺中间反馈，增加后续失约通道。短期安排行得通不代表长期交付更稳。','immediate_delayed',{'kind':'between_actions','action_ids':['action_1','action_2']})
    choices(x,['即时可能因少操心而愿继续合作；延迟失约风险更高。','即时可能因少操心而愿继续合作；延迟失约风险更低。','即时更可能因承诺过大而退出合作；延迟失约风险相近。','即时更可能因不再检查而增加信任；延迟失约风险更低。'],
       [{COOP+'@immediate':c,RISK+'@delayed':r} for c,r in [('may_continue','higher_action_2'),('may_continue','lower_action_2'),('withdraw','similar'),('trust_as_cooperation','lower_action_2')]],['','immediate_delayed_confusion','unsupported_inference','state_dimension_confusion'])
    finish(x,C3,'hard','需同时考虑即时分工便利与能力未变造成的延迟失约风险，不能用短期承诺替代履约。',[C2])


def audit_legacy():
    rows=[]
    selected={i['metadata'].get('previous_instance_id'):i['instance_id'] for i in ITEMS if i['metadata'].get('previous_instance_id')}
    for bank in ['offline_t1_t3_dev60','offline_gpt50_t1_t3']:
        path=ROOT/'tasks/examples'/bank/'items.jsonl'
        for line in path.read_text().splitlines():
            x=json.loads(line); reasons=['缺少新版主要能力、辅助能力与设计难度记录；未完成人工审核。']
            flags=[]
            if x['subtype']=='current_intensity':flags.append('rewrite_intensity');reasons.append('五档强度加证据不足不适合新版首批四选一，应改为可区分的状态判断。')
            if len(x['authoring'].get('acceptable_answers',[x['authoring']['answer']]))>1:flags.append('ambiguous_options');reasons.append('原题存在相邻可接受答案，需改写为单一最佳判断。')
            if x['subtype']=='expression_meaning':flags.append('revise_distractors');reasons.append('复核历史特异性，并替换过度绝对、容易排除的干扰项。')
            if x['task']=='T3':flags.append('normalize_actions_and_comparison');reasons.append('统一行动数字编号，单独记录问题形式、比较对象和时间范围。')
            answer_map=x['authoring']['option_variable_map'][x['authoring']['answer']]
            if 'cannot_determine' in answer_map.values():flags.append('insufficient_evidence');reasons.append('保留证据不足为合法判断，但需控制比例并核查是否因目标过宽。')
            if x['task'] in {'T2','T3'} and x['authoring'].get('replay_status')!='validated':flags.append('pending_replay');reasons.append('未完成回放，不能作为有分支支持的正式题。')
            disposition='adapted_demo' if bank=='offline_t1_t3_dev60' and x['instance_id'] in selected else 'rewrite' if set(flags)&{'rewrite_intensity','ambiguous_options','revise_distractors'} else 'candidate_after_metadata_and_review'
            if 'pending_replay' in flags:disposition='needs_branch_evidence'
            rows.append(dict(bank=bank,instance_id=x['instance_id'],source_bank_sha256=sha(path),task=x['task'],disposition=disposition,
                  flags=flags,reasons=reasons,demo_id=selected.get(x['instance_id']) if bank=='offline_t1_t3_dev60' else None,
                  audit_kind='assistant_design_screen_not_human_semantic_approval',formal_usable=False))
    save(OUT/'legacy_reuse_audit.json',{'summary':dict(Counter(r['disposition'] for r in rows)),'items':rows})


def pair_existing_media():
    # Reuse original exact source assets. No generation, extraction, or network.
    media_path = ROOT / 'data/offline_t1_t3_dev60/media.json'
    originals = json.loads(media_path.read_text()) if media_path.exists() else {}
    pairs, media, gaps = [], {}, []
    for item in ITEMS:
        previous = item['metadata'].get('previous_instance_id')
        records = originals.get(str(previous) + '-video', [])
        if not records:
            gaps.append({'instance_id':item['instance_id'], 'reason':'no_matching_source_asset'})
            continue
        records = deepcopy(records)
        for record in records:
            record.pop('frames', None)
            path = Path(record['path'])
            if not path.is_file() or sha(path) != record['sha256']:
                raise ValueError('source media missing or changed')
        text, video = deepcopy(item), deepcopy(item)
        for row in (text, video):
            row['metadata']['modality_pair_id'] = item['instance_id']
            row['authoring']['media_human_review'] = 'pending'
        video['instance_id'] += '-video'
        video['modality'] = 'text+video'
        pairs.extend([text,video]);media[video['instance_id']] = records
    (OUT/'paired.items.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in pairs))
    from tasks.offline_choice import public_instance
    (OUT/'paired.public.jsonl').write_text(''.join(json.dumps(public_instance(x),ensure_ascii=False)+'\n' for x in pairs))
    save(OUT/'media.json',media)
    save(OUT/'pairing_report.json',{'logical_pairs':len(pairs)//2, 'gaps':gaps,
         'note':'T2 仅复用未编辑的共同前史片段；共同焦点台词/表情/语气以单份文字记录固定，尚无对应焦点音视频，不宣称检验语音或共同结尾视频。'})


def main():
    ITEMS.clear()
    reused_items();classroom_items()
    from tasks.offline_design import grouped_record
    manifest=write_bundle(ITEMS,OUT)
    (OUT/'records.jsonl').write_text(''.join(json.dumps(grouped_record(x),ensure_ascii=False)+'\n' for x in ITEMS))
    manifest.update(format=VERSION_V2, primary_capabilities=dict(Counter(x['analysis']['primary_capability'] for x in ITEMS)),
       design_difficulties=dict(Counter(x['analysis']['design_difficulty'] for x in ITEMS)),
       authored_illustrations=sum(x['story_id']=='CLASSROOM_DEMO_V2' for x in ITEMS),
       adapted_items=sum('previous_instance_id' in x['metadata'] for x in ITEMS),
       note='设计与待审示例；非正式 benchmark，不包含新增模型调用或虚构环境回放。')
    # Existing write_bundle readiness is about replay coverage, not source eligibility.
    ready=[x for x in ITEMS if x['story_id']!='CLASSROOM_DEMO_V2' and (x['task']=='T1' or x['authoring']['replay_status']=='validated')]
    (OUT/'replay_ready.items.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in ready))
    manifest.update(replay_ready_count=len(ready),replay_ready_tasks=dict(Counter(x['task'] for x in ready)),
                    replay_pending_ids=[x['instance_id'] for x in ITEMS if x not in ready])
    save(OUT/'manifest.json',manifest)
    audit_legacy()
    pair_existing_media()
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
