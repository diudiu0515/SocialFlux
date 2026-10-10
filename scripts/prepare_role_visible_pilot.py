"""Prepare six review-only scenario copies, never approve or launch them."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from environment.public_situation import policy_narrative_reference,sanitize_public_text

OUT=ROOT/'data/gpt50/experiment/state_v3_validation/v323_state_judgment_primary/observed_evidence_v6_pilot_preparation'
PLAN=[
    ('gpt','002','gpt',[0,1,2],True,None),
    ('gpt','003','gpt',[0,1,2],True,None),
    ('gpt','026','gpt',[0,1,2],True,
     'At the release deadline, the funeral director asks the family spokesperson to authorize a prepaid direct-cremation plan. Relatives have requested a vigil, a viewing, and inclusion of an excluded relative. The spokesperson knows of the private reconciliation they arranged and promised to keep confidential. A reading of planner notes is scheduled later; its contents and consequences are not yet established in the conversation.'),
    ('claude','030','claude',[0,1,2],False,
     "The new executive director is preparing a revised records-retention policy for board presentation in three weeks and seeks the foundation archivist's endorsement. The draft would authorize destruction of internal correspondence and meeting records older than seven years. The archive spans forty-two years and includes records of a controversial community program and the leadership crisis two years ago. Storage costs, privacy, institutional accountability and record preservation are at issue. The archivist has not yet given the requested endorsement."),
    ('claude','014','claude',[0,1,2],True,
     'Mara and Owen co-founded The Frequency Floor four years ago with a 60/40 ownership split reflecting different financial and operational contributions. A compliance notice requires accessibility upgrades costing $95,000–$120,000 within ninety days, and the lease expires in thirty days. Neither can fund the upgrades alone. Owen has a nonprofit offer that would fund upgrades but require operational control and exclude Mara from management; he has not yet disclosed those conditions. Prior disputes about unilateral decisions and leaked financial information affect the negotiation.'),
    ('claude','044','claude',[1,2,4],False,
     "At a 280-person manufacturing company, HR received an anonymous hotline report about an employee's concerning workplace statements and behavior, without an articulated specific threat. By Monday HR must decide whether to use administrative leave, seek a fitness evaluation, or take no action. The insurance carrier is pressing for tighter workplace-violence protocols after an external incident. HR seeks guidance from the in-house EAP director within professional confidentiality boundaries. HR knows the anonymous caller used workplace-training language, which could reflect an overinterpretation of ordinary frustration. An executive review is scheduled in three weeks. The counselor has not disclosed this employee's clinical history or current care status."),
]

ENVIRONMENT_VIEWS={
    ('gpt','002'):([0,1], 'Before the examination-week deadline, the parent advocate is asking the school counselor for a written access and quiet-reset plan. Committee review is scheduled after the first examinations. The counselor knows a temporary aide and a private room are available. The student and advocate have not disclosed all functional or symptom details to the school.'),
    ('gpt','003'):([0,1,3], 'At a small city paper, the editor is reviewing the reporter\'s procurement-favoritism account before publication and a council vote the next morning. Public records are scheduled for release the following Monday. Counsel told the editor that the source accepted consulting fees from a subcontractor during the bidding period; the editor has not disclosed this finding to the reporter.'),
    ('gpt','026'):([0,1,3], 'At the release deadline, the funeral director seeks authorization of a prepaid direct-cremation order while relatives request alternatives. The director has received a handwritten amendment asking for returning family to have room and for the deceased to be carried to the water; it specifies neither ritual nor timing. A reading of planner notes is scheduled later, but its outcome is not known.'),
    ('claude','030'):([0,1,2], 'The foundation archivist manages forty-two years of institutional records, including material concerning a collapsed community program and the leadership crisis two years ago. The new executive director seeks endorsement of a retention policy authorizing destruction of older records before a board presentation in three weeks. The archivist secured donor-restricted funding intended to preserve lessons from both successes and mistakes. A donor visit is scheduled in four months; no future question or outcome has occurred.'),
    ('claude','014'):([0,1,3], 'Mara and Owen co-founded The Frequency Floor four years ago with unequal capital and operational contributions and a 60/40 ownership split. Required accessibility upgrades cost $95,000–$120,000 within ninety days, while the lease expires in thirty days and neither partner can self-fund the work. Mara holds a corporate lease offer at triple rent requiring vacant possession. She also knows the building owner plans to sell within two years, creating relocation risk; she has not disclosed this to Owen. Owen has a nonprofit alternative, but Mara has not been told its governance conditions.'),
    ('claude','044'):([0,1,3], 'The EAP counselor receives an urgent HR request about a workplace safety concern reported through an anonymous hotline. HR faces a Monday decision on administrative leave, fitness evaluation, or no action. The counselor knows the employee as an established client with a recent personal crisis, consistent engagement, situational anger toward a supervisor, a working safety plan, and a missed appointment. The counselor assesses risk as elevated but manageable and not meeting the imminent-harm threshold for a confidentiality exception. These clinical facts have not been disclosed to HR.'),
}

def augment_role_views(scenario,pool,number):
    history,background=ENVIRONMENT_VIEWS[(pool,number)]
    paths=['relationship_structure','power_structure']+[f'relevant_history.{i}' for i in history]
    scenario['environment_background']=background
    scenario['environment_visible_narrative']=[policy_narrative_reference(scenario,p) for p in paths]
    shared={
        ('gpt','002'):sanitize_public_text(scenario['background']),
        ('gpt','003'):sanitize_public_text(scenario['background']),
        ('gpt','026'):'At the release deadline, the funeral director seeks authorization of a prepaid direct-cremation order while relatives request a vigil, viewing, and inclusion of an excluded relative.',
        ('claude','030'):'The executive director seeks the archivist\'s endorsement of a draft retention policy affecting records older than seven years, before a board presentation in three weeks.',
        ('claude','014'):'The venue co-founders face accessibility upgrades costing $95,000–$120,000 within ninety days and a lease renewal in thirty days. Neither partner can self-fund the work.',
        ('claude','044'):'HR requests guidance on a workplace safety concern within EAP confidentiality boundaries. No clinical information has yet been disclosed in this conversation.',
    }
    scenario['shared_background']=shared[(pool,number)]


def create(path,body):
    if path.exists():
        raise FileExistsError(path)
    patch='*** Begin Patch\n*** Add File: '+str(path)+'\n'+''.join('+'+s+'\n' for s in body.splitlines())+'*** End Patch'
    subprocess.run(['apply_patch',patch],check=True)

def main():
    manifest={'status':'prepared_not_started','human_review_status':'pending','full_scale_authorized':False,
              'notes':['Agent-curated visibility, not human approval','014 and 044 were not used in state-appraiser modification','No short trajectory will be padded; retain natural ending and 20-turn limit'], 'cases':[]}
    for pool,number,policy,history,conflict,background in PLAN:
        source=ROOT/('data/gpt50/experiment/scenario/scenarios_state_v3' if pool=='gpt' else 'data/claude150_v1/scenarios_state_v3')/('scenario_'+number)/('scenario_'+number+'.json')
        scenario=json.loads(source.read_text())
        paths=['relationship_structure','power_structure']+(['goal_conflict'] if conflict else [])+[f'relevant_history.{i}' for i in history]
        scenario['policy_background']=background or sanitize_public_text(scenario['background'])
        scenario['policy_visible_narrative']=[policy_narrative_reference(scenario,p) for p in paths]
        augment_role_views(scenario,pool,number)
        candidate=OUT/'scenarios'/f'{pool}_{number}.json'
        create(candidate,json.dumps(scenario,ensure_ascii=False,indent=2)+'\n')
        all_paths=['relationship_structure','power_structure','goal_conflict']+[f'relevant_history.{i}' for i in range(len(scenario['narrative_design']['relevant_history']))]
        manifest['cases'].append({'scenario_id':scenario['scenario_id'],'policy':policy,
            'source':str(source.relative_to(ROOT)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'candidate':str(candidate.relative_to(ROOT)),'role_visible_paths':paths,
            'withheld_narrative_paths':[p for p in all_paths if p not in paths],
            'policy_background':scenario['policy_background'],'author_background_and_state_unchanged':True})
        manifest['cases'][-1]['environment_background']=scenario['environment_background']
        manifest['cases'][-1]['shared_background']=scenario['shared_background']
        manifest['cases'][-1]['candidate_sha256']=hashlib.sha256(candidate.read_bytes()).hexdigest()
    create(OUT/'manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    lines=['六条影子轨迹：角色可见性准备（尚未运行；待人工审核）','',
           'GPT：学校、新闻编辑、丧葬协商。Claude：机构档案、合伙人协商、EAP/HR 协商。',
           '原始世界背景和初始状态保留；分别整理双方可知事实与共同背景。不冒充人工通过。','']
    for c in manifest['cases']:
        lines.extend([c['scenario_id']+' / '+c['policy'],'policy 可见背景：'+c['policy_background'],
                      '环境角色可见背景：'+c['environment_background'],
                      '初始共同背景：'+c['shared_background'],
                      '可见叙事：'+', '.join(c['role_visible_paths']), '隐藏叙事：'+', '.join(c['withheld_narrative_paths']),
                      '完整候选：'+c['candidate'],''])
    create(OUT/'review.txt','\n'.join(lines))

if __name__=='__main__':
    main()
