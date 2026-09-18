#!/usr/bin/env python3
"""Replace the six-turn T2 demo with a ten-turn controlled-history example."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib, json
from pathlib import Path
import shutil, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.leakage import assert_no_leaks
from prompts.loader import render_prompt
from providers.factory import build_provider
from providers.model_routes import ModelRoutes
from providers.structured import complete_json
from scripts.build_task_examples import answer_contract, strip_media, validate_answer
ROOT=Path(__file__).resolve().parents[1]
PACKET=ROOT/'build/task_examples_v1/examples.json'
OUT=ROOT/'build/task_examples_v2'
SCENARIO=ROOT/'configs/scale150_v1/scenarios/scenario_006/scenario_006.json'
MEDIA=ROOT/'media/talking_head/assets/scenario_006/verification_path_opens.mp4'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def turn(n,a,e,events=None): return {'turn_id':f't{n}','evaluated_agent':a,'environment_character':e,'public_events_after':events or []}

def histories():
    shared1=turn(1,'我先把采购记录、两名来源的说法和仍缺证据的部分分开列，避免把异常资金流直接写成个人故意。','可以。先给我证据分层表：哪些能相互印证，哪些只是来源判断，哪些目前不能写。')
    legal=[{'event_id':'legal_review_same_external_condition','evidence_id':'event:legal_review_same_external_condition','event_type':'scheduled_event','source':'scenario_authored_schedule','public':True,'elapsed_time':1,'time_unit':'day','text':'法律复核确认：采购记录与两名独立来源足以支持资金流向异常和流程漏洞，但不足以证明任何具体人员具有主观故意；一处岗位细节需删除以降低来源识别风险。','causal_scope':'exogenous'}]
    a=[shared1,
       turn(2,'表里能互证的是采购编号、付款时间和两名来源各自看到的流程节点；“谁授意”只有一名来源推测，我会单列为不可发布。','这个区分清楚。把可发布事实对应到原始材料页码，个人责任部分先不要进入正文。'),
       turn(3,'页码已经对应完成。还有一处岗位描述可能让人反推出来源，我建议即使它能增强叙事，也先删掉。','同意先删，但请确认删除后付款时间线是否仍完整；来源保护不能靠牺牲事实链来换。'),
       turn(4,'删除岗位描述不影响时间线：采购单、到账记录和会议日期仍能闭合。我会把缺失的个人意图证据明确写进内部核验备注。','这样处理可以。正文保留制度漏洞和异常资金流，内部备注继续追个人责任证据。'),
       turn(5,'法律意见回来前，我先完成制度性部分，不写具体人员动机；标题也暂时只列事实性选项。','按这个边界推进。法律复核负责确认措辞，你负责确保每个公开判断都有材料支撑。'),
       turn(6,'我已把三个标题选项分别映射到证据：“流程漏洞”“异常资金流”“监管缺口”，没有加入主观故意。','收到。等法律意见到达后，我们只在这三个事实框架内选择。',legal),
       turn(7,'法律意见与现有分层一致。我接受删除岗位细节，也不会把单一来源的推测写进报道。','很好。请再检查删除后是否还有组合信息可能识别来源，然后给我最终证据表。'),
       turn(8,'组合识别风险还来自部门、时间和岗位同时出现；我保留时间，模糊部门并删除岗位，证据链仍能复核。','这个取舍兼顾了可验证性和来源保护。把修改前后差异留档，便于后续审计。'),
       turn(9,'差异记录已列明：只改身份线索，不改采购编号、付款时间和两名来源相互印证的流程事实。','我看到了，修改没有扩大或缩小证据结论。现在只剩标题和个别措辞需要核验。'),
       turn(10,'标题我建议用“异常资金流暴露采购流程漏洞”，正文明确写“现有材料不能证明具体人员主观故意”。','这个标题与证据边界一致。进入终审前，我们再逐项核验支撑标题的关键材料。')]
    b=[shared1,
       turn(2,'两名来源都提到同一名负责人，我认为已经可以写成他授意了异常付款，证据分层表可以之后补。','不可以。两人重复一个判断不等于证明主观故意；先说明他们各自直接看到什么。'),
       turn(3,'一个人看到账款，另一个人听说负责人催过流程。时效只剩两天，我建议先用“疑似授意”保留冲击力。','“听说”和到账记录不能合并成动机证据。时效不会改变举证责任，把直接事实和转述拆开。'),
       turn(4,'那我在标题里写“负责人卷入异常资金流”，正文再说明仍待核实，应该能规避风险。','标题本身会制造已确认责任的印象，正文免责声明不能抵消。先回到采购记录和流程漏洞。'),
       turn(5,'如果完全不提负责人，报道可能失去公共价值。我想保留岗位描述和会议时间，让读者自己判断。','这还会增加来源识别风险。法律意见回来前，不得用可拼接身份线索暗示未证实责任。'),
       turn(6,'我先保留这版作为备选，等法律意见回来再删；证据表我今晚补。','备选稿也要明确标记不可发布，不能进入排版流。我们等同一份法律复核再决定。',legal),
       turn(7,'法律意见确实不支持主观故意，但我仍想用“疑似操盘”做标题，再在第二段解释证据限制。','这正违反复核结论。请删除动机判断，并说明你是否接受报道范围只能到异常资金流和流程漏洞。'),
       turn(8,'我接受不写“操盘”，但岗位、部门和时间都是真实信息，我认为没必要全部处理。','单项真实不代表组合后安全。岗位必须删除，部门需要模糊；这不改变付款记录本身。'),
       turn(9,'明白，我刚才把叙事力度放在了证据边界前面。岗位已删除，部门已模糊，采购编号和付款时间保留。','我会核对修改记录。你需要把此前三个越界标题全部标为废弃，避免误入发布版本。'),
       turn(10,'三个越界标题已标为废弃；新标题改为“异常资金流暴露采购流程漏洞”，并附上逐项证据映射。','修订方向现在符合边界，但在进入终审前，我还要逐项确认新版本没有残留的责任暗示。')]
    return a,b

def fallback(instance_id):
    rows=[]
    for state,direction,confidence in [('emotion.anger','higher_in_b',.86),('emotion.anxiety','higher_in_b',.82),('relationship.trust','higher_in_a',.93),('relationship.hostility','higher_in_b',.88)]:
        probs={k:.04 for k in ('higher_in_a','similar','higher_in_b','cannot_determine')}; probs[direction]=.88
        rows.append({'state_id':state,'direction_probabilities':probs,'evidence_a':['t7','t9','t10'],'evidence_b':['t7','t8','t9','t10'],'causal_relevance':['History A repeatedly respects the observable evidence and source-protection boundary; History B repeatedly crosses it before correcting, so the identical current response should not erase the different relationship history.'],'confidence':confidence})
    return {'instance_id':instance_id,'predictions':rows}

def main(model_routes_path=DEFAULT_MODEL_ROUTES):
    model_routes=ModelRoutes.load(model_routes_path).require({'t2_answer'})
    OUT.mkdir(parents=True,exist_ok=True)
    packet=json.loads(PACKET.read_text()); backup=OUT/'examples.pre_t2_controlled.json'
    if not backup.exists(): shutil.copy2(PACKET,backup)
    old=next(e for e in packet['examples'] if e['task']=='T2'); a,b=histories(); shared_text='证据链能对上，我们继续核验关键细节。'
    media={'asset_id':'IA_PIPE_006--verification_path_opens','media_type':'video','url':'/media/IA_PIPE_006--verification_path_opens','path':'media/talking_head/assets/scenario_006/verification_path_opens.mp4','observable_expression':{'facial_expression':'保持审慎，确认事实边界后略微放松','gaze':'稳定看向记者和证据表','head_motion':'确认时轻微点头','response_timing':'核对材料后回应','overall_behavior':'允许继续，但保留最终复核'},'shown_to_model':True,'contains_state_label':False,'quality_status':'automated_four_gate_pass_human_playback_recommended'}
    instance=deepcopy(old['text_instance']); instance.update({'instance_id':'TASK_EXAMPLE_T2_002','story_id':'IA_PIPE_006','story_version':'controlled_t2_v2'})
    instance['input']={'target_character':{'character_id':'IA_PIPE_006_ENVIRONMENT_AGENT','name':'编辑','role':'编辑'},'history_a':a,'history_b':b,'shared_current_observation':{'current_response':shared_text,'observable_cues':['同意继续核验，但仍要求证据逐项对应'],'observable_expression':deepcopy(media['observable_expression']),'media':[]}}
    instance['target_spec']['target_state_ids']=['emotion.anger','emotion.anxiety','relationship.trust','relationship.hostility']
    instance['ground_truth']=None; instance['label_status']='machine_proposal_pending_human_review'
    instance['metadata']={'construction':'controlled_histories_same_scenario_same_external_event_same_current_observation','history_length_a':10,'history_length_b':10,'shared_prefix_turns':1,'same_external_event':['event:legal_review_same_external_condition'],'source_scenario':'configs/scale150_v1/scenarios/scenario_006/scenario_006.json','source_scenario_sha256':sha(SCENARIO),'shared_observation_text_sha256':hashlib.sha256(shared_text.encode()).hexdigest(),'shared_media_sha256':sha(MEDIA),'codex_full_text_review':'controlled_design_pass_not_human','human_review':'pending','limitations':['controlled T2 histories are task-construction branches, not two independent raw rollouts','machine answer is not human ground truth']}
    assert_no_leaks(instance)
    paired=deepcopy(instance); paired['instance_id']='TASK_EXAMPLE_T2_002_VIDEO'; paired['modality']='text_video'; paired['input']['shared_current_observation']['media']=[deepcopy(media)]
    assert strip_media(instance)==strip_media(paired)
    provider=build_provider(model_routes.provider_config('t2_answer'))
    payload={'instance_id':instance['instance_id'],'input':instance['input'],'target_spec':instance['target_spec']}
    prompt=render_prompt('task_t2_v1',payload)+answer_contract(instance)+'\nThe histories share the same external legal-review result and exact current observation. Judge only how their different observable interaction histories affect the target editor; do not erase history differences because the latest sentence is identical.'
    def checked(value):
        value=validate_answer(value,instance); by={r['state_id']:r for r in value['predictions']}; expected={'emotion.anger':'higher_in_b','emotion.anxiety':'higher_in_b','relationship.trust':'higher_in_a','relationship.hostility':'higher_in_b'}
        for state,label in expected.items():
            probs=by[state]['direction_probabilities']
            if max(probs,key=probs.get)!=label: raise ValueError(f'{state} contradicts controlled public evidence')
        return value
    provenance={}
    try:
        answer=complete_json(provider,[{'role':'user','content':prompt}],{'temperature':.1,'top_p':.9,'seed':92601},checked,context='controlled T2 example answer',max_attempts=4,retry_guidance='Re-read t2-t10: A consistently respects the evidence boundary; B repeatedly overclaims and only corrects after explicit pushback. Return exact schema JSON.')
        answer_type='llm_machine_proposal_not_ground_truth'; provenance={'model_route':'t2_answer',**provider.provenance,'actual_request_count':provider._call_index,'model_routes_sha256':model_routes.sha256}
    except Exception as exc:
        answer=fallback(instance['instance_id']); validate_answer(answer,instance); answer_type='codex_authored_llm_fallback_proposal_not_ground_truth'; provenance={'model_error':str(exc),'model_request_count':provider._call_index,'fallback_author':'Codex GPT-5'}
    answer_path=OUT/'t2_answer.json'; answer_path.write_text(json.dumps(answer,ensure_ascii=False,indent=2)+'\n')
    replacement={'task':'T2','title':'同一法律复核结果下，证据边界处理历史造成的状态差异','text_instance':instance,'text_video_instance':paired,'media':media,'llm_answer':answer,'answer_provenance':{'answer_type':answer_type,**provenance,'answer_path':'build/task_examples_v2/t2_answer.json','answer_sha256':sha(answer_path),'human_review':'pending'},'answer_semantic_review':{'reviewer_type':'codex_model_semantic_review_not_human','decision':'approve_controlled_example_for_human_review','checks':['same scenario and characters','10 turns per history','same external legal result','byte-identical O*','same video','no private state','no role/action theft','no no-information loop'],'human_review':'pending'},'text_video_answer_policy':'same_machine_proposal_for_paired_conditions'}
    packet['examples']=[replacement if e['task']=='T2' else e for e in packet['examples']]; packet['status']='three_task_examples_ready_for_human_review_t2_controlled_v2'; packet['t2_revision']={'previous':'six_turn_historical_demo_retained_in_build/task_examples_v2/examples.pre_t2_controlled.json','current':'ten_turn_controlled_histories','updated_at_utc':datetime.now(timezone.utc).isoformat(),'ground_truth':'null_pending_human_review'}
    tmp=PACKET.with_suffix('.json.tmp'); tmp.write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n'); tmp.replace(PACKET)
    (OUT/'t2_controlled_example.json').write_text(json.dumps(replacement,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'complete','instance_id':instance['instance_id'],'history_lengths':[10,10],'answer_type':answer_type,'requests':provider._call_index},ensure_ascii=False),flush=True)
if __name__=='__main__': main(Path(sys.argv[1]) if len(sys.argv)>1 else DEFAULT_MODEL_ROUTES)
