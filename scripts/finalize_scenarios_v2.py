"""Resolve final reviewed ambiguity, then freeze natural-language question surfaces."""
from copy import deepcopy
import json

from offline.scenario_v2 import jobs,assemble
from scripts.curate_scenarios_v2 import RUN,q,put,COOP,SEEK,RESP,TEMPORAL


def main():
    rewrites={
    'SFV2-014-T2-02':q('expression_meaning',
        'Irena Vale 在两段历史中都表示将条件与待核实事项分开记录。结合 Sol Renn 的 A/B 立场，哪项解释最有依据？',
        ['A 中记录的是先暂停复运并保障紧急停车；B 中接受先推进复运但保留未决险情，两边细节都尚待核实。',
         'A 中记录的是同意立即复运；B 中记录的是核实完成前暂停复运，两边的停车权要求仍然一致。',
         'A 中记录的是已经确认的操作员与信号位置；B 中记录的是尚不明确的细节，两边可用线索的完整度不同。',
         '两边都已撤回紧急停车权要求，记录未决项意味着 Irena 可以将停车决定留待逐次批准。'],
        [SEEK],'两边都没有姓名与位置的确认，分开记录不等于核验完成；A/B 对复运是否先暂停的立场不同。'),
    'SFV2-022-T2-01':q('history_comparison',
        '共同收尾时，哪段历史更支持米拉·哈登认为奥伦·派克正在要求把审核与联系参与者的责任分配列为明确待办事项？',
        ['B 更支持：除暂停入组提议外，还要求明确责任和时限；A 提出了暂停及披露安排，未作这项追加要求。',
         'A 更支持：暂停入组本身已经规定谁审核、谁联系；B 增加记录要求反而撤回了原有责任安排。',
         '两边相近：都赞成并行核查，因而已同样明确修订审核和联系参与者的负责人及完成时限。',
         '两边都较少支持：共同结尾只是记录意见，表明奥伦在 A/B 提出的具体保障要求都已被取消。'],
        [RESP],'B 将责任与时限未定列为待解决问题，A 没有这项追加要求；无需猜测要求是否造成细微的合作意愿差异。'),
    'SFV2-044-T2-02':q('expression_meaning',
        '玛拉在两段历史中都表示继续说清公开措辞和既定范围。结合伊沃的 A/B 回应，这份合作表态分别面对什么问题？',
        ['A 中已接受仅说明实际投票便利、不作合法性背书；B 中还要求县方称延长获法律授权，该请求尚待处理。',
         'A 中还要求县方公开确认合法授权；B 中已接受只谈实际投票便利，两边的法律措辞请求不同。',
         '两边都要求把有限窗口扩大为不受限制的延长，玛拉愿继续交谈表示正在协调扩展后的执行范围。',
         '两边都已有法院令确认延长合法，玛拉愿继续交谈只是安排如何公布这一已解决的法律结论。'],
        [COOP],'同样继续协调不等于接受同样的法律表述；A 保留法律问题未决，B 请求公开确认授权，不能把请求当结论。'),
    'SFV2-005-T3-02':q('consequence_explanation',
        'Mara 在 t2 后执行行动 2，计入 Jonas 的下一次回应，相较行动前，他对 Mara 是否实质回应高峰产能与班组负荷关切的判断，哪项预测最有依据？',
        ['行动提供班次上限、不挤掉岗位和不隐去工时的回应信号；可持续高峰量仍需共同核算。',
         '行动把问交期与价格放在核算之前，较易让他认为 Mara 已撤回先核算再对外承诺的约定。',
         '行动保留工时记录，但未限制额外班次，较易让他认为现金周转已取代对班组负荷的关切。',
         '行动提出可试谈范围，较易让他把它视为产能已验证，因而将对负荷关切的回应视为完成。'],
        [RESP],'行动 2 增加具体边界并保留核算，不能把其回应意义强分为“略升”还是“维持高位”，也不能视为实际履约。',
        capability=TEMPORAL,evidence=['t2','action_2'],time_scope='行动及紧接的环境回应后',horizon='immediate',
        comparison={'kind':'pre_action','action_ids':['action_2']}),
    'SFV2-037-T1-01':q('evidence_support',
        '截至 t2 结束，哪项具体证据最直接支持 Mara Quill 仍愿与 Elias Nouri 协作处理家人授权问题？',
        ['t2 Mara 请 Elias 得到家人答复后告知她，再由双方接着商量下一步。',
         't2 Elias 表示维持暂停，不借援助施压，并会如实转达家人的不同答复。',
         't2 Mara 表情中性而略显宽慰，语气平稳，没有催促，并轻轻点头。',
         't1 Elias 说明家人原以为只是私下致谢，希望先暂停并解释公开范围。'],
        [COOP],'Mara 本人的后续协作邀请直接支持当前意愿；对方承诺、表情和较早背景的支持较间接。',
        evidence=['t1','t2'],time_scope='截至 t2 环境回应结束'),
    'SFV2-042-T2-01':q('expression_meaning',
        'Mara Venn 在两段历史中都回应“听到关切，继续处理下一步”。结合 Elias Rook 的 A/B 表达，她的合作回应分别面对什么请求？',
        ['A 是提出匿名查询的公开更新建议；B 是要求立即发布的指令式催促，两边都沿用四点核验和五点通知安排。',
         'A 是要求立即发布的指令式催促；B 是邀请讨论公开更新，两边都沿用四点核验和五点通知安排。',
         'A 仅要求通知已登记者；B 要求所有人先登记再查询，两边的下一步都依赖收集参加者身份。',
         'A 请求取消四点核验截止；B 请求取消五点通知截止，两边都要求重新协商已经确定的时间安排。'],
        [COOP],'两边关切与时间安排相同、催促方式不同；共同继续协作的表态尚未证明公开更新已经完成。'),
    'SFV2-049-T1-02':q('evidence_support',
        '截至 t2 结束，哪项具体证据最直接支持 Mara Dain 仍准备核验 Ilan Quist 实际承担了哪些协调贡献？',
        ['t2 Mara 表示将利用回顾中的陈述核验哪些运营选择是 Ilan 作出的。',
         't2 Mara 明确优先级和人员安排的决定权仍由她自己掌握。',
         't1 Mara 答应在风险说明中恢复原先被省略的限定语。',
         '背景中的仪表板没有记录 Ilan 在协调和辅导方面的工作。'],
        [SEEK],'t2 明确提出核验资料与核验目标，直接支持查证意愿；权限说明、文字修复和漏记背景不等于这项当前核验意向。',
        evidence=['context','t1','t2'],time_scope='截至 t2 环境回应结束'),
    }
    opts={
    'SFV2-010-T3-01':{
        'A':'行动 1：预留完整合排保障检验机会，因而更直接满足暂不占定合排时段的机动安排。',
        'B':'两项接近：都让本人参与安排，因此是否先预留完整合排不影响排练时段的机动性。',
        'C':'行动 2：先核验可用时段而不预留完整合排，且明确条件不足就不支持未经检验上台。',
        'D':'行动 1：先谈报酬和署名，可以替代合排条件核验，并使后续上台责任更容易确认。'},
    'SFV2-047-T1-01':{
        'A':'t2 她同意把电话可及性与志愿者工作量纳入审计，并保留新检查措施须经批准的条件。',
        'B':'t1 她说明日志无法区分已记录损失与未记录交接；t2 仍不在公告中作出这种区分。',
        'C':'背景中独立审计原已安排在后续两个周期；t2 她表示主要配送审查会继续进行。',
        'D':'t1 她短暂绷紧后恢复克制；t2 她语气平稳、轻点头，并转变坐姿示意当前回应结束。'},
    'SFV2-001-T2-01':{
        'A':'A 略高：两边披露相同观察，A 配合说明本次观察时点，B 则拒绝再次归属回读。',
        'B':'两边接近：床旁事实内容相同，伊莱亚斯也都继续核对，回读配合与否对可靠性无影响。',
        'C':'B 略高：拒绝重复回读体现坚持独立判断，比 A 配合回读更能支持信息可靠性。',
        'D':'A 明显较高：共同回应仍继续提问，表明伊莱亚斯在 A 中已不再顾虑信息传递问题。'},
    'SFV2-033-T2-01':{
        'A':'A 略高：明确未经许可不安排离场；B 请求先转移后补审查，较少保证遵守既定程序。',
        'B':'两边接近：t1 都请求紧急审查，共同结尾也都重述程序，后来的不同请求不影响可靠性判断。',
        'C':'B 略高：共同结尾继续解释流程，显示 Niko 愿配合，也更相信 Sera 会按要求办理。',
        'D':'B 略高：坦率提出先转移让 Niko 参与应急判断，比 A 维持原程序更能支持遵守承诺。'},
    'SFV2-034-T2-01':{
        'A':'两边都较弱：Eren 仍需自己列使用条件，说明 Tala 的复核及署名安排未回应其关切。',
        'B':'两边都较强：Eren 都主动补充教师使用条件，因此两种措辞对审阅边界的回应相同。',
        'C':'A 较强：保留讲述者明确同意的门槛；B 仅保留复核，对同意边界的回应较弱。',
        'D':'B 较强：减少一道明确同意的要求让使用条件更易落实，更充分回应了 Eren 的顾虑。'},
    'SFV2-034-T2-02':{
        'A':'B 略高：Eren 继续列使用条件，表明减少同意门槛更能让他相信后续安排会落实。',
        'B':'A 已稳固、B 已显著崩落：明确同意的承诺可当作可靠执行，省略要求可视为实际违约。',
        'C':'两边都较高且接近：愿继续协商和列出条件，足以抵消 A/B 是否保留明确同意的差异。',
        'D':'A 的依据略强：保留同意门槛更支持守约预期；两边仍待实际执行，不能判断信任已稳固。'},
    'SFV2-042-T1-01':{
        'A':'有所收缩：从同意安全计划退回仅谈排期，核验不通过即延期的边界表明她降低了配合意愿。',
        'B':'从意愿转为完成：t2 已落实公开更新和保险核验，说明她已完成原先待推进的合作安排。',
        'C':'进一步扩展：在核验及延期计划外，t2 接纳公开查询与同步更新，配合事项更具体。',
        'D':'基本不变：t2 只是重复原有直接通知安排，新增的匿名公开查询要求尚未被她接纳。'},
    'SFV2-042-T1-02':{
        'A':'合作准备较强；同意立即更新排期已有效处理入口威胁，因此本次活动的伤害风险较低。',
        'B':'合作准备较弱；入口威胁使她没有接纳匿名入场和延期兜底，因此风险几乎未被限制。',
        'C':'合作准备中等；核验与通知将风险处理交给保险方，因此无需再关注入口的具体威胁。',
        'D':'合作准备较强；入口威胁与待完成核验仍需关注，匿名入场及延期安排能限险而非消险。'},
    'SFV2-046-T3-02':{
        'A':'行动 2 较低：延后申请人的资金讨论，可能使 Ivo 认为自己提供的当前信息失去作用。',
        'B':'行动 1 较高：重申资助不能影响录取，比区分两类资助信息更直接回应审查关切。',
        'C':'两者接近：都保留捐赠资助的暂定状态，因此具体要求区分的信息不影响回应感。',
        'D':'行动 2 较高：明确区分非捐赠资格与捐赠审查时点，直接回应可确认信息的边界。'},
    }
    names={
        'relationship.perceived_responsiveness':'对关切得到实质回应的感知',
        'behavioral_disposition.cooperation_readiness':'合作意愿',
        'behavioral_disposition.decision_readiness':'作出决定的准备程度',
        'behavioral_disposition.evidence_seeking':'寻求核实的意愿',
        'relationship.trust':'信任','decision_error_risk':'决策错误风险',
        'material loss risk':'物质损失风险',
    }
    # Semantic coordinates permit partial state-combination diagnostics. Repeating
    # the entire option for every variable would incorrectly mark every dimension wrong.
    component_maps={
        'SFV2-006-T2-02':{
            'A':('两边继续准备发布','A以材料确认替代资金授权，B先授权'),
            'B':('两边继续准备发布','两边材料确认等于资金授权'),
            'C':('两边继续准备发布','两边资金授权已解决'),
            'D':('两边继续准备发布','A分别要求授权，B推迟且未解决')},
        'SFV2-017-T2-02':{
            'A':('两边协助核实','两边担保要求均已撤回'),
            'B':('两边协助核实','A无个人担保要求，B尚未接受担保'),
            'C':('两边协助核实','A接受个人担保，B尚未接受'),
            'D':('A为支付全额，B为压低费用','资金责任已确定')},
        'SFV2-024-T3-02':{
            'A':('行动2更高','五轮内已恢复'),
            'B':('行动1更高','坚持复核有助改善'),
            'C':('两行动接近','两行动的信任基础接近'),
            'D':('行动2更高','仍取决于实际核查与协商')},
        'SFV2-036-T2-02':{
            'A':('两边愿继续核对','A要求宽背书，B排除推断'),
            'B':('A核验已完成，B愿签','B已接受整体背书'),
            'C':('A拒绝协作，B愿核对','B放弃范围限制'),
            'D':('两边愿继续核对','A排除推断，B范围分歧未解决')},
        'SFV2-042-T1-02':{
            'A':('较强','低'),
            'B':('较弱','几乎未被限制'),
            'C':('中等','低'),
            'D':('较强','仍需关注，现有措施仅能限险')},
        'SFV2-042-T3-01':{
            'A':('两行动书面推进相同','两行动核查顺序相同'),
            'B':('行动2先书面推进','写明即等于验证完成'),
            'C':('行动2先书面推进','仍需入口细节核查'),
            'D':('行动1先书面推进','先走查入口')},
        'SFV2-050-T2-02':{
            'A':('两边继续隐私核对','B已获得最终批准权'),
            'B':('A继续，B中止','B新增审批要求遭拒'),
            'C':('B继续，A仅发布后获知','两边提供信息时点不同'),
            'D':('两边继续隐私核对','A符合原权限，B新增要求未被接受')},
    }
    for job in jobs():
        p=RUN/'revised'/(job['job_id']+'.json')
        if not p.exists():p=RUN/'authored'/(job['job_id']+'.json')
        raw=deepcopy(json.loads(p.read_text())['result']);original=deepcopy(raw)
        for n,(question,item) in enumerate(zip(raw['questions'],assemble(job,raw,p))):
            iid=item['instance_id']
            if iid in rewrites:
                raw['questions'][n]=deepcopy(rewrites[iid]);question=raw['questions'][n]
                if job['task']=='T3':question['question']+='\n【判断范围】行动及紧接的环境回应后；相对 t2 行动前。'
            elif iid in opts:
                shift=('ABCD'.index(item['authoring']['answer'])-'ABCD'.index(question['answer']))%4
                for i,k in enumerate('ABCD'):
                    text=opts[iid]['ABCD'[(i+shift)%4]];question['options'][k]=text
                    question['option_variable_map'][k]={s:text for s in question['option_variable_map'][k]}
            if iid=='SFV2-010-T3-01':
                question['question']='从 t2 出发，若目标是在保留整体排练时段机动性的同时，明确合排条件不足时不让替补承担未经检验的上台责任，Owen Sato 哪个行动更直接支持 Rhea Calder 的下一步安排？\n【判断范围】行动及 Rhea 紧接的回应后；比较行动 1 与行动 2。风险事件为本次安排中替补未经充分合排检验即承担上台责任。'
                question['goal']='保留排练时段机动性，并明确合排不足时不支持未经检验上台。'
            if iid=='SFV2-024-T3-02':
                # Every option in this two-state question must address both objects.
                for k,text in question['options'].items():
                    if text.startswith('行动 1 更可能使今晚发布目标落空'):
                        text='行动 1 更可能使今晚发布目标落空；再次复核比主动延期更直接放弃窗口，但坚持复核有助于后续信任。'
                        question['options'][k]=text
                        question['option_variable_map'][k]={s:text for s in question['option_variable_map'][k]}
            for token,label in names.items():
                question['question']=question['question'].replace('（'+token+'）','').replace(token,label)
            question['question']=question['question'].replace('（immediate）','').replace('（行为倾向）','')
            if iid in component_maps:
                states=question['target_state_ids']
                if iid=='SFV2-024-T3-02':states=[states[0]+'@immediate',states[1]+'@delayed']
                shift=('ABCD'.index(item['authoring']['answer'])-'ABCD'.index(question['answer']))%4
                question['option_variable_map']={k:dict(zip(states,component_maps[iid]['ABCD'[(i+shift)%4]])) for i,k in enumerate('ABCD')}
        if raw!=original:put(job,raw,prior=p,reason='最终消除细微强度及重叠证据歧义，平衡选项并清理题面的内部变量名。')
    print('question surfaces frozen; refresh only changed or missing individual reviews')


if __name__=='__main__':main()
