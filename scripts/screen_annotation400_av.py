"""Local unprompted speech checks for individual paid video segments."""
import argparse
from difflib import SequenceMatcher
import json
import re
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.build_annotation400 import load,save,sha
from offline.speech_screen import normalized

SCREEN_VERSION = 'english_critical_words_clock_notation_v6'

def speech_text(text):
    # Orthographic variants are acoustically identical; preserve every content
    # word, number and negation. Do not forgive substituted technical terms.
    text = re.sub(r'\bok\b', 'okay', text, flags=re.I)
    text = re.sub(r'\borganise\b', 'organize', text, flags=re.I)
    text = re.sub(r'\bnormalisation\b', 'normalization', text, flags=re.I)
    text = re.sub(r'\bauthorise\b', 'authorize', text, flags=re.I)
    text=text.lower().replace('’',"'")
    for source,target in {"can't":'cannot',"won't":'will not',"don't":'do not',"doesn't":'does not',"didn't":'did not',"isn't":'is not',"aren't":'are not',"wasn't":'was not',"weren't":'were not',"haven't":'have not',"hasn't":'has not',"hadn't":'had not',"shouldn't":'should not',"wouldn't":'would not',"couldn't":'could not'}.items():
        text=re.sub(r'\b'+re.escape(source)+r'\b',target,text)
    text=re.sub(r'\bcannot\b','can not',text)
    units='zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    tens={'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
    text=re.sub(r'\b('+'|'.join(tens)+r')(?:[ -]('+'|'.join(units[1:10])+r'))?\b',lambda m:str(tens[m[1].lower()]+(units.index(m[2].lower()) if m[2] else 0)),text,flags=re.I)
    text=re.sub(r'\b('+'|'.join(units)+r')\b',lambda m:str(units.index(m[1].lower())),text,flags=re.I)
    return text

def speech_normalized(text):return normalized(speech_text(text))

def critical_content_matches(expected, observed):
    """Compare ordered negations and numbers, retaining explicit clock semantics.

    ASR may write a spoken clock time with a colon or a decimal separator.
    Only a clock phrase in the reference licenses that spelling equivalence;
    prices, decimal quantities, concatenated digits and changed times stay distinct.
    """
    hours = 'one two three four five six seven eight nine ten eleven twelve'.split()
    minute_units = 'one two three four five six seven eight nine'.split()
    minute_teens = 'ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
    minute_tens = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50}
    minute_pattern = ('(?:' + '|'.join(minute_tens) + ')(?:[ -](?:' +
                      '|'.join(minute_units) + '))?|(?:' + '|'.join(minute_teens) + ')')
    clock_words = re.compile(r'\b(' + '|'.join(hours) + r')[ -](' + minute_pattern + r')\b')

    def clock_value(match):
        parts = re.split('[ -]', match[2])
        minutes = (minute_teens.index(parts[0]) + 10 if parts[0] in minute_teens
                   else minute_tens[parts[0]] + (minute_units.index(parts[1]) + 1 if len(parts) > 1 else 0))
        return f'{hours.index(match[1]) + 1}:{minutes:02}'

    def tokens(text):
        text = clock_words.sub(clock_value, text.lower().replace('’', "'"))
        text = speech_text(text)
        return text, list(re.finditer(r'\b(?:no|not|never|without)\b|\d{1,2}:[0-5]\d|\d+(?:\.\d+)?', text))

    _, reference = tokens(expected)
    transcript_text, transcript = tokens(observed)
    position = 0
    for match in reference:
        if position >= len(transcript):
            return False
        wanted, actual = match[0], transcript[position][0]
        if wanted == actual:
            position += 1
            continue
        if ':' in wanted:
            clock = tuple(map(int, wanted.split(':')))
            if re.fullmatch(r'\d{1,2}\.[0-5]\d', actual):
                if clock == tuple(map(int, actual.split('.'))):
                    position += 1
                    continue
            # Some unprompted ASR models separate the spoken hour and minute
            # with a comma. Require adjacent, unchanged numeric tokens; an
            # intervening word (e.g. "and") never joins separate quantities.
            if actual.isdigit() and position + 1 < len(transcript):
                following = transcript[position + 1]
                separator = transcript_text[transcript[position].end():following.start()]
                if (following[0].isdigit() and re.fullmatch(r'[,\s]+', separator)
                        and clock == (int(actual), int(following[0]))):
                    position += 2
                    continue
        return False
    return position == len(transcript)

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--request-id',required=True);a=p.parse_args()
    m=load(a.manifest);record=next(r for r in m['requests'] if r['request_id']==a.request_id)
    path=ROOT/record['video_file'];h=sha(path);out=a.manifest.parent/'segment_speech_screen.json'
    result=load(out) if out.exists() else {}
    old=result.get(a.request_id,{})
    if old.get('video_sha256')==h and old.get('screen_version')==SCREEN_VERSION:
        print(json.dumps(old));return
    if old.get('video_sha256')==h:
        text,language=old['transcript'],old['language']
    else:
        from faster_whisper import WhisperModel
        model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=4,download_root=str(ROOT/'.local_models/faster-whisper'),local_files_only=True)
        segments,info=model.transcribe(str(path),beam_size=5,vad_filter=True,condition_on_previous_text=False)
        text=''.join(s.text for s in segments).strip();language=info.language
    expected=load(ROOT/record['request_file'])['audio']['exact_line']
    score=SequenceMatcher(None,speech_normalized(expected),speech_normalized(text),autojunk=False).ratio()
    small={'model':'small','transcript':text,'language':language,'normalized_similarity':round(score,4)}
    recheck=None
    if score<0.98 or language!='en' or not critical_content_matches(expected,text):
        from faster_whisper import WhisperModel
        model=WhisperModel('large-v3-turbo',device='cpu',compute_type='int8',cpu_threads=4,download_root=str(ROOT/'.local_models/faster-whisper'),local_files_only=True)
        segments,info=model.transcribe(str(path),beam_size=5,vad_filter=True,condition_on_previous_text=False)
        alternate=''.join(s.text for s in segments).strip()
        ratio=SequenceMatcher(None,speech_normalized(expected),speech_normalized(alternate),autojunk=False).ratio()
        recheck={'model':'large-v3-turbo','transcript':alternate,'language':info.language,'normalized_similarity':round(ratio,4)}
        text,language,score=alternate,info.language,ratio
    row={'video_sha256':h,'expected':expected,'transcript':text,'language':language,'normalized_similarity':round(score,4),'screen_version':SCREEN_VERSION,
         'critical_content_match':critical_content_matches(expected,text),
         'machine_screen_passed':score>=0.98 and language=='en' and critical_content_matches(expected,text),'human_review':'pending','speech_verified':False,'initial_screen':small,'large_model_recheck':recheck}
    result[a.request_id]=row;save(out,result);print(json.dumps(row))

if __name__=='__main__':main()
