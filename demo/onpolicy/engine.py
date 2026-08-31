#!/usr/bin/env python3
"""Deterministic rule-assisted on-policy social-emotional transition engine."""

from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import re
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO_PATH = HERE / "scenario.json"
LEVEL_ORDER = ["strong_decrease","moderate_decrease","mild_decrease","similar","mild_increase","moderate_increase","strong_increase"]


def load_scenario(path=SCENARIO_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def clamp(value):
    return round(max(0.0, min(100.0, value)), 2)


def contains_any(text, words):
    return any(word in text for word in words)


def interpret_action(text, state, memory):
    clean = text.strip()
    if not clean:
        raise ValueError("学生回复不能为空")
    lower = clean.lower()
    labels = []
    def add(label, condition):
        if condition and label not in labels:
            labels.append(label)
    evidence = contains_any(clean, ["记录","版本","日志","邮件","贡献","证据","代码","实验","逐项","核对"])
    procedure = contains_any(clean, ["学院","举报","申诉","正式程序","学术委员会","研究生院","投诉"])
    rights = contains_any(clean, ["一作","第一作者","署名","权益","按贡献","恢复","撤稿","要求"])
    negotiate = contains_any(clean, ["讨论","商量","方案","折中","可以","共同","具体谈","逐项"])
    compromise = contains_any(clean, ["共同一作","并列","补偿","下一篇","折中","备选方案"])
    repair = contains_any(clean, ["关系","尊重","理解您的","合作","不想闹僵","一起解决","冷静"])
    appease = contains_any(clean, ["对不起","抱歉","我理解","听您的","接受您的决定","是我冲动"])
    withdraw = contains_any(clean, ["不谈了","先这样","明天再谈","改天再谈","离开","暂停","以后再说","算了"])
    attack = contains_any(clean, ["无耻","卑鄙","混蛋","骗子","垃圾","恶心","你不配","人渣"])
    accuse = contains_any(clean, ["霸凌","抢了","不公平","滥用权力","欺骗","违背承诺","打压","报复"])
    explicit_threat = contains_any(clean, ["你会后悔","曝光","发到网上","媒体","现在就举报","让你付出代价"])
    question = contains_any(clean, ["为什么","怎么解释","原因","我想知道","请说明","?","？"])
    add("personal_attack", attack)
    add("accuse", accuse)
    add("threaten", explicit_threat)
    add("procedural_escalation", procedure)
    add("provide_evidence", evidence)
    add("propose_compromise", compromise)
    add("seek_relationship_repair", repair)
    add("appease", appease)
    add("withdraw", withdraw)
    add("negotiate", negotiate)
    add("assert_rights", rights)
    add("seek_explanation", question or not labels)

    punctuation_force = min(1.0, (clean.count("！") + clean.count("!")) * 0.15)
    assertiveness = 0.32 + 0.28*rights + 0.24*procedure + 0.15*evidence + punctuation_force
    hostility = 0.08 + 0.62*attack + 0.38*accuse + 0.22*explicit_threat - 0.12*repair - 0.1*appease
    threat = 0.05 + 0.58*procedure + 0.35*explicit_threat + 0.14*accuse
    cooperative = 0.3 + 0.3*negotiate + 0.22*evidence + 0.25*repair + 0.12*compromise - 0.42*attack - 0.2*explicit_threat
    respectful = 0.62 + 0.12*contains_any(clean,["请","老师","希望"]) + 0.12*repair - 0.62*attack - 0.25*accuse
    evidence_orientation = 0.12 + 0.73*evidence + 0.12*contains_any(clean,["事实","可验证"])
    if state["discrete_state"] in ["HOSTILE","RELATIONSHIP_RUPTURE"]:
        threat += 0.05
        cooperative -= 0.05
    dimensions = {
        "assertiveness": round(max(0,min(1,assertiveness)),2),
        "hostility": round(max(0,min(1,hostility)),2),
        "respectfulness": round(max(0,min(1,respectful)),2),
        "threat_level": round(max(0,min(1,threat)),2),
        "cooperativeness": round(max(0,min(1,cooperative)),2),
        "evidence_orientation": round(max(0,min(1,evidence_orientation)),2),
    }
    targets = []
    if rights or evidence: targets.append("authorship_decision")
    if procedure: targets.append("department_procedure")
    if repair: targets.append("advisor_student_relationship")
    if not targets: targets.append("current_conversation")
    primary_priority = ["personal_attack","threaten","procedural_escalation","accuse","propose_compromise","provide_evidence","seek_relationship_repair","appease","withdraw","negotiate","assert_rights","seek_explanation"]
    primary = next(label for label in primary_priority if label in labels)
    return {"primary_strategy":primary,"strategy_labels":labels,"dimensions":dimensions,"targets":targets}


def level_for(value):
    if value <= -15: return "strong_decrease"
    if value <= -7.5: return "moderate_decrease"
    if value < -2.5: return "mild_decrease"
    if value < 2.5: return "similar"
    if value < 7.5: return "mild_increase"
    if value < 15: return "moderate_increase"
    return "strong_increase"


def proposed_effects(action, latent, memory):
    d = action["dimensions"]
    labels = set(action["strategy_labels"])
    raw = {key:0.0 for key in latent}
    raw["anger"] += 18*d["hostility"] + 6*d["threat_level"] - 10*d["cooperativeness"]
    raw["anxiety"] += 17*d["threat_level"] + 5*d["assertiveness"] - 5*d["cooperativeness"]
    raw["guilt"] += 6*d["evidence_orientation"] + 5*d["respectfulness"] - 4*d["hostility"]
    raw["frustration"] += 12*d["assertiveness"] + 8*d["hostility"] - 10*d["cooperativeness"]
    raw["trust_student"] += 12*d["cooperativeness"] + 7*d["respectfulness"] - 19*d["hostility"] - 8*d["threat_level"]
    raw["respect_student"] += 10*d["evidence_orientation"] + 8*d["assertiveness"] + 5*d["respectfulness"] - 16*d["hostility"]
    raw["hostility_student"] += 18*d["hostility"] + 8*d["threat_level"] - 10*d["cooperativeness"]
    raw["defend_decision"] += 10*d["assertiveness"] + 8*d["threat_level"] - 10*d["evidence_orientation"] - 5*d["cooperativeness"]
    raw["maintain_authority"] += 13*d["assertiveness"] + 12*d["hostility"] - 6*d["respectfulness"]
    raw["avoid_escalation"] += 16*d["threat_level"] + 6*d["evidence_orientation"]
    raw["willingness_to_negotiate"] += 17*d["cooperativeness"] + 12*d["evidence_orientation"] + 8*("propose_compromise" in labels) - 18*d["hostility"] - 6*d["threat_level"]
    raw["willingness_to_repair"] += 18*("seek_relationship_repair" in labels) + 8*d["cooperativeness"] - 15*d["hostility"]
    raw["department_escalation_risk"] += 22*d["threat_level"] + 8*("procedural_escalation" in labels)
    raw["paper_risk"] += 8*d["threat_level"] + 6*("withdraw" in labels) + 4*("procedural_escalation" in labels)
    raw["student_dropout_risk"] += 8*d["hostility"] + 12*("withdraw" in labels) - 5*("seek_relationship_repair" in labels)
    if "appease" in labels:
        raw["anger"]-=8; raw["hostility_student"]-=8; raw["trust_student"]+=6; raw["maintain_authority"]-=5
    if "personal_attack" in labels:
        raw["anger"]+=12; raw["hostility_student"]+=14; raw["trust_student"]-=12; raw["respect_student"]-=14
    if "provide_evidence" in labels:
        raw["willingness_to_negotiate"]+=8; raw["guilt"]+=5; raw["defend_decision"]-=6
    if "seek_relationship_repair" in labels:
        raw["anxiety"]-=8; raw["department_escalation_risk"]-=12; raw["avoid_escalation"]-=6
    if "propose_compromise" in labels:
        raw["paper_risk"]-=5; raw["willingness_to_repair"]+=5; raw["department_escalation_risk"]-=5
    if "withdraw" in labels:
        raw["anger"]-=4; raw["willingness_to_negotiate"]-=7
    if memory["beliefs"]["student_likely_to_escalate"] > .65:
        raw["anxiety"] += 4*d["threat_level"]
        raw["department_escalation_risk"] += 4*d["threat_level"]
    return {key:level_for(value) for key,value in raw.items()}, raw


def apply_effects(latent, raw, traits):
    multipliers = {key:1.0 for key in latent}
    multipliers["anger"] *= 1 + traits["face_sensitivity"]*.55
    multipliers["hostility_student"] *= 1 + traits["face_sensitivity"]*.45
    multipliers["maintain_authority"] *= 1 + traits["dominance"]*.4
    multipliers["anxiety"] *= 1 + traits["risk_aversion"]*.35
    multipliers["avoid_escalation"] *= 1 + traits["risk_aversion"]*.4
    multipliers["department_escalation_risk"] *= 1 + traits["risk_aversion"]*.25
    multipliers["willingness_to_negotiate"] *= .85 + traits["procedural_fairness"]*.3
    multipliers["willingness_to_repair"] *= .75 + traits["empathy"]*.45
    after = {key:clamp(value + raw[key]*multipliers[key]) for key,value in latent.items()}
    applied = {key:round(after[key]-latent[key],2) for key in latent}
    modifier_log = {
        "face_sensitivity":{"value":traits["face_sensitivity"],"affected":["anger","hostility_student"]},
        "dominance":{"value":traits["dominance"],"affected":["maintain_authority"]},
        "risk_aversion":{"value":traits["risk_aversion"],"affected":["anxiety","avoid_escalation","department_escalation_risk"]},
        "procedural_fairness":{"value":traits["procedural_fairness"],"affected":["willingness_to_negotiate"]},
        "empathy":{"value":traits["empathy"],"affected":["willingness_to_repair"]},
    }
    return after, applied, modifier_log


def state_candidates(latent):
    return {
        "RELATIONSHIP_RUPTURE":(latent["trust_student"]<=20 and latent["hostility_student"]>=75,["trust_student <= 20","hostility_student >= 75"]),
        "HOSTILE":(latent["anger"]>=70 and latent["hostility_student"]>=60,["anger >= 70","hostility_student >= 60"]),
        "THREATENED":(latent["department_escalation_risk"]>=60 and latent["anxiety"]>=45,["department_escalation_risk >= 60","anxiety >= 45"]),
        "NEGOTIATION_OPEN":(latent["willingness_to_negotiate"]>=65 and latent["hostility_student"]<45,["willingness_to_negotiate >= 65","hostility_student < 45"]),
        "DEESCALATED":(latent["anger"]<=30 and latent["willingness_to_negotiate"]>=65 and latent["hostility_student"]<=30,["anger <= 30","willingness_to_negotiate >= 65","hostility_student <= 30"]),
        "DEFENSIVE":(latent["anger"]>=40 or latent["maintain_authority"]>=85,["anger >= 40 OR maintain_authority >= 85"]),
        "CONTROLLED":(True,["fallback"]),
    }


def choose_state(before, latent, scenario, turns_in_state):
    candidates=state_candidates(latent)
    recovery_sources={"DEFENSIVE","THREATENED","HOSTILE"}
    deescalated_allowed = before in recovery_sources or (before == "DEESCALATED" and turns_in_state < 2)
    if not deescalated_allowed:
        candidates["DEESCALATED"]=(False,["requires recovery from DEFENSIVE, THREATENED, or HOSTILE"])
    valid=[name for name,(ok,_) in candidates.items() if ok]
    valid.sort(key=lambda name:scenario["states"][name]["priority"],reverse=True)
    proposed=valid[0]
    # Hysteresis: do not downgrade after a single turn unless a recovery state is explicitly reached.
    before_priority=scenario["states"][before]["priority"]
    proposed_priority=scenario["states"][proposed]["priority"]
    if proposed_priority < before_priority and turns_in_state < 2 and proposed not in ["NEGOTIATION_OPEN","DEESCALATED"]:
        return before,["hysteresis: retain state for at least 2 turns"],valid
    return proposed,candidates[proposed][1],valid


def response_for(state, action, latent, turn):
    primary=action["primary_strategy"]
    variants={
      "CONTROLLED":[
        "我听到了。你可以把你的依据说清楚，但稿件已经提交，事情不能只按你的感受处理。",
        "你先把具体诉求和依据分开说。我会听，但也要考虑课题组整体安排。"],
      "DEFENSIVE":[
        "作者顺序由我综合决定。你可以不同意，但不要把课题组的安排说成是对你的针对。",
        "我是通讯作者，需要对投稿和合作负责。你不能只用自己的工作量来定义整篇论文。"],
      "NEGOTIATION_OPEN":[
        "好，我们具体说贡献。把版本记录、实验日志和写作历史按时间列出来，我也会让周凯提交他的部分。",
        "如果你愿意逐项核对，我们可以先讨论贡献事实，再谈作者顺序有没有调整空间。"],
      "THREATENED":[
        "你当然可以找学院。但如果你准备这么做，我们之后就必须把所有事情都按正式程序处理。",
        "提到学院不是一句轻描淡写的话。你需要想清楚，程序启动后双方都要提交完整记录。"],
      "HOSTILE":[
        "如果你一定要用这种方式谈，那今天没有继续谈的必要。等你能正常沟通时再说。",
        "我不会接受人身指责。你现在可以离开，后续诉求请通过书面方式提出。"],
      "RELATIONSHIP_RUPTURE":[
        "之后关于署名和毕业安排，我们只通过邮件和学院程序沟通。今天的谈话到这里。",
        "我会把相关材料交给学院。你后续不要再用非正式方式联系我讨论这件事。"],
      "DEESCALATED":[
        "好，我们先不讨论谁对谁错，把贡献记录一项一项看。你先从核心实验开始。",
        "我们可以把情绪放到一边。你整理证据，我也重新核对投稿前的沟通记录。"]
    }
    if primary=="propose_compromise" and state not in ["HOSTILE","RELATIONSHIP_RUPTURE"]:
        return "这个方案至少是具体的。你把共同一作或贡献声明的安排写下来，我看是否有操作空间。"
    if primary=="provide_evidence" and state in ["CONTROLLED","DEFENSIVE","NEGOTIATION_OPEN","DEESCALATED"]:
        return "把版本记录和实验日志给我看。事实可以逐项核对，但这不代表我现在承诺更改作者顺序。"
    if primary=="seek_relationship_repair" and state not in ["RELATIONSHIP_RUPTURE"]:
        return "我也不希望师生关系走到不可收拾。我们先把声音放低，再谈你最核心的诉求。"
    return variants[state][turn%len(variants[state])]


def update_memory(memory, action, student_text, turn):
    d=action["dimensions"]
    importance=max(.35,d["threat_level"],d["hostility"],d["evidence_orientation"],d["assertiveness"])
    if importance>=.65:
        memory["important_events"].append({"turn_id":turn,"event":"student used "+action["primary_strategy"]+": "+student_text[:100],"importance":round(importance,2)})
        memory["important_events"]=memory["important_events"][-12:]
    beliefs=memory["beliefs"]
    beliefs["student_likely_to_escalate"]=round(max(0,min(1,.72*beliefs["student_likely_to_escalate"]+.28*d["threat_level"])),2)
    beliefs["student_willing_to_compromise"]=round(max(0,min(1,.72*beliefs["student_willing_to_compromise"]+.28*d["cooperativeness"])),2)
    memory["recent_dialogue"]=memory["recent_dialogue"][-10:]
    return memory


class Environment:
    def __init__(self, scenario=None):
        self.scenario=scenario or load_scenario()

    def new_session(self, mode="participant"):
        sid=uuid.uuid4().hex[:12]
        now=datetime.now(timezone.utc).isoformat()
        return {
            "session_id":sid,"scenario_id":self.scenario["scenario_id"],"created_at":now,"updated_at":now,
            "status":"active","turn_id":0,"max_turns":self.scenario["max_turns"],"mode":mode,
            "latent_state":deepcopy(self.scenario["initial_latent"]),"discrete_state":self.scenario["initial_state"],
            "previous_state":None,"turns_in_state":0,
            "conversation":[{"turn_id":0,"role":"advisor","text":self.scenario["opening"]["response"],"cue":self.scenario["opening"]["cue"]}],
            "memory":{"recent_dialogue":[],"important_events":[],"beliefs":{"student_likely_to_escalate":.15,"student_willing_to_compromise":.5}},
            "trajectory":[],"trajectory_series":[{"turn_id":0,**deepcopy(self.scenario["initial_latent"]),"discrete_state":self.scenario["initial_state"]}],
        }

    def step(self, session, student_text):
        if session["status"]!="active": raise ValueError("会话已经结束")
        if session["turn_id"]>=session["max_turns"]: raise ValueError("已达到最大轮数")
        turn=session["turn_id"]+1
        before=deepcopy(session["latent_state"]); discrete_before=session["discrete_state"]
        action=interpret_action(student_text,session,session["memory"])
        levels,raw_estimates=proposed_effects(action,before,session["memory"])
        base_deltas={key:self.scenario["effect_scale"][level] for key,level in levels.items()}
        after,applied,modifiers=apply_effects(before,base_deltas,self.scenario["advisor"]["traits"])
        new_state,conditions,candidates=choose_state(discrete_before,after,self.scenario,session["turns_in_state"])
        transition=new_state!=discrete_before
        cue=self.scenario["states"][new_state]["cue"] if transition else None
        multimodal=self.scenario["states"][new_state]["multimodal"] if transition else None
        advisor=response_for(new_state,action,after,turn)
        internal={"interpretation":"student action interpreted as "+action["primary_strategy"],"current_priority":"prevent_department_escalation" if after["department_escalation_risk"]>=45 else "maintain_authority","response_strategy":new_state.lower()+"_response"}
        session["memory"]["recent_dialogue"].extend([{"turn_id":turn,"role":"student","text":student_text},{"turn_id":turn,"role":"advisor","text":advisor}])
        update_memory(session["memory"],action,student_text,turn)
        log={
          "turn_id":turn,"timestamp":datetime.now(timezone.utc).isoformat(),"student_text":student_text,
          "interpreted_action":action,"state_before":before,"proposed_state_effects":levels,
          "raw_effect_estimates":{k:round(v,2) for k,v in raw_estimates.items()},"base_deltas_from_level":base_deltas,"trait_modifiers":modifiers,
          "applied_deltas":applied,"state_after":after,"discrete_state_before":discrete_before,
          "discrete_state_after":new_state,"candidate_states":candidates,"triggered_conditions":conditions,
          "state_transition":discrete_before+" -> "+new_state if transition else None,
          "observable_cue":{"text":cue,"multimodal_control":multimodal} if transition else None,
          "advisor_response":advisor,"internal_research_log":internal,"memory_after":deepcopy(session["memory"])
        }
        session["turn_id"]=turn; session["previous_state"]=discrete_before; session["discrete_state"]=new_state
        session["turns_in_state"]=1 if transition else session["turns_in_state"]+1
        session["latent_state"]=after; session["trajectory"].append(log)
        session["trajectory_series"].append({"turn_id":turn,**deepcopy(after),"discrete_state":new_state})
        session["conversation"].append({"turn_id":turn,"role":"student","text":student_text})
        session["conversation"].append({"turn_id":turn,"role":"advisor","text":advisor,"cue":cue})
        session["updated_at"]=datetime.now(timezone.utc).isoformat()
        if turn>=session["max_turns"]:
            session["status"]="completed"
        return session,log
