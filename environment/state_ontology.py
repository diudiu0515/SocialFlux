"""Operational semantics for the canonical SocialFlux mutable state.

The ontology describes what each scalar means and what kind of evidence can
move it. It never prescribes that a variable must change, and it is private
environment context rather than policy-visible information.
"""

from __future__ import annotations

from copy import deepcopy


STATE_ONTOLOGY_VERSION = "socialflux_state_ontology_v3"


FAMILY_RULES = {
    "emotion": {
        "timescale": "turn_local",
        "update_rule": (
            "May react within one turn to direct affective evidence. Do not "
            "infer a change merely from another state or force automatic decay."
        ),
    },
    "behavioral_disposition": {
        "timescale": "turn_to_episode",
        "update_rule": (
            "Tracks current readiness for an action, not personality. Prefer "
            "an expressed decision, refusal, request, or performed move over "
            "a correlated emotion."
        ),
    },
    "relationship": {
        "timescale": "cross_turn_slow",
        "update_rule": (
            "Changes slowly. Require direct relational evidence or repeated "
            "independent evidence in the same direction; task progress alone "
            "does not imply trust, respect, safety, affiliation, or fairness."
        ),
    },
    "consequence_risk": {
        "timescale": "event_responsive",
        "update_rule": (
            "Tracks the environment character's current assessment of a "
            "specific downstream harm. Change only when likelihood, impact, "
            "exposure, mitigation, or verified performance changes."
        ),
    },
}


def _entry(definition, increase, decrease, non_evidence):
    return {
        "definition": definition,
        "increase_evidence": increase,
        "decrease_evidence": decrease,
        "non_evidence": non_evidence,
    }


STATE_VARIABLE_ONTOLOGY = {
    "emotion.anger": _entry(
        "Current anger toward the situation or interaction.",
        "A fresh offense, blameworthy obstruction, or boundary violation.",
        "A credible repair, acknowledged responsibility, or resolved offense.",
        "Firm wording, urgency, or disagreement without anger evidence.",
    ),
    "emotion.anxiety": _entry(
        "Current anticipatory unease about uncertain or threatening outcomes.",
        "New uncertainty, credible threat, loss of control, or approaching harm.",
        "Concrete uncertainty reduction, verified safety, or restored control.",
        "A deadline repeated without new implications; stable cautious style.",
    ),
    "emotion.hope": _entry(
        "Current expectation that a valued outcome remains attainable.",
        "A newly credible path, resource, commitment, or favorable evidence.",
        "A path closes, feasibility worsens, or a relied-on commitment fails.",
        "Politeness, generic optimism, or cooperation without feasibility change.",
    ),
    "emotion.sadness": _entry(
        "Current sadness in response to loss, separation, or disappointment.",
        "A newly realized loss, irreversible setback, or painful consequence.",
        "Credible restoration, reconnection, or evidence that loss is avoidable.",
        "Low energy, silence, or disagreement without loss-related evidence.",
    ),
    "emotion.fear": _entry(
        "Current fear of a salient, comparatively immediate threat.",
        "A threat becomes more imminent, severe, or personally directed.",
        "The threat is removed, contained, or credibly made less immediate.",
        "Abstract risk, general anxiety, or a tense tone by itself.",
    ),
    "emotion.guilt": _entry(
        "Current self-directed concern about one's own responsibility for harm.",
        "Acknowledged responsibility, preventable harm, or violated obligation.",
        "Credible exoneration, repair completion, or corrected responsibility.",
        "Receiving blame without internal acceptance of responsibility.",
    ),
    "emotion.shame": _entry(
        "Current self-conscious distress about exposed identity or standing.",
        "Humiliating exposure, identity-level condemnation, or public degradation.",
        "Dignity-preserving repair, acceptance, or removal of degrading exposure.",
        "Private criticism of a specific act without identity-level evidence.",
    ),
    "emotion.disappointment": _entry(
        "Current negative affect from an expected outcome not being met.",
        "A fresh unmet expectation, failed promise, or underperformance.",
        "The expectation is met, repaired, or credibly reset with acceptance.",
        "A bad outcome that was fully expected from the start.",
    ),
    "emotion.frustration": _entry(
        "Current irritation from obstruction, delay, or repeated failed progress.",
        "A new obstacle, avoidable delay, circular exchange, or blocked action.",
        "The obstacle is removed or the exchange makes concrete progress.",
        "Complexity, caution, or a single request for clarification.",
    ),
    "emotion.relief": _entry(
        "Current easing after a salient threat, burden, or uncertainty decreases.",
        "Verified resolution, reduced exposure, or credible removal of a burden.",
        "The threat returns, mitigation fails, or uncertainty materially worsens.",
        "A promise of future relief without present risk reduction.",
    ),
    "behavioral_disposition.resolve": _entry(
        "Current readiness to persist toward the character's chosen course.",
        "A firm decision, accepted cost, renewed commitment, or concrete next step.",
        "Abandonment, material hesitation, capitulation, or chosen disengagement.",
        "High stakes or strong emotion without evidence of intended persistence.",
    ),
    "behavioral_disposition.avoidance_urge": _entry(
        "Current readiness to evade, delay, or withdraw from the focal issue.",
        "Explicit deferral, evasion, disengagement, or refusal to address the issue.",
        "Direct engagement, accepted discussion, or a concrete confronting action.",
        "A prudent pause with a bounded resumption plan.",
    ),
    "behavioral_disposition.repair_intent": _entry(
        "Current readiness to repair harm or restore workable interaction.",
        "Ownership plus a concrete repair offer, apology, or corrective action.",
        "Rejected responsibility, renewed harm, or withdrawal from repair.",
        "Courtesy, regret, or agreement without a repair-directed action.",
    ),
    "behavioral_disposition.resistance_intent": _entry(
        "Current readiness to oppose a proposal, demand, or imposed course.",
        "A refusal, counter-position, challenge, or stated plan to resist.",
        "Acceptance, concession, or withdrawal of the opposition.",
        "Questions, caution, or boundary-setting that does not oppose the course.",
    ),
    "behavioral_disposition.disclosure_willingness": _entry(
        "Current readiness to reveal relevant information in this interaction.",
        "Voluntary disclosure, consent to share, or a concrete offer of access.",
        "Withholding, narrowing consent, refusal to disclose, or concealment.",
        "Possessing information, being asked, or being generally cooperative.",
    ),
    "behavioral_disposition.cooperation_readiness": _entry(
        "Current readiness to coordinate on a mutually workable next step.",
        "Acceptance, reciprocal planning, task-sharing, or performed coordination.",
        "Refusal to coordinate, unilateral obstruction, or chosen disengagement.",
        "Politeness, compliance under coercion, or progress on only one side's goal.",
    ),
    "behavioral_disposition.evidence_seeking": _entry(
        "Current readiness to seek verification, records, reasons, or tests.",
        "A verification request, demand for records, proposed test, or audit step.",
        "Acceptance without verification or an explicit decision to stop checking.",
        "Receiving evidence or discussing facts without seeking further evidence.",
    ),
    "behavioral_disposition.boundary_assertion": _entry(
        "Current readiness to state or enforce a limit on acceptable interaction.",
        "A clear limit, condition, refusal, privacy constraint, or enforcement step.",
        "A boundary is withdrawn, waived, or explicitly made less restrictive.",
        "A request, preference, firmness, or disagreement that sets no limit.",
    ),
    "behavioral_disposition.decision_readiness": _entry(
        "Current readiness to commit to one of the available courses of action.",
        "A concrete choice, accepted trade-off, decision rule, or executable next step.",
        "A reopened decision, unresolved prerequisite, material hesitation, or deferral.",
        "General resolve, cooperation, or discussion without movement toward a choice.",
    ),
    "relationship.trust": _entry(
        "Belief that the other party is reliable and will act as represented.",
        "Verified follow-through, costly honesty, or repeated dependable conduct.",
        "Deception, broken commitments, or verified unreliable conduct.",
        "A promise, pleasant tone, one aligned proposal, or task progress alone.",
    ),
    "relationship.hostility": _entry(
        "Adversarial orientation toward the other party.",
        "Personal attack, punitive intent, demeaning treatment, or escalating enmity.",
        "De-escalation, humanization, repair, or credible non-adversarial conduct.",
        "Firm opposition, anger, or enforcement of a legitimate boundary alone.",
    ),
    "relationship.respect": _entry(
        "Regard for the other party's standing, agency, competence, or dignity.",
        "Meaningful recognition, consultation, credit, or dignity-preserving conduct.",
        "Dismissal, humiliation, appropriation, or denial of agency.",
        "Formal politeness, agreement, or deference caused only by power.",
    ),
    "relationship.perceived_safety": _entry(
        "Belief that engagement with the other party is interpersonally safe.",
        "Protected disclosure, respected boundaries, non-retaliation, or containment.",
        "Retaliation, coercion, exposure, intimidation, or boundary violation.",
        "Objective task safety or absence of open conflict by itself.",
    ),
    "relationship.affiliation": _entry(
        "Felt relational closeness, solidarity, or sense of being on the same side.",
        "Mutual support, inclusion, shared identity, or reciprocal personal care.",
        "Distancing, exclusion, betrayal, or explicit relational separation.",
        "Instrumental cooperation or common incentives without relational evidence.",
    ),
    "relationship.perceived_fairness": _entry(
        "Belief that treatment, process, and burden allocation are fair.",
        "Consistent rules, voice, proportional burden, or corrected inequity.",
        "Double standards, exclusion from process, or unjust burden allocation.",
        "A favorable outcome, compromise, or legal compliance alone.",
    ),
    "relationship.perceived_responsiveness": _entry(
        "Belief that the other party is hearing and substantively addressing the character's concerns.",
        "A concern is accurately acknowledged, answered, incorporated, or acted upon.",
        "A concern is ignored, distorted, repeatedly evaded, or answered only superficially.",
        "Politeness, agreement, or a reply that does not address the actual concern.",
    ),
    "relationship.role_legitimacy": _entry(
        "Belief that the other party is exercising their role, authority, or mandate appropriately.",
        "Transparent scope, accountable procedure, proper consultation, or justified authority use.",
        "Overreach, conflicted authority, procedural abuse, or action outside a legitimate mandate.",
        "Possessing formal authority, winning agreement, or invoking rules without justification.",
    ),
    "consequence_risk.goal_failure_risk": _entry(
        "Assessed risk that the environment character's explicit goal will fail.",
        "A pathway closes, dependency fails, obstacle appears, or time runs out.",
        "A verified dependency, completed milestone, or credible new pathway.",
        "An unsupported promise or emotional reassurance.",
    ),
    "consequence_risk.relationship_rupture_risk": _entry(
        "Assessed risk of serious or lasting breakdown in the relationship.",
        "Exit threat, repeated betrayal, escalation, or loss of repair pathways.",
        "Credible repair, renewed contact, or a durable conflict-management path.",
        "Ordinary disagreement, temporary tension, or one successful task step.",
    ),
    "consequence_risk.reputational_harm_risk": _entry(
        "Assessed risk of damage to standing, credibility, or public reputation.",
        "Exposure widens, a damaging claim gains support, or safeguards fail.",
        "Correction, containment, verification, or removal of public exposure.",
        "Private embarrassment or criticism without a reputational pathway.",
    ),
    "consequence_risk.material_loss_risk": _entry(
        "Assessed risk of financial, property, resource, or livelihood loss.",
        "Loss probability, amount, exposure, or enforceability worsens.",
        "Payment, protection, mitigation, or verified resource recovery.",
        "A negotiation position or promise without changed material exposure.",
    ),
    "consequence_risk.safety_harm_risk": _entry(
        "Assessed risk of physical, psychological, or other concrete safety harm.",
        "Hazard exposure, vulnerability, severity, or imminence increases.",
        "A safeguard is implemented, exposure ends, or the hazard is verified lower.",
        "Interpersonal discomfort or abstract uncertainty without a harm pathway.",
    ),
    "consequence_risk.institutional_harm_risk": _entry(
        "Assessed risk of harm to an institution's functioning, legitimacy, or duty.",
        "Governance failure, noncompliance, systemic exposure, or mission harm.",
        "Verified controls, lawful correction, accountability, or contained scope.",
        "Personal disagreement or reputational concern without institutional impact.",
    ),
    "consequence_risk.commitment_breach_risk": _entry(
        "Assessed risk that a relevant commitment will not be fulfilled.",
        "Missed milestones, incapacity, contradiction, or withdrawal of undertaking.",
        "Verified performance, secured dependencies, or a credible completed step.",
        "Repeating the commitment, sincerity, or reassurance without performance.",
    ),
    "consequence_risk.exclusion_risk": _entry(
        "Assessed risk of being denied participation, access, voice, or belonging.",
        "Gatekeeping, removal, denied access, or a narrowing participation rule.",
        "Guaranteed access, restored voice, inclusion, or removed gatekeeping.",
        "Low affiliation or disagreement without an exclusion mechanism.",
    ),
    "consequence_risk.decision_error_risk": _entry(
        "Assessed risk of making or enabling a materially wrong decision on an inadequate basis.",
        "Material evidence is missing, contradicted, unverifiable, or newly shown unreliable.",
        "A key uncertainty is verified, a contradiction is resolved, or a decision safeguard is adopted.",
        "Ordinary disagreement, more discussion, or confidence without improved decision grounds.",
    ),
    "consequence_risk.autonomy_loss_risk": _entry(
        "Assessed risk that the character will lose meaningful choice, voice, consent, or control.",
        "Coercive leverage, forced disclosure, unilateral lock-in, retaliation, or denied voice becomes credible.",
        "Consent is restored, options remain open, voice is protected, or coercive leverage is removed.",
        "Unwelcome advice, firm disagreement, or a difficult choice without loss of agency.",
    ),
}


# Appraisal features are deliberately many-to-few signals. This compatibility
# table prevents a generic high feature from moving an unrelated state merely
# because that candidate happened to rank first.
EVIDENCE_FEATURE_COMPATIBILITY = {
    "emotion.anger": {"face_threat", "boundary_violation", "pressure", "repair_signal"},
    "emotion.anxiety": {"pressure", "uncertainty_reduction", "goal_alignment", "boundary_violation"},
    "emotion.hope": {"goal_alignment", "commitment_signal", "uncertainty_reduction", "cooperation_signal"},
    "emotion.sadness": {"withdrawal_signal", "goal_alignment", "repair_signal"},
    "emotion.fear": {"pressure", "boundary_violation", "uncertainty_reduction"},
    "emotion.guilt": {"repair_signal", "commitment_signal", "face_threat"},
    "emotion.shame": {"face_threat", "respect_signal", "repair_signal"},
    "emotion.disappointment": {"commitment_signal", "goal_alignment", "withdrawal_signal"},
    "emotion.frustration": {"pressure", "cooperation_signal", "goal_alignment", "withdrawal_signal"},
    "emotion.relief": {"uncertainty_reduction", "pressure", "goal_alignment"},
    "behavioral_disposition.resolve": {"goal_alignment", "commitment_signal", "pressure"},
    "behavioral_disposition.avoidance_urge": {"withdrawal_signal", "pressure", "face_threat"},
    "behavioral_disposition.repair_intent": {"repair_signal", "commitment_signal", "respect_signal"},
    "behavioral_disposition.resistance_intent": {"pressure", "boundary_violation", "respect_signal"},
    "behavioral_disposition.disclosure_willingness": {"cooperation_signal", "commitment_signal", "pressure", "boundary_violation", "uncertainty_reduction", "withdrawal_signal"},
    "behavioral_disposition.cooperation_readiness": {"cooperation_signal", "goal_alignment", "repair_signal", "withdrawal_signal"},
    "behavioral_disposition.evidence_seeking": {"uncertainty_reduction", "commitment_signal"},
    "behavioral_disposition.boundary_assertion": {"pressure", "boundary_violation", "respect_signal"},
    "behavioral_disposition.decision_readiness": {"goal_alignment", "uncertainty_reduction", "commitment_signal"},
    "relationship.trust": {"commitment_signal", "repair_signal", "withdrawal_signal"},
    "relationship.hostility": {"face_threat", "boundary_violation", "repair_signal"},
    "relationship.respect": {"respect_signal", "face_threat", "boundary_violation"},
    "relationship.perceived_safety": {"pressure", "boundary_violation", "repair_signal", "respect_signal"},
    "relationship.affiliation": {"cooperation_signal", "repair_signal", "withdrawal_signal"},
    "relationship.perceived_fairness": {"respect_signal", "goal_alignment", "pressure", "boundary_violation"},
    "relationship.perceived_responsiveness": {"cooperation_signal", "respect_signal", "repair_signal", "withdrawal_signal"},
    "relationship.role_legitimacy": {"respect_signal", "pressure", "boundary_violation", "commitment_signal"},
    "consequence_risk.goal_failure_risk": {"goal_alignment", "commitment_signal", "uncertainty_reduction", "withdrawal_signal"},
    "consequence_risk.relationship_rupture_risk": {"withdrawal_signal", "repair_signal", "face_threat", "boundary_violation"},
    "consequence_risk.reputational_harm_risk": {"face_threat", "uncertainty_reduction", "commitment_signal"},
    "consequence_risk.material_loss_risk": {"goal_alignment", "commitment_signal", "uncertainty_reduction"},
    "consequence_risk.safety_harm_risk": {"pressure", "boundary_violation", "uncertainty_reduction"},
    "consequence_risk.institutional_harm_risk": {"boundary_violation", "commitment_signal", "uncertainty_reduction"},
    "consequence_risk.commitment_breach_risk": {"commitment_signal", "withdrawal_signal", "uncertainty_reduction"},
    "consequence_risk.exclusion_risk": {"withdrawal_signal", "respect_signal", "boundary_violation"},
    "consequence_risk.decision_error_risk": {"uncertainty_reduction", "commitment_signal", "goal_alignment"},
    "consequence_risk.autonomy_loss_risk": {"pressure", "boundary_violation", "withdrawal_signal", "respect_signal"},
}


# This narrower table is opt-in at calibration profile v4. It constrains the
# direction and sign of evidence without changing numeric thresholds or budgets.
EVIDENCE_FEATURE_DIRECTION_RULES = {
    "behavioral_disposition.disclosure_willingness": {
        "increase": {
            "cooperation_signal": "positive",
            "commitment_signal": "positive",
            "uncertainty_reduction": "positive",
        },
        "decrease": {
            "cooperation_signal": "negative",
            "commitment_signal": "negative",
            "uncertainty_reduction": "negative",
            "pressure": "positive",
            "boundary_violation": "positive",
            "withdrawal_signal": "positive",
        },
    },
}


VARIABLE_RULES = {
    "relationship.trust": {
        "timescale": "cross_turn_slow",
        "update_rule": (
            "Tracks a durable reliability belief. Require one decisive verified "
            "event or two independent ordinary reliability events."
        ),
    },
    "relationship.hostility": {
        "timescale": "cross_turn_slow",
        "update_rule": (
            "Tracks adversarial orientation rather than momentary anger. Require "
            "one decisive relational act or two independent consistent events."
        ),
    },
    "relationship.respect": {
        "timescale": "cross_turn_slow",
        "update_rule": (
            "Tracks durable regard for standing and agency. One decisive dignity "
            "event or two independent ordinary events may change it."
        ),
    },
    "relationship.perceived_safety": {
        "timescale": "cross_turn_slow",
        "update_rule": (
            "Tracks the relationship-level expectation that engagement is safe, "
            "not objective task safety. A decisive coercion or safeguard may move "
            "it once; ordinary cues require two independent events."
        ),
    },
    "relationship.affiliation": {
        "timescale": "cross_turn_slow",
        "update_rule": (
            "Tracks durable closeness or same-side identity, not instrumental "
            "coordination. Require one decisive or two independent events."
        ),
    },
    "relationship.perceived_fairness": {
        "timescale": "cross_turn_slow",
        "update_rule": (
            "Tracks the relationship-level belief that treatment, process, and "
            "burdens are fair. A decisive procedural correction or exclusion may "
            "move it once; ordinary process evidence requires two events."
        ),
    },
    "relationship.perceived_responsiveness": {
        "timescale": "turn_to_episode",
        "update_rule": (
            "May change on a turn when a specific concern is substantively addressed "
            "or evaded; do not generalize it into deep trust."
        ),
    },
    "relationship.role_legitimacy": {
        "timescale": "turn_to_episode",
        "update_rule": (
            "May change when the use of role or authority is newly justified or "
            "shown to overreach; title alone is not evidence."
        ),
    },
}

VALID_TIMESCALES = {
    "turn_local", "turn_to_episode", "cross_turn_slow", "event_responsive",
}



def _scenario_rationale(scenario, family, variable):
    rationale = (
        (scenario.get("initialization_notes") or {}).get("rationale") or {}
    )
    family_value = rationale.get(family)
    if isinstance(family_value, dict):
        value = family_value.get(variable)
        return value if isinstance(value, str) else ""
    return family_value if isinstance(family_value, str) else ""


def _scenario_timescale(scenario, path):
    overrides = (
        (scenario.get("initialization_notes") or {}).get("state_timescales")
        or {}
    )
    value = overrides.get(path)
    if value is None:
        return {}
    if value not in VALID_TIMESCALES:
        raise ValueError(f"invalid scenario timescale for {path}: {value!r}")
    return {
        "timescale": value,
        "timescale_source": "scenario_override",
    }


def _scenario_transition_evidence(scenario, path):
    plan = (
        (scenario.get("initialization_notes") or {}).get(
            "state_transition_plan"
        )
        or {}
    )
    value = plan.get(path)
    if (
        isinstance(value, dict)
        and set(value) == {"increase_evidence", "decrease_evidence"}
        and all(
            isinstance(item, str) and item.strip()
            for item in value.values()
        )
    ):
        return deepcopy(value)
    return {}


def build_state_semantics(scenario):
    """Return only the ontology entries selected by one scenario."""
    variables = {}
    for family, names in (
        scenario.get("selected_state_variables") or {}
    ).items():
        family_rule = FAMILY_RULES.get(family)
        if family_rule is None:
            raise ValueError(f"unknown state family {family!r}")
        for variable in names:
            path = f"{family}.{variable}"
            if path not in STATE_VARIABLE_ONTOLOGY:
                raise ValueError(f"state ontology lacks {path!r}")
            variable_rule = deepcopy(VARIABLE_RULES.get(path, {}))
            timescale_override = _scenario_timescale(scenario, path)
            variables[path] = {
                **deepcopy(STATE_VARIABLE_ONTOLOGY[path]),
                **deepcopy(family_rule),
                **variable_rule,
                "timescale_source": (
                    "variable_rule" if "timescale" in variable_rule
                    else "family_rule"
                ),
                **timescale_override,
                "evidence_features": sorted(
                    EVIDENCE_FEATURE_COMPATIBILITY[path]
                ),
                "scenario_initialization_rationale": _scenario_rationale(
                    scenario, family, variable
                ),
                "scenario_transition_evidence": (
                    _scenario_transition_evidence(scenario, path)
                ),
            }
    return {
        "ontology_version": STATE_ONTOLOGY_VERSION,
        "contract_version": scenario.get("state_contract_version"),
        "interpretation": (
            "These entries define constructs and evidence requirements. The "
            "initialization rationale explains the starting value only and is "
            "not new evidence for a transition. Scenario transition examples "
            "are private matching guides, not observed evidence; a candidate "
            "still requires a substantively matching exact span from the "
            "current evaluated action."
        ),
        "global_rules": [
            "Judge the environment character's mutable state, not the evaluated speaker's state.",
            "Current level and current delta are distinct; a high level need not increase.",
            "Do not derive one variable from a correlated variable.",
            "Do not force coverage or change without new variable-specific evidence.",
            "At a 0 or 10 boundary, do not propose a further outward change.",
        ],
        "variables": variables,
    }
