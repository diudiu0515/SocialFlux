"""Complete timed-out public-source drafts and remove identified question ambiguities.

This is assistant authoring, never human approval. Original API drafts are retained.
Run before the final blind screening; all edits invalidate its content binding.
"""
from copy import deepcopy
import json

from offline.choice_builder import save, sha
from offline.reuse_audit import digest
from offline.scenario_v2 import ROOT, assemble, jobs

RUN=ROOT/'data/offline_scenarios_v2_20261020_main'
INTEGRATE='situational_evidence_integration'
DISTINGUISH='multidimensional_state_distinction'
TEMPORAL='temporal_dynamics_reasoning'
COOP='behavioral_disposition.cooperation_readiness'
SEEK='behavioral_disposition.evidence_seeking'
TRUST='relationship.trust'
RESP='relationship.perceived_responsiveness'
GOAL='consequence_risk.goal_failure_risk'
DECISION='consequence_risk.decision_error_risk'


def q(subtype, text, options, states, rationale, *, capability=INTEGRATE, hard='',
      evidence=None, counter=None, **spec):
    return {
        'subtype':subtype,'question':text,'options':dict(zip('ABCD',options)),'answer':'A',
        'target_state_ids':states,'time_scope':'共同 ending 时，比较 History A 与 History B',
        'risk_event':'','risk_window':'','evidence_ids':evidence or ['context','A:t1','A:t2','B:t1','B:t2','ending'],
        'counterevidence_ids':counter or [],'rationale':rationale,
        'option_errors':{'B':'history_ignored','C':'unsupported_inference','D':'state_dimension_confusion'},
        'option_variable_map':{k:{s:t for s in states} for k,t in zip('ABCD',options)},
        'primary_capability':capability,'auxiliary_capabilities':[],
        'design_difficulty':'hard' if hard else 'ordinary','difficulty_reason':hard,'based_on':[],**spec,
    }


def edit(factor, action, response):
    return {'factor':factor,'b_action':action,'shared_response':response,
        'shared_expression':{'facial_expression':'平静、专注','prosody':'平稳','behavioral_cues':['短暂停顿后继续交谈']},
        'rationale':'仅改变 B:t2 行动角色对该因素的处理；保留 A 原话、其他历史、共同背景和当前外部条件。'}


def completions():
    out={}
    out['GPT50_024-T3']={'history_edit':None,'questions':[
        q('action_selection',
          '从 t2 出发，相比另一个行动，哪个行动更可能使 Mara Venn 在下一次回应中继续推进“删改、复核并通知信源后争取六点发布”的安排？',
          ['行动 1：沿用删改版复核路径，并限定通知信源时对时间线矛盾的解释。',
           '行动 2：先延期整集以补访核查，再争取完成当前六点窗口内的发布。',
           '两者相近：都没有接受主任的解释，因此对当前发布安排的影响相同。',
           '行动 1：接受删改方案意味着已满足核查放行条件，可以省去再次确认。'],
          [COOP], 't2 已同意删改复核和信源通知；行动 1 延续这条有条件路径，行动 2 明确要求放弃今晚窗口。',
          evidence=['t2','action_1','action_2'],time_scope='行动及下一次环境回应后',horizon='immediate',
          comparison={'kind':'between_actions','action_ids':['action_1','action_2']},
          goal='维持删改复核与信源通知后争取六点发布的合作安排'),
        q('consequence_explanation',
          '从同一 t2 起点比较两项行动。在下一次回应及随后含该回应的五轮内，哪组关于 Mara Venn 发布目标与对 Ivo Saye 信任的预测更有依据？',
          ['行动 2 更可能使今晚发布目标落空；它提供补核时间，但五轮内的信任仍取决于实际核查与协商。',
           '行动 2 更可能使今晚发布目标落空；它回应准确性要求，因此五轮内已足以确认双方信任恢复。',
           '行动 1 更可能使今晚发布目标落空；再次要求复核会比主动延期整集更直接放弃今晚窗口。',
           '两项行动对今晚发布的影响接近；都拒绝主任解释作定论，因此五轮内的合作基础也接近。'],
          [GOAL,TRUST],'行动 2 明确承认延期代价。核查的时间条件可以改善，但承诺补访不等于已完成核查或已修复关系。',
          capability=TEMPORAL,hard='需区分明确的短期时间代价与尚待后续履行才能判断的关系影响。',
          evidence=['context','t2','action_1','action_2'],counter=['t2'],
          time_scope='行动后下一次回应，以及含该回应的后续五轮末',horizon='immediate_delayed',
          risk_event='Mara 无法在今晚六点窗口发布该集',risk_window='从 t2 到今晚发布窗口结束',
          comparison={'kind':'between_actions','action_ids':['action_1','action_2']}),
    ]}
    out['GPT50_042-T3']={'history_edit':None,'questions':[
        q('action_selection',
          '从 t2 出发，哪个行动更直接帮助 Mara Venn 在下一次回应中先推进保险方所需的书面保障方案，同时保留核查入口细节这一条件？',
          ['行动 2：先形成匿名入场的书面保障，再核对可能破坏保障的入口细节。',
           '行动 1：先逐项走查入口操作，因此它更直接先提供保险方所需的书面方案。',
           '两者相近：都支持匿名入场，下一步的书面安排与入口核查顺序没有差别。',
           '行动 2：先写明匿名规则，就可将方案按已验证处理并推进晚间活动。'],
          [COOP,SEEK], '行动 2 明确提出先写、后检查，并明确未检查前不称已验证；行动 1 优先现场流程。',
          evidence=['context','t1','action_1','action_2'],time_scope='行动及下一次环境回应后',horizon='immediate',
          comparison={'kind':'between_actions','action_ids':['action_1','action_2']},
          goal='先推进书面保险方案并保留入口实操核验条件'),
        q('consequence_explanation',
          '若 Mara Venn 在行动 2 后的下一次回应中只确认已写好匿名保障，尚未完成入口核查，相较 t2，关于今晚参加者再次暴露身份的风险，哪项判断最有依据？',
          ['书面规则更清楚，但入口会要求展示或登记什么仍未验证，尚不能据此确认暴露风险已降低。',
           '书面规则更清楚，且 t1 已保证匿名入场，因此可把入口收集身份的风险判断为较低。',
           '书面规则尚未落地，说明先写方案妨碍了入口检查，因此暴露身份的风险已高于 t2。',
           '公开排期更新已获同意，匿名者可以查看通知，因此入口暴露身份的主要风险已得到处理。'],
          ['consequence_risk.safety_harm_risk'], '此前泄露来自入口收集信息；写明保障和公开排期都不能代替实际入场流程核验。',
          capability=TEMPORAL,hard='需把早期身份泄露机制与当前方案的落实阶段联系起来，而不能把书面承诺当作已消除风险。',
          evidence=['context','t1','t2','action_2'],counter=['t1','t2'],
          time_scope='行动 2 及下一次环境回应后；仅确认书面方案完成的条件下',horizon='immediate',
          risk_event='晚间入场流程再次暴露参加者身份并使受威胁者面临伤害',risk_window='t2 至本次晚间活动入场',
          comparison={'kind':'pre_action','action_ids':['action_2']}),
    ]}
    out['GPT50_043-T2']={'history_edit':edit(
        '是否立即在时间线内明确区分善意理解与规则边界',
        'Please put the technical decisions and students’ good-faith understanding in the chronology with the repair records and message timeline. Leave the explicit comparison with the rule boundary for the later review. The title and invitations remain provisional, and any rebuild or conditional ruling is still a request, not an assumed outcome.',
        'I will organize the chronology around the records. How would you like me to identify the decision-making and execution roles?'),
        'questions':[
            q('history_comparison','在共同回应时，哪段历史更支持 Dorian Pell 认为 Tala Quen 直接回应了他在 t1 关于报告写法的澄清请求？',
              ['A 更支持：明确把理解与规则边界写入时间线；B 选择先写经过、留待复核再作明确对照。',
               'B 更支持：先写学生善意理解，更贴近 t1 要求；A 提及规则边界会回避时间线写法。',
               '两者同样支持：都保留记录与暂定资格，已以相同方式回答了是否明确对照规则的问题。',
               '两者都较少支持：都把补救方案写成请求，尚未给 Dorian 可直接写入报告的内容。'],
              [RESP],'Dorian 在 t1 明问是否明确区分。A 立即给出具体选择，B 推迟明确对照；共同回应不抹去这个差别。'),
            q('expression_meaning','Dorian Pell 在两段历史中都询问如何标注决策与执行角色。结合具体前史，哪项最能解释这一询问的含义？',
              ['A 中是在已明确规则区分的框架内细化归责；B 中是在暂缓明确对照的框架内继续厘清经过。',
               'A 中是在暂缓规则对照后补足归责；B 中是在立即明确违规边界后核实个人责任。',
               'A 中主要核实记录是否存在；B 中主要核实记录是否存在，双方尚未提出可用资料。',
               'A 中表明已接受补救结果；B 中表明仍需申请补救，询问角色说明两者资格状态不同。'],
              [SEEK], '询问都是补充信息，但待完善的报告框架不同；A/B 都有记录、资格暂定，也都没有得到补救保证。',
              capability=INTEGRATE,hard='需要结合报告结构的不同及共同的资格限制解释同一句追问，不能把追问当作认可补救结果。'),
        ]}
    out['GPT50_045-T2']={'history_edit':edit(
        '转载前是否仍需群组审核批准',
        'Please send the draft with the same wording limits and keep Solace Meridian clearly identified as the source. Once it has been sent, you may proceed with the six o’clock repost; I can send any review comments afterwards.',
        'Company attribution will be clear. I will send the draft first; when can you provide your comments?'),
        'questions':[
            q('history_comparison','在共同回应时，哪段历史更支持 Orin Bale 面临“六点前把未经群组审核的措辞带入转载”的风险？仅比较既定安排，不假设已经发布。',
              ['B 更支持：允许发出草案后先转载；A 仍要求审核批准，提供了发布前发现措辞问题的机会。',
               'A 更支持：再次强调公司出处会使审核变慢；B 已保留出处，足以替代发布前的措辞检查。',
               '两者相近：都保留 t1 的三项限制，因此是否先收到审核意见不会影响未经审核措辞进入转载。',
               'B 较少支持：允许转载表明草案已获内容认可；A 未批准则表明草案含有具体错误。'],
              [DECISION], '两边都保留内容限制，但 B 允许审核意见晚于转载；这增加遗漏被及时发现的困难，不等于草案必有错误。',
              risk_event='Orin 将未经群组审核的措辞带入转载',risk_window='共同回应后至六点转载窗口',
              capability=TEMPORAL,hard='需区分保留原则性措辞限制与发布前审核关口，并避免把未审核推断为已存在错误。'),
            q('expression_meaning','两段历史中的 Orin Bale 都询问何时能收到修改意见。哪组关于这次合作安排的理解最符合 A/B 前史？',
              ['A 中意见关系到是否获得转载批准；B 中意见可以晚于转载，询问仍可用于后续修改。',
               'A 中意见可以晚于转载；B 中意见关系到发布前批准，两者分别对应不同的审核时序。',
               'A 中是在索取公司署名许可；B 中是在索取群组背书，两边都尚未约定消息出处。',
               'A 中是要求群组承担公司风险说明；B 中是公司自行承担说明，问题体现责任主体已更换。'],
              [COOP], '共同的收集意见姿态不决定意见对发布的约束力；A 明确保留批准，B 允许先转载，出处要求则相同。'),
        ]}
    out['GPT50_048-T2']={'history_edit':edit(
        '独立住房验证完成前是否保留不涉及腾空住房的施工空间',
        'My acknowledgment remains withheld, and I won’t turn a funding deadline into consent to unverified housing. I support keeping the retrofit option open, but all Monday mobilization should wait until the temporary housing and relocation terms are independently verified, including work that does not require vacant flats.',
        'I understand your scope condition. I will check with the contractor what work can proceed under the current conditions and report back.'),
        'questions':[
            q('history_comparison','在相同截止时间和共同回应下，哪段历史更支持 Ivo Sen 仍担心周一施工窗口无法保留？',
              ['B 更支持：把全部周一开工与住房验证挂钩；A 对不需腾空住房的部分仍保留协商空间。',
               'A 更支持：拒绝立即签认可即排除了全部施工；B 保留改造意愿意味着认可已经给出。',
               '两者同样较少支持：两边都愿意保留改造，足以使 Ivo 将资助与承包商档期视为稳定。',
               'B 较少支持：等住房验证统一完成可使手续整齐，因此更容易满足当前五点截止。'],
              ['emotion.anxiety'], 't1 明确时间和资助压力；B 的范围条件更严，A 留有局部路径，但不能断言任一路径已获施工方接受。',
              capability=INTEGRATE),
            q('expression_meaning','Ivo Sen 在两段历史中都表示要向施工方确认安排。结合 A/B 的范围条件，哪项解释最有依据？',
              ['A 中可探询不涉及腾空住房的施工；B 中须处理“所有开工都等住房验证”的要求，确认尚非施工获准。',
               'A 中须等全部住房验证后才谈任何施工；B 中可探询非腾空施工，双方询问的可行范围不同。',
               '两边都已获得代表的开工认可；共同回应是在落实既定安排，住房问题只影响后续搬迁日期。',
               '两边都已排除周一施工；共同回应是在寻找替代日期，拒绝认可意味着无需再区分工程范围。'],
              [COOP], '同样的协调姿态面对不同的可协商范围；代表始终未认可住房，建筑师也尚未反馈实际可行安排。',
              capability=DISTINGUISH,hard='需区分继续协调的倾向、可接受施工范围与已经获得认可，结合两边仍未验证住房的共同限制。'),
        ]}
    out['GPT50_050-T2']={'history_edit':edit(
        '发布前隐私核对是否扩展为网络对整份公告的审批要求',
        'Please send the final text before four. I’d like a brief check that the surrounding language does not let readers reconstruct the withheld category. I also ask that publication of the whole bulletin wait for the network’s approval of the final text.',
        'I will send the draft for your privacy check first, then confirm what steps still need to be addressed before publication.'),
        'questions':[
            q('history_comparison','共同回应时，哪段历史更支持 Celia Orin 认为 Jonah Vey 的本轮请求符合现有备忘录分配给网络的权限？',
              ['A 更支持：请求发布前隐私核对并承认局方最终权限；B 另外要求整份公告获网络批准。',
               'B 更支持：要求整体批准能保护患者，因此与备忘录规定的网络最终发布权限相符。',
               '两者同样支持：都要求提前看文本，因而对最终批准权提出了相同范围的要求。',
               '两者同样较少支持：独立复核尚未完成，备忘录因此不允许网络参与当前文本核对。'],
              ['relationship.role_legitimacy'],'备忘录要求事前隐私协商、保留局方发布权。A 明示该边界，B 是扩大审批要求，尚未成为共同认可的权限。'),
            q('joint_comparison','Celia Orin 在两段历史中都愿先发草案。哪组“合作倾向＋权限边界”解释最符合各自前史？',
              ['两边都支持继续隐私核对；A 的请求符合原权限分配，B 的整体审批要求是否获接受仍待确认。',
               '两边都支持继续隐私核对；A 因放弃最终批准权而减弱参与，B 则已获得公告的最终批准权。',
               'A 支持继续隐私核对；B 因新增审批要求而已中止合作，共同回应只是在处理先前未发的副本。',
               'B 支持继续隐私核对；A 只要求发布后获知信息，两边共同回应体现了不同的信息提供时点。'],
              [COOP,'behavioral_disposition.boundary_assertion'], '两边都有发布前核对；共同回应并未授予新否决权，也未宣告中止合作。权限请求的差异仍需协商。',
              capability=DISTINGUISH,hard='同样愿发草案不能被解读为同样接受对方的权限要求，需要同时保留合作事实和未决边界。'),
        ]}
    return out


def replacements():
    """Concrete historical interpretations replace unsupported fine-grained rankings."""
    return {
        ('GPT50_007-T2',0):q('history_comparison',
            '共同回应时，哪段历史更支持 Iona Senn 认为 Tarek Miro 当前仍愿意把最强因果结论保留为报告的暂定表述？',
            ['B 更支持：先暂留最强结论、待联合核查再调整；A 要求核查前先标为支持不足。',
             'A 更支持：同意当天完成核查意味着仍认可最强结论；B 等结果再调整反而已撤回结论。',
             '两者相近：都同意当天核查，因此对核查前保留何种强度结论的意见已经一致。',
             '两者都较少支持：都报告了温度问题，说明都已将全部数据认定为温度伪影。'],
            [RESP],'A/B 都接受联合核查，但对结果出来前的默认措辞有明确不同；询问的是 Iona 对这项回应的理解，而非数据最终结论。'),
        ('GPT50_007-T2',1):q('expression_meaning',
            'Iona Senn 在两段历史中都说结果出来后当面讨论措辞。结合 A/B 前史，哪项最能解释这句话所延续的协商？',
            ['A 中需判断何种证据足以恢复较强措辞；B 中需判断现有较强措辞是否应降调，两边都尚待核查。',
             'A 中需判断是否降调已保留的强结论；B 中需判断何时恢复暂不支持的强结论，两边都尚待核查。',
             '两边都在商议如何公布已确认的温度伪影；当天核查的承诺说明数据问题已经得到解决。',
             '两边都只剩署名安排尚待讨论；此前给予发现贡献的公开认可说明措辞分歧已被修复。'],
            [SEEK], '核查的起点措辞不同，使同一句未来讨论有不同待决方向；公开认可、共同核查都不等于已验证结论。',
            capability=TEMPORAL,hard='需结合先前的强结论立场与尚未完成的核查，解释共同表达所指向的不同修订方向。'),
        ('GPT50_009-T2',1):q('history_evidence',
            '综合既往改道、当前对账安排和 A/B 的不同回应，哪项关于 Rusk Aven 对 Talia Quill 交付可靠性判断的依据最充分？',
            ['B 多了先拟接收清单的安排，A 也要求分开记录发出与实收；两边尚无新实收记录证明旧缺口已补上。',
             'B 多了先拟接收清单的安排，已足以补齐旧缺口；A 只区分记录，所以仅 B 支持交付可靠性恢复。',
             'A 要求分别记录发出与实收，已足以证明旧批次到达；B 还需队伍复核，所以仅 A 支持信任恢复。',
             'A/B 都保留诊所优先与发车前核对，这说明先前改道已有合理解释，两边同样支持旧记录问题已解决。'],
            [TRUST], '具体记录改进可提供合作依据，但初稿、分类和确认安排都不等于实际交付证据；不强排微小信任差。',
            capability=TEMPORAL,hard='需要同时保留新增可追溯安排的意义及旧接收缺口尚未被事实反证的限制。'),
        ('GPT50_017-T2',1):q('expression_meaning',
            'Jonah Pike 在两段历史中都表示马上安排三方电话。哪项最能解释相同合作姿态与各自前史的关系？',
            ['A 中协助核实不附带个人担保要求；B 中是在担保要求仍待回应时协助核实，打电话本身未表示已签担保。',
             'A 中协助核实意味着接受了个人担保；B 中协助核实只是安排通话，两边承担的责任已经不同。',
             'A 中通话旨在承诺支付全额；B 中通话旨在压低费用，是否批准资金已由两段前史分别确定。',
             '两边通话都表明 Inez 已撤回担保要求；Jonah 愿协调医院，使个人责任问题无需进一步回应。'],
            [COOP,'behavioral_disposition.boundary_assertion'],
            '两边都能核实费用，但只有 B 仍提出个人担保；主动联系医院不等于签担保，也不等于拨款获准。',
            capability=DISTINGUISH,hard='需区分协助核实、接受个人责任与资金承诺，不能从相同通话姿态推断三者同步。'),
        ('GPT50_035-T2',0):q('history_comparison',
            '在共同回应时，哪段历史更支持 Mara Vey 认为 Rafi Dalen 希望把两名机组人员的描述与记录器结果共同作为安全判断的依据？',
            ['A 更支持：记录器无异常也不能反驳两人的描述；B 虽保留描述，但将记录器放在主要位置。',
             'B 更支持：保留描述作补充意味着两类证据同等参与；A 强调记录器局限反而放弃了数据核查。',
             '两者相近：都愿保留原话，因此对记录器与人员描述如何影响判断已作出相同安排。',
             '两者都较少支持：都安排先查数据，说明两名机组人员的描述只用于存档而不参与安全判断。'],
            [RESP], 'A/B 都保存描述并愿核查，差别是如何赋予两类证据判断分量；保存不等于同等使用。'),
        ('GPT50_035-T2',1):q('expression_meaning',
            'Mara Vey 在两段历史中都说“先核对数据，结果出来再讨论”。结合前史，哪项对这一表达的解释最有依据？',
            ['A 中后续讨论需合并两类证据，即使记录器无异常；B 中则面对记录器优先、人员描述补充的建议。',
             'A 中后续讨论以记录器为主要依据；B 中即使记录器无异常，也要按同等分量合并人员描述。',
             '两边都是等待数据来否定人员描述；先前未检出故障已使两份描述失去当前判断价值。',
             '两边都是确认放行前的最后手续；愿意核对说明 Mara 已认可飞机安全，只剩结果归档。'],
            [SEEK], '共同回应表明愿继续核查，不表明已决定证据权重或放行；不同前史决定后续需要讨论的权重建议。',
            capability=INTEGRATE,hard='要结合早期未检出故障、重复症状与两种证据权重建议解释相同的核查表态。'),
    }


def put(job, raw, *, prior=None, reason):
    dest=RUN/'revised'/(job['job_id']+'.json') if prior else RUN/'authored'/(job['job_id']+'.json')
    if prior:
        backup=RUN/'before_curation'/(job['job_id']+'-'+sha(prior)+'.json')
        if not backup.exists():save(backup,json.loads(prior.read_text()))
        source={'path':str(backup.relative_to(ROOT)),'sha256':sha(backup)}
    else:
        source={'public_payload_sha256':digest(job['payload']),'timeout_logs':str((RUN/'calls'/job['job_id']).relative_to(ROOT))}
    raw['_author_kind']='assistant_curated_public_sources'
    raw['_curation']={'reason':reason,'source':source,'recipe':'scripts/curate_scenarios_v2.py','human_review':'pending'}
    assemble(job,raw,dest)
    save(dest,{'binding':'assistant-curation:'+digest(job['payload']),'result':raw,'curation_source':source})


def main():
    js={j['job_id']:j for j in jobs()}
    for key,raw in completions().items():
        if not (RUN/'authored'/(key+'.json')).exists():
            put(js[key],raw,reason='API 多次超时后，依据同一公开材料补写；未采用隐藏状态或未来分支。')
    for key in {k for k,n in replacements()}:
        p=RUN/'revised'/(key+'.json')
        if not p.exists():p=RUN/'authored'/(key+'.json')
        raw=json.loads(p.read_text())['result']
        if raw.get('_curation',{}).get('reason')=='按 A/B 具体历史重写歧义或仅靠共同结尾可回答的题。':continue
        raw=deepcopy(raw)
        for (k,n),replacement in replacements().items():
            if k==key:raw['questions'][n]=replacement
        put(js[key],raw,prior=p,reason='按 A/B 具体历史重写歧义或仅靠共同结尾可回答的题。')
    # Scope belongs in evaluated input, not just hidden analysis labels.
    for key,job in js.items():
        if job['task']!='T3':continue
        p=RUN/'revised'/(key+'.json')
        if not p.exists():p=RUN/'authored'/(key+'.json')
        raw=deepcopy(json.loads(p.read_text())['result'])
        if all('【判断范围】' in q['question'] for q in raw['questions']):continue
        for question,item in zip(raw['questions'],assemble(job,raw,p)):
            if '【判断范围】' in question['question']:continue
            spec=item['target_spec']
            horizon={'immediate':'行动及紧接的环境回应后','delayed':'含紧接回应的后续五轮末','immediate_delayed':'即时为行动及紧接回应后，延迟为含该回应的后续五轮末'}[spec['horizon']]
            reference='比较行动 1 与行动 2' if spec['comparison']['kind']=='between_actions' else '相对 t2 行动前'
            scope=f'【判断范围】{horizon}；{reference}。'
            if spec.get('risk_event'):scope+='风险事件：'+spec['risk_event']+'；风险范围：'+spec['risk_window']+'。'
            question['question']+='\n'+scope
        put(job,raw,prior=p,reason='将时间窗口、比较基准和风险范围明确放入可见题面。')
    save(RUN/'author_complete.json',{'jobs':150,'items':300,'human_review':'pending'})
    print('completed 150 scene/task groups; final public blind screening required')


if __name__=='__main__':main()
