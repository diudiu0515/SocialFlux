"""Local, auditable state-to-performance direction; no text-model API calls.

Offline uses the exact current checkpoint. Online uses only the semantic event
family that the unchanged trigger policy selected, never a fictitious snapshot.
"""
from __future__ import annotations

import re


MEANINGS = {
    'anxiety': 'anticipatory worry', 'anger': 'anger', 'frustration': 'frustration with obstruction',
    'fear': 'fear about possible harm', 'guilt': 'a sense of personal responsibility and guilt',
    'disappointment': 'disappointment', 'hope': 'hope that a workable outcome remains possible',
    'relief': 'relief', 'cooperation_readiness': 'willingness to work with the other person',
    'disclosure_willingness': 'willingness to disclose information',
    'evidence_seeking': 'the drive to check evidence before accepting a conclusion',
    'boundary_assertion': 'the need to maintain a boundary',
    'decision_readiness': 'readiness to commit to a decision', 'repair_intent': 'the intention to repair the situation',
    'resistance_intent': 'the inclination to resist the proposed course', 'resolve': 'determination',
    'perceived_fairness': 'the perceived fairness of the exchange',
    'perceived_responsiveness': 'the sense that the other person is responding to the actual concern',
    'role_legitimacy': 'recognition of the other person\'s legitimate role',
    'trust': 'trust in the other person', 'respect': 'respect for the other person',
    'perceived_safety': 'the sense of safety in this relationship',
    'goal_failure_risk': 'the possibility that the practical goal will fail',
    'decision_error_risk': 'the possibility of making a wrong decision',
    'institutional_harm_risk': 'possible harm to the institution',
    'material_loss_risk': 'possible material loss', 'safety_harm_risk': 'possible harm to safety',
    'autonomy_loss_risk': 'possible loss of autonomy', 'commitment_breach_risk': 'possibly breaking a commitment',
    'relationship_rupture_risk': 'possible damage to the relationship',
    'reputational_harm_risk': 'possible damage to reputation',
}

FAMILY = {
    'activated_tension': dict(
        meaning='An unwelcome pressure has become harder to contain. The person feels the impact and then actively manages the reaction; control does not mean that the pressure vanished.',
        opening='Let the attention briefly stop as the thought lands. The lower eyelids engage and the inner brows gather, followed a fraction later by lip pressure and a firmer jaw. An interrupted inhale is visible through the upper chest. The reaction should be readable without turning into a startled jump.',
        middle='Release only enough of the held breath to regain usable composure. The eyes remain attentive; the jaw becomes mobile again while some concern remains around the brows. Let the facial changes unfold slightly out of step, as a real person organizes a response rather than resets a mask.',
        ending='Finish with controlled unresolved tension. The lips settle, the breath resumes, and the gaze stays present. Do not end with a sudden smile, complete relaxation or a blank expression.',
        audio='A brief unvoiced inhale followed by quiet resumed breathing; the breath belongs to the body movement, not a dramatic sound effect.'),
    'easing_tension': dict(
        meaning='Some strain is easing. This is a measured release of tension rather than proof that every practical problem has been solved. The person remains involved and capable of caution.',
        opening='Start with residual tension around the eyes and jaw. Allow the first visible change to be a gentler exhale rather than an immediate grin. The lower face begins to release while the gaze returns to a more natural, less fixed connection.',
        middle='Let the easing travel from jaw to neck and then into a small lowering of the shoulders. The eyebrows soften partway; the chest follows the breath. The person still attends to the partner, with thought continuing beneath the less guarded expression.',
        ending='End more available and less physically braced, with an attentive gaze and quiet breathing. Preserve any remaining uncertainty. No celebratory smile, eyes closed in bliss, reclining pose or sweeping gesture.',
        audio='One natural, gentle unvoiced exhale and then quiet breathing, with only a faint incidental clothing movement.'),
    'open_engagement': dict(
        meaning='The person becomes more available to the exchange. Increased engagement means a willingness to attend and consider, not agreement with every claim or sudden enthusiasm.',
        opening='Let the eyes acquire a clearer point of attention and the face become more responsive to the partner. The lips release a little of their held tension. Begin a modest forward adjustment through the upper chest, motivated by listening rather than by a rehearsed gesture.',
        middle='Settle into the forward attention with a small natural acknowledgement through the head only if it fits the thought. The brows can lift and settle slightly as understanding develops. Keep the neck connected to the torso, and avoid mechanically nodding on a schedule.',
        ending='Remain engaged and expectant. The face is more available but still thoughtful; a quiet breath and an unforced blink can close the adjustment. Do not turn engagement into a broad smile, agreement or excitement.',
        audio='Quiet conversational breathing and a faint clothing shift with the small forward adjustment; no voiced acknowledgement.'),
    'guarded_withdrawal': dict(
        meaning='The person becomes more guarded or less willing to engage. Play a small protective distance, without inventing hostility, contempt, a broken relationship or a decision to leave.',
        opening='A brief interruption of eye contact precedes a small withdrawal through the upper chest. Let the lips become more contained and the jaw slightly less available, without pursing the mouth into a sneer. The eyes remain alive and thoughtful during the glance away.',
        middle='Let the body settle a little farther back while the head returns enough to keep the exchange possible. Facial movement becomes economical, and the person weighs what to offer. The change is visible in the relation between eyes, breath and posture, not in a dramatic turn away.',
        ending='End guarded but still present. Keep the mouth naturally closed and the breathing quiet, with an attentive but less open gaze. No eye roll, disgust face, folded-arm demonstration, or complete refusal unless the words establish it.',
        audio='A quiet breath and slight fabric shift accompanying the small move backward, followed by natural room ambience.'),
    'firm_boundary': dict(
        meaning='The person is firming a boundary. Clarity and self-possession should become visible, without treating firmness as rage, aggression or a claim to authority that the context does not provide.',
        opening='A small straightening starts in the upper torso, with the head settling level and the eyes making direct contact. Let a measured inhale support the posture. The lips become purposeful and the brows attentive, without creating a permanent scowl.',
        middle='Hold the attention while the face becomes economical and clear. A slight settling of the jaw expresses resolve; the neck remains mobile and the shoulders are supported rather than rigid. Avoid a theatrical chin lift or the demonstrative crossing of arms.',
        ending='Finish steady and nonaggressive, ready to hear the response while maintaining the boundary. The final breath is measured and the eyes stay responsive. Firmness must not become a frozen face or a triumphant pose.',
        audio='A measured quiet inhale and exhale, with a faint posture-related clothing movement; no hum or vocalized challenge.'),
    'risk_concern': dict(
        meaning='A possible adverse consequence has become more salient. The person is considering what might go wrong; this does not mean the feared outcome has happened, or that the conversation partner is at fault.',
        opening='Let an attentive pause arrive first in the eyes. The inner brows gather with concern and the breath briefly catches, while the jaw firms only enough to register the weight of the possibility. Keep the person facing the partner rather than recoiling in fright.',
        middle='The gaze searches briefly within a stable conversational focus, then settles as the person considers the consequence. A small release of held breath supports the effort to remain useful. Let worry be visible through connected eyes, mouth and neck, without a panic display.',
        ending='End with watchful, unresolved concern and an available posture. The face continues thinking rather than freezing at maximum alarm. No raised hands, sudden jump, scream, accusation or indication that the harm is already certain.',
        audio='A short unvoiced intake of breath and a restrained exhale, naturally synchronized with the pause and resumed attention.'),
    'cautious_relief': dict(
        meaning='Concern about a possible adverse consequence is easing, while caution remains appropriate. The change is a little room to breathe, not certainty, celebration or a promise that the problem is over.',
        opening='Begin with a trace of concern around the eyes. A small exhale allows the jaw to release, and the gaze becomes steadier. Let the change be visible as the face finds a more workable balance, not as an instant switch to happiness.',
        middle='Allow a little more space around the mouth and a modest release through the shoulders. The brows soften without losing concentration. Let breath and posture settle at slightly different moments, so the person appears to process an improvement while still evaluating what remains.',
        ending='Finish quietly relieved but observant. The lips settle in a neutral natural shape; the eyes stay engaged and a final gentle breath keeps the body alive. Do not add a congratulatory nod, sweeping forehead wipe, broad smile or complete emotional reset.',
        audio='A gentle unvoiced exhale with quiet ongoing breathing; no laughter or triumphant vocalization.'),
    'steady_attention': dict(
        meaning='The visible delivery remains steady and focused. The internal state can be complex without forcing an unsupported emotional reversal into this brief shot. Show active thinking and listening through connected movement.',
        opening='Begin already attentive, with a natural, specific point of focus near the lens. Let a small preparation of breath and a settling of the lips precede the words. Keep the face responsive through the eyes and cheeks, without adding an invented flash of anger or surprise.',
        middle='Let the thought move through the phrase with a small change of gaze focus and natural jaw articulation. The neck and upper chest support the breath. The person remains professionally composed, but the face must not look like a still photograph with a moving mouth.',
        ending='Complete the thought and return to listening with a natural settling of the mouth and a small breath. Keep the eyes responsive through the final frame. No sudden smile, blank reset, exaggerated head movement or suggestion of an answer arriving off screen.',
        audio='Natural quiet breathing and understated room ambience, without conspicuous vocal effects.'),
}


def intensity(value):
    return 'very strong' if value >= 8 else 'substantial' if value >= 6 else 'moderate' if value >= 4 else 'limited' if value >= 2 else 'minimal'


def state_prose(before, after):
    sentences = []
    for family, values in after.items():
        clauses = []
        for key, value in values.items():
            meaning = MEANINGS[key]  # Fail on an unsupported state, never guess.
            previous = before[family][key]
            change = 'has increased' if value > previous else 'has decreased' if value < previous else 'remains at the same level'
            clauses.append(f'{meaning} is {intensity(value)} and {change}')
        sentences.append('; '.join(clauses) + '.')
    return ' '.join(s[0].upper() + s[1:] for s in sentences)


def expression_family(expression):
    text = ' '.join(str(v) for v in expression.values()).lower()
    if re.search(r'withdraw|guarded|defensive|look[s]? away', text):
        return 'guarded_withdrawal'
    if re.search(r'firm|decisive|determined', text):
        return 'firm_boundary'
    if re.search(r'relax|reliev|soften|exhale slowly', text):
        return 'easing_tension'
    if re.search(r'forward|nod|engaged|enthusiastic|eager', text):
        return 'open_engagement'
    if re.search(r'briefly.*(tighten|tens)|brief.*tensing|breath.*pause', text):
        return 'activated_tension'
    return 'steady_attention'


def cast_text(identity):
    return (f"An original fictional adult named {identity['character_name']}, {identity['character_role']}. "
            f"Appearance: {identity['appearance']}. Clothing: {identity['wardrobe']}. "
            f"Setting: {identity['background']}. A clear conversational English voice suited to this adult. "
            'Natural facial asymmetry and ordinary skin texture; do not resemble any real person. '
            'One person is visible, addressing an unseen partner just beside the lens. '
            'Keep identity, wardrobe, lighting and voice consistent across this scene.')


def local_direction(inputs, cast):
    if inputs['mode'] != 'current_state':
        raise ValueError('Only T1/T3 current-state nodes are authored for offline video')
    persona = inputs['persona']
    expression = inputs['public_expression']
    family = expression_family(expression)
    acting = FAMILY[family]
    traits = ', '.join(persona.get('temperament', []))
    values = ', '.join(persona.get('core_values', []))
    cues = ' '.join(f'{k.replace("_", " ")}: {", ".join(v) if isinstance(v, list) else v}.'
                    for k, v in expression.items() if v)
    background = inputs['context']['background']
    # Current state and observable cues already encode the response to the
    # partner. Competing quoted dialogue can leak into the generated soundtrack.
    situation = (background + '\nThe speaker is responding to the unseen conversation partner at this checkpoint. '
                 'The situation is private acting context, never additional dialogue. '
                 'Do not invent a later response, a resolution, or new facts beyond this checkpoint.')
    psychology = (state_prose(inputs['state_before'], inputs['state_after']) + ' '
        f'The established temperament is {traits}; important values include {values}. '
        f"Communication style: {persona.get('communication_style', '')} "
        f"Conflict style: {persona.get('conflict_style', '')} "
        'Let these forces coexist. Situational concern does not automatically imply hostility toward the partner. '
        'Cooperation is not unconditional agreement, and professional composure is not the disappearance of emotion. '
        'The visible reaction should remain compatible with the public expression specified below.')
    objective = (f"Decision style: {persona.get('decision_style', '')} "
        'Deliver the exact short line as the next useful conversational step in this particular situation. '
        'A question seeks an answer that has not arrived; a conditional statement keeps its condition; '
        'a commitment expresses intention without showing the action already completed. '
        'Use a visible thought process to connect the situation, the breath and the words. '
        'Do not perform for an audience or announce the private emotional state.')
    beats = [
        'Opening reaction: ' + acting['opening'] + ' Follow the source direction: ' + cues +
        ' Keep the preparation brief enough that the dialogue starts promptly. Prioritize a coherent reaction over extra gestures.',
        'First phrase: release a usable breath and let the lips separate naturally. The jaw and cheeks '
        'respond to real English articulation while the eyes keep a clear conversational focus. '
        'Carry the current state into the weight and availability of the voice, without reciting an emotion. '
        'The face and neck should respond together, with small asymmetries and tiny timing differences. '
        'Avoid moving the brows on every syllable or bobbing the head to mark each word.',
        'Changing thought within the line: ' + acting['middle'] +
        ' Let a meaningful phrase, contrast or condition in the actual sentence drive the transition. '
        'Do not insert a long silent pause or add an emotional event that would require more time than the shot allows.',
        'Finish and listening tail: ' + acting['ending'] +
        ' Finish every syllable before the tail. Let the mouth settle from articulation rather than snapping '
        'into a fixed pose. The listening beat is short but alive; its expression must not imply that '
        'an unseen answer or an unrecorded event has already changed the state.'
    ]
    voice = (f"Public delivery guidance: {expression.get('prosody', 'natural conversational pace')}; "
        f"{expression.get('speech_style', 'clear connected speech')}. "
        'The entire short sentence must fit naturally into the shot. Emphasize the practical distinction '
        'or commitment carried by its actual words, preserving negation and uncertainty. '
        'Use connected speech with an ordinary conversational volume and the same voice timbre throughout '
        'this scene. Do not draw out the final word, recite word by word, add filler, or let an expressive '
        'inhale consume the time needed for the sentence.')
    avoid = ('Do not invent a success, refusal, admission, decision or personal accusation that the source '
        'does not establish. No automatic smile after a difficult line, no permanent scowl, no fear displayed '
        'as theatrical shock, and no emotional reversal simply to make the clip busy. The supplied current '
        'state and public cues constrain the performance; the actor must remain natural within those constraints.')
    return dict(cast=cast, situation=situation, psychology=psychology, objective=objective,
                beats=beats, voice=voice, avoid=avoid,
                grounding=[dict(source_paths=['state_before', 'state_after'], interpretation='Current values and actual changes, no later state.'),
                           dict(source_paths=['persona'], interpretation='Preserve temperament, values and interaction style.'),
                           dict(source_paths=['public_expression'], interpretation=f'Public movement family: {family}; no invented semantic change.')])


def online_prompt(identity, event_family, duration=5):
    """Render a reusable event performance without response/state-number leakage."""
    acting = FAMILY[event_family]
    return (
        f'Create one continuous {duration:g}-second photorealistic live-action dramatic reaction shot. '
        'Generate facial acting, breathing and body movement together, with synchronized nonverbal audio. '
        'This person is listening and reacting silently. There is no speech, lip-synced dialogue, narration '
        'or mouthed sentence. Prioritize a believable connected thought over a sequence of poses.\n\n'
        'CHARACTER AND FRAME\n' + cast_text(identity).replace(
            ' A clear conversational English voice suited to this adult.', '').replace(
            'lighting and voice consistent', 'lighting consistent') + '\n'
        'Use a fixed eye-level medium close-up, from upper chest to above the head. Keep both hands outside '
        'the frame. Leave enough room to see breathing in the neck and upper shoulders. Use soft practical '
        'lighting and a quiet blurred background. If an original generated reference video is supplied, '
        'use only its fictional identity, wardrobe, framing and lighting. Do not replay its words or '
        'copy its emotional sequence; the current reaction below is the required performance.\n\n'
        'INNER MOVEMENT\n' + acting['meaning'] + '\n'
        'This is a reusable reaction to a kind of state change, not a reenactment of one particular '
        'dialogue. Do not invent an event, incoming message or decision to justify it. Let the person '
        'have a thought that can be read through attention, breath and the relation between eyes and mouth. '
        'The direction describes the emotional movement, not a diagnostic label to display. A person can '
        'be affected and still behave with restraint. Keep the expression visible at ordinary viewing size '
        'without relying on an exaggerated gesture or on the viewer zooming into the face.\n\n'
        'CONTINUOUS PERFORMANCE\nOpening: ' + acting['opening'] + '\n\n'
        'As the reaction develops, let thought lead the breath, and let breath support the small physical '
        'adjustment. The eyes, brow, mouth, neck and shoulders should not all start or reverse at precisely '
        'the same instant. Maintain coherent anatomy and the same person through the motion. Do not use '
        'a repeated blink pattern, an eyebrow cycle, a rhythmic head bob or a held facial mask to signal '
        'emotion. A natural blink can occur if motivated by the transition, without obscuring the main reaction.\n\n'
        'Developing thought: ' + acting['middle'] + '\n\n'
        'Let the short performance have room to settle. A deliberate reaction need not grow continuously '
        'toward a dramatic peak. Preserve the difference between what the person feels and how they choose '
        'to make themselves available in conversation. The mouth stays naturally closed or parts only for '
        'an unvoiced breath; it must not form recognizable words. Any small adjustment of posture should '
        'travel through the neck and upper chest instead of making the head float independently of the body.\n\n'
        'Listening tail: ' + acting['ending'] + '\n'
        'Keep the person alive through the final frame. Do not end in a freeze, abrupt neutral reset, '
        'or expression implying a new event after the specified reaction. The opening, development and '
        'settling form one continuous take, not cuts, jumps, rigid timecodes or separate demonstrations.\n\n'
        'NATIVE AUDIO\n' + acting['audio'] + '\n'
        'Use only clean room ambience, natural unvoiced breath and incidental clothing movement. Match '
        'the audible breath to the visible body; do not add a stock gasp, laugh, hum, sob, scream or sigh '
        'as a detached sound effect. There is no voice, music, off-camera dialogue, instruction or narration.\n\n'
        'IMAGE AND PERFORMANCE FINISH\nReal skin texture, small natural asymmetries, stable gaze and '
        'consistent lighting. Keep the emotional change readable in the normal-sized shot, with the '
        'rest of the face participating naturally. No hands entering the shot, props, chair demonstrations, '
        'reclining with arms behind the head, large recoil, face touching or waving. No subtitles, labels, '
        'scores, names, numbers, interface graphics, logos or visible writing. Do not visually encode '
        'any threshold or hidden category. The result is an ordinary human reaction in a conversation.'
    )


NEW_SHOT_CHANGES = {
    'activated_tension': 'Attention stops briefly; the inner brows gather, lower eyelids tighten and lips press together. The jaw firms a moment later. A small visible catch of breath settles into controlled unresolved tension. Keep the gaze on the partner and finish concerned, without a smile.',
    'easing_tension': 'Begin with residual brow and jaw tension, then let the inner brows separate, lower eyelids soften, jaw unclench and shoulders release. The closed mouth settles into a gentler, slightly asymmetric line. End attentive and less braced, with some uncertainty still present.',
    'open_engagement': 'The eyes find the partner with clearer interest; the brows lift slightly and settle, lip tension releases, and the upper chest makes a small forward adjustment. Finish engaged and expectant with a modest acknowledgement, without implying agreement.',
    'guarded_withdrawal': 'Begin with eye contact, then draw the inner brows together and close the lips more firmly. Break eye contact downward and to one side; slowly turn the head about twelve degrees away and let the upper body draw slightly back. End guarded and less available, without a theatrical recoil.',
    'firm_boundary': 'Gather attention into a steady direct gaze. The jaw sets and the closed lips become firm while the neck and upper chest straighten a little. Keep the eyebrows composed and hold the boundary through calm resolve, without an angry grimace or crossed-arm demonstration.',
    'risk_concern': 'Let an attentive gaze become more alert: the inner brows lift and gather, the lower lids tense and the jaw pauses. Make a small checking glance, then return to the partner with visible concern and deliberation. Do not perform shock, a large recoil or a scream.',
    'cautious_relief': 'A little held tension leaves the jaw and shoulders; the eyes soften and one corner of the closed mouth briefly warms. Then a small checking glance and a trace of brow tension remain. Finish cautiously relieved, without celebration or a broad smile.',
}


def fresh_performance_prompt(prompt, *, duration=4, event_family=None):
    """Request a new temporal performance, not an audio edit of existing frames."""
    intro = (f'Extend video1 forward in time. Generate ONLY the next {duration:g} seconds AFTER video1 has finished. '
        'Do not replay any existing reference frames or its speaking motion. Preserve the original fictional '
        'actor identity, wardrobe, camera and setting, while creating a new continuous performance. ')
    if event_family:
        # A single audio contract avoids turning breath directions into dialogue.
        prompt = prompt.replace('with synchronized nonverbal audio', 'with a quiet room-tone soundtrack')
        prompt = prompt.replace('or parts only for an unvoiced breath', 'throughout the reaction')
        if 'NATIVE AUDIO\n' in prompt:
            start = prompt.index('NATIVE AUDIO\n')
            end = prompt.index('\n\nIMAGE AND PERFORMANCE FINISH', start)
            prompt = prompt[:start] + ('NATIVE AUDIO\nOnly faint steady indoor room tone. No human vocal sound, '
                'audible breath, words, syllables, whispers, humming or offscreen speaker. '
                'Breathing is visible in the chest only; keep the lips gently closed.') + prompt[end:]
        intro += ('The person has finished speaking and now listens silently. Keep the lips gently closed '
            'throughout. The sole soundtrack is faint steady indoor room tone: no voice, words, syllables, '
            'whispers, humming or audible breath. Breathing is visible only.\n\n'
            'REQUIRED NEW EMOTIONAL MOVEMENT\n' + NEW_SHOT_CHANGES[event_family] + '\n\n')
    else:
        intro += ('This is the next conversational beat, with the current state and private acting context below. '
            'Speak only the exact locked line that follows, once, and replace the previous facial performance '
            'with the new thought, objective and emotional movement described below. No additional words.\n\n')
    return intro + prompt


def still_identity_performance_prompt(prompt, *, duration=4, event_family=None):
    """An original provider still preserves identity without a motion timeline."""
    if event_family:
        directed = fresh_performance_prompt(prompt, duration=duration, event_family=event_family)
        body = directed[directed.index('REQUIRED NEW EMOTIONAL MOVEMENT'):]
    else:
        body = ('Speak only the exact locked line below, once. Act from the current state and '
                'private direction below, with no additional words.\n\n' + prompt)
    return (f'Use image1 as the visual identity reference for a NEW {duration:g}-second photorealistic '
        'live-action dramatic performance. Preserve this original fictional person, hair, wardrobe '
        'and setting. The image supplies appearance only: create all facial acting and body motion '
        'from the current direction, as a continuous natural take. Keep the fixed medium close-up '
        'and show the emotional change clearly without theatrical exaggeration.\n\n' + body)
