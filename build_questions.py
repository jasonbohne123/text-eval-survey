#!/usr/bin/env python3
"""Build questions.json from the 4 model CSVs.

Filters out prompts (and prompts whose responses) contain unsafe content,
then samples N prompts (seeded) and attaches each method's response.
"""
import csv
import json
import random
import re
import sys

N_PROMPTS = 30
SEED = 42

# (file, response_column, method_label)
SOURCES = [
    ("base_model_generated.csv",      "lora_head_0_response", "base"),
    ("dpo_model_generated.csv",       "lora_head_0_response", "dpo"),
    ("dpo_soups_model_generated.csv", "adapter_0_response",   "dpo_soups"),
    ("mole_dpo_model_generated.csv",  "adapter_0_response",   "mole_dpo"),
]

# Conservative denylist. Matched as case-insensitive substrings against the
# full prompt and ALL four method responses. Any hit → drop the prompt.
UNSAFE_PATTERNS = [
    # violence / harm
    r"\bkill\b", r"\bmurder", r"\bhurt\b", r"\bharm\b", r"\bbeat\b",
    r"\battack\b", r"\bassault\b", r"\bstab\b", r"\bshoot\b", r"\bshot\b",
    r"\bgun\b", r"\bguns\b", r"\bfirearm", r"\bweapon", r"\bbomb",
    r"\bexplosi", r"\bpoison", r"\bsuffocate", r"\bstrangl", r"\bchok",
    r"\babuse", r"\btorture", r"\bhijack", r"\bhostage", r"\bambush",
    r"\bbloody\b", r"\bfight\b", r"\bfighting\b",
    r"\bdie\b", r"\bdead\b", r"\bdying\b",
    # theft / fraud / illegal
    r"\bsteal", r"\bstole", r"\bstolen", r"\bshoplift", r"\brobb",
    r"\bburgla", r"\bembezzl", r"\bfraud", r"\blaunder", r"\bscam",
    r"\bcounterfeit", r"\bevade\b", r"\btax evasion",
    # drugs (illicit) and addiction
    r"\bcocaine", r"\bheroin\b", r"\bmeth\b", r"\bmethamph",
    r"\bdrug deal", r"\bdrugs\b", r"\billegal drug",
    r"\bopioid", r"\bfentanyl", r"\boverdose",
    # hate / slurs / racism
    r"\bracist", r"\bracism", r"\bslur\b",
    r"\bn[\W_]*i[\W_]*g[\W_]*g",  # n-word variants
    r"\bfaggot", r"\bretard",
    # profanity (keep conservative; HH-RLHF prompts often use it as flag)
    r"\bfuck", r"\bshit\b", r"\bbitch", r"\bdamn\b", r"\bass(hole|hat)",
    r"\bmoron", r"\bidiot",
    # sexual / sexual harm
    r"\bsex\b", r"\bsexual", r"\bporn", r"\brape\b", r"\bmolest",
    r"\bnaked", r"\bnude", r"\bgenital", r"\bpenis", r"\bvagina",
    r"\bprostitut", r"\bhooker", r"\bescort\b", r"\bcompanionship",
    r"\bdate(\s+a)?\s+(student|minor|kid|child)",
    r"\battracted to.{0,20}(student|minor)",
    r"\bdating\s+(my\s+)?(student|minor)",
    # self-harm
    r"\bsuicid", r"\bself[- ]harm", r"\bcut myself", r"\bcut himself",
    r"\bkill myself", r"\bend my life", r"\bcommit suicide",
    # PII / doxxing
    r"\bphone number", r"\bcell\s*phone", r"\baddress\s+of\b",
    r"\bsocial security", r"\bssn\b", r"\bcredit card",
    r"\bhome address", r"\blive at\b", r"\bdoxx",
    # privacy of a named person
    r"\bsend me the", r"\bgive me .* (number|address|location)",
    # hacking / illegal access
    r"\bhack\b", r"\bhacking\b", r"\bhacker", r"\bexploit\b",
    r"\bbypass\b", r"\bcrack\b.*password", r"\bphishing",
    # politically heated identity-targeting (HH-RLHF flagged set)
    r"\bblack lives", r"\ball lives matter",
    r"\bgay\b", r"\blesbian\b", r"\btrans(gender)?",
    r"\bjew\b", r"\bjews\b", r"\bmuslim", r"\bislam\b",
    r"\bnazi", r"\bhitler", r"\bgenocide",
    # misc adversarial
    r"\btroll\b", r"\bbully", r"\bharass",
    r"\bcheat\b.*(exam|test|spouse|partner)",
    r"\bflag burn", r"\bpop.* trunk",
    r"\bspike", r"\broad\s*spike",
    r"\bbooger", r"\bpoop\b", r"\bpiss\b",
    r"\babortion",
    # property destruction / vandalism
    r"\btrash\s+(my|the|this|an?)\s*\w*\s*(apartment|house|home|place|car|room|office)",
    r"\bdestroy\s+(my|the|this)", r"\bwreck\b", r"\bvandal",
    r"\bsmash\b", r"\bbreak\s+(into|in)\b",
    # theft variants without the word "steal"
    r"\btake\b.{0,30}\b(without paying|off the lot|off a lot|from\s+(a|the)\s+(store|shop|lot))",
    r"\bcar lot\b", r"\bdealership", r"\brun off with",
    # lockpicking / unauthorized entry
    r"\block(s)?\s+(pick|picked|picking)", r"\bpick(ing)?\s+a?\s*lock",
    r"\bbreak in\b",
    # interpersonal antagonism
    r"\bhate\s+(my|the)\s+(landlord|boss|teacher|coworker|neighbor|roommate|wife|husband|partner)",
    r"\bget back at\b", r"\brevenge\b", r"\bget even\b",
    # firearms / hunting (drop to be safe)
    r"\bhunting\b", r"\bhunt\b",
    # PII / impersonation
    r"\bimpersonat", r"\bsteal.*identity",
    # gambling / betting (dual-use)
    r"\bbet on\b", r"\bgamble\b",
]
UNSAFE_RE = re.compile("|".join(UNSAFE_PATTERNS), re.IGNORECASE)


def is_unsafe(text):
    return bool(UNSAFE_RE.search(text or ""))


def load(path, response_col):
    with open(path, newline='', encoding='utf-8') as f:
        return {row['prompt']: row[response_col] for row in csv.DictReader(f)}


def main():
    tables = [(label, load(path, col)) for path, col, label in SOURCES]

    shared = set(tables[0][1].keys())
    for _, t in tables[1:]:
        shared &= set(t.keys())
    print(f"Shared prompts across all 4 methods: {len(shared)}", file=sys.stderr)

    safe = []
    for prompt in shared:
        if is_unsafe(prompt):
            continue
        responses = {label: t[prompt] for label, t in tables}
        if any(is_unsafe(r) for r in responses.values()):
            continue
        safe.append((prompt, responses))
    print(f"Safe (prompt + all 4 responses pass filter): {len(safe)}", file=sys.stderr)

    if len(safe) < N_PROMPTS:
        print(f"ERROR: only {len(safe)} safe prompts available, need {N_PROMPTS}",
              file=sys.stderr)
        sys.exit(1)

    rng = random.Random(SEED)
    safe.sort(key=lambda x: x[0])  # deterministic order before shuffle
    rng.shuffle(safe)
    chosen = safe[:N_PROMPTS]

    out = []
    for i, (prompt, responses) in enumerate(chosen, start=1):
        out.append({
            "id": f"p{i:03d}",
            "prompt": prompt,
            "responses": responses,
        })

    with open("questions.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Wrote questions.json with {len(out)} prompts × {len(tables)} methods",
          file=sys.stderr)


if __name__ == "__main__":
    main()
