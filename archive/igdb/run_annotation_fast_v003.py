#!/usr/bin/env python3
import sys, re, json, csv, time
from pathlib import Path
from collections import Counter
sys.path.insert(0, '/mnt/data')
import annotate_igdb_archetypes_agent_v001 as ag

# Better high-level title patterns inserted before broad simulator/sandbox rules.
front_patterns = [
    (re.compile(r'\bminecraft\b', re.I), ('Player avatar / Steve or Alex','player_avatar_weakly_defined','Creator/Artist','Explorer/Seeker','Hero/Warrior','general_knowledge','Sandbox avatar; Steve/Alex are default player representations.')),
    (re.compile(r'\banimal crossing\b', re.I), ('Player villager','player_avatar_weakly_defined','Everyman/Orphan','Creator/Artist','Caregiver/Guardian','metadata_inference','Life-sim player villager role.')),
]
ag.PATTERNS = front_patterns + ag.PATTERNS

NAME_RE = r"[A-Z][A-Za-zÀ-ÖØ-öø-ÿ0-9'’\-\.]+(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ0-9'’\-\.]+){0,4}"
NAMED_RES = [
    re.compile(rf"(?:main protagonist|protagonist|hero|main character|lead character)\s+(?:is|named|called)\s+({NAME_RE})"),
    re.compile(rf"(?:follows|centers on|centres on|focuses on)\s+(?:the\s+story\s+of\s+)?({NAME_RE})"),
    re.compile(rf"named\s+({NAME_RE})"),
]
CONTROL_RES = [
    re.compile(rf"(?:player|players|you)\s+(?:controls?|take control of|takes control of|plays as|play as|embodies|assumes the role of)\s+(?:the\s+role\s+of\s+)?(?:a|an|the)?\s*({NAME_RE})", re.I),
]
ROLE_RES = [
    re.compile(r'(?:you|player|players)\s+(?:are|is|become|play as|take on the role of|assume the role of)\s+(?:a|an|the)?\s*([^\.,;]{3,70})', re.I),
    re.compile(r'(?:you|player|players)\s+(?:control|controls|pilot|guide|command)\s+(?:a|an|the)?\s*([^\.,;]{3,70})', re.I),
]
KEYWORDS = re.compile(r'protagonist|main character|lead character|player|players|you |follows|centers on|centres on|focuses on|named|plays as|play as|controls|takes control|assume|role', re.I)
ROLE_NOUNS = re.compile(r'\b(hero|warrior|soldier|agent|spy|detective|investigator|hunter|survivor|pilot|driver|commander|manager|ruler|king|queen|prince|princess|wizard|mage|witch|thief|assassin|pirate|criminal|bandit|diver|astronaut|student|child|boy|girl|knight|samurai|ninja|robot|dragon|animal|cat|dog|trainer|farmer|chef|artist|writer|builder|explorer|adventurer|avatar|character|crew|squad|team|party)\b', re.I)
BAD_ROLE_START = re.compile(r'^(first|left|right|after|before|when|while|with|selecting|represented|guided|hit|pursuing|supposed|allowing|trying|another|what|how|where|in|on|to|for)\b', re.I)
BAD_ROLE_WORDS = re.compile(r'\b(options|among|points|score|button|keys|game|levels|screen|cards|pieces|gun located|which must|trying to|you can|you must)\b', re.I)

def clean_named(c):
    c = ag.clean_candidate(c)
    if not c: return ''
    # Proper-name extractions must really start uppercase in the captured text.
    if not c[0].isupper(): return ''
    # Reject sentence fragments that slipped through.
    if BAD_ROLE_START.search(c) or BAD_ROLE_WORDS.search(c): return ''
    return c

def clean_role(c):
    c = ag.clean_candidate(c)
    if not c: return ''
    if BAD_ROLE_START.search(c) or BAD_ROLE_WORDS.search(c): return ''
    # Keep only if it actually contains a role noun.
    if not ROLE_NOUNS.search(c): return ''
    # Normalize overly generic first-person roles.
    c = re.sub(r'^(?:the\s+)?player\s+', 'player ', c, flags=re.I)
    if len(c.split()) > 6:
        c = ' '.join(c.split()[:6])
    # Lowercase roles are roles, not fixed names.
    if c[0].islower():
        return c[:1].upper() + c[1:]
    return c

def fast_extract(row):
    text = ' '.join([row.get('summary','') or '', row.get('storyline','') or ''])
    if not text or not KEYWORDS.search(text[:5000]):
        return '', ''
    text = re.sub(r'\s+', ' ', text[:4500])
    # Proper named patterns: case-sensitive candidate, case-insensitive keyword handled by alternative not needed for IGDB prose mostly.
    # Also run a lower-case keyword version manually by searching on exact phrases but preserving candidate case.
    for rx in NAMED_RES:
        m = rx.search(text)
        if m:
            c=clean_named(m.group(1))
            if c: return c, 'metadata_inference'
    # Common proper-name after control/play-as.
    for rx in CONTROL_RES:
        m = rx.search(text)
        if m:
            c = clean_named(m.group(1))
            if c: return c, 'metadata_inference'
    # Role patterns: accept only controlled role nouns.
    for rx in ROLE_RES:
        m = rx.search(text)
        if m:
            c=clean_role(m.group(1))
            if c: return c, 'metadata_inference'
    return '', ''

def better_infer_ptype(protag, row):
    if protag and (protag[0].islower() or re.search(r'\b(player|avatar|character|hero|hunter|survivor|pilot|driver|commander|manager|soldier|agent|detective|trainer|farmer|student|child|boy|girl)\b', protag, re.I)):
        if re.search(r'player|avatar|character|trainer', protag, re.I): return 'player_avatar_weakly_defined'
        return 'fixed_role_single'
    return ag._orig_infer_ptype(protag, row) if hasattr(ag, '_orig_infer_ptype') else ag.infer_ptype(protag, row)

# Monkeypatch once
ag.extract_explicit_protagonist = fast_extract
if not hasattr(ag, '_orig_infer_ptype'):
    ag._orig_infer_ptype = ag.infer_ptype
ag.infer_ptype = better_infer_ptype

def process_with_resume(start_clean=True):
    base=Path('/mnt/data')
    out=base/'igdb_needs_llm_annotation_filled_metadata_agent_v001.csv'
    delta=base/'igdb_new_metadata_agent_annotations_delta_v001.csv'
    inp=base/'igdb_needs_llm_annotation_v001.csv'
    if start_clean:
        for p in [out,delta,base/'igdb_metadata_agent_annotation_summary_v001.json']:
            try: p.unlink()
            except FileNotFoundError: pass
        return ag.process_file(inp, out, delta)
    # Resume mode
    with open(out,newline='',encoding='utf-8',errors='replace') as f:
        written=sum(1 for _ in csv.reader(f))-1
    stats=Counter()
    with open(inp,newline='',encoding='utf-8-sig',errors='replace') as f_in:
        reader=csv.DictReader(f_in); fieldnames=reader.fieldnames
        with open(out,'a',newline='',encoding='utf-8') as f_out, open(delta,'a',newline='',encoding='utf-8') as f_delta:
            writer=csv.DictWriter(f_out,fieldnames=fieldnames,extrasaction='ignore')
            delta_writer=csv.DictWriter(f_delta,fieldnames=fieldnames,extrasaction='ignore')
            for i,row in enumerate(reader,1):
                if i<=written: continue
                filled,ann=ag.fill_row(row, stats)
                writer.writerow(filled)
                if ann is not None: delta_writer.writerow(filled)
    return stats

if __name__ == '__main__':
    t0=time.time()
    stats=process_with_resume(start_clean=True)
    base=Path('/mnt/data')
    summary={'agent_model':ag.AGENT_MODEL+'_fast_extract_v003','needs_stats':dict(stats),'elapsed_sec':round(time.time()-t0,2)}
    with open(base/'igdb_metadata_agent_annotation_summary_v001.json','w',encoding='utf-8') as f: json.dump(summary,f,ensure_ascii=False,indent=2)
    print(json.dumps(summary,ensure_ascii=False,indent=2)[:5000])
