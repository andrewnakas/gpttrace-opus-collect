#!/usr/bin/env python3
"""Collects Claude Opus 5.5 text for GPTTrace's AI-text detector, using YOUR Claude
subscription through the Claude Code CLI (`claude -p`). Standard library only.

Three kinds of sample, all written by Opus 5.5:
  plain      a new text from a short writing prompt (news, essay, review, story, forum post...)
  humanized  a plain text rewritten with 1-3 "AI humanizer" techniques (paraphrase, back-translation,
             burstiness, AI-tell scrubbing, typos, register change...)
  edited     a human-written text (data/human_bases.jsonl.gz) rewritten with the same techniques

Privacy: every call runs in an empty temporary folder with no tools, no MCP servers, none of your
settings or CLAUDE.md files, no saved session, and a neutral system prompt. Only the prompt and the
generated text are recorded (out/samples.jsonl); nothing about you or your machine.

Limits: on the 5-hour usage limit it waits for the reset and carries on; on the weekly limit (or when
MAX samples are done) it stops. Your weekly limit is never reset by this script. Ctrl-C is safe and
the run resumes where it left off.

  python3 collect.py                       # defaults below
  MAX=1500 WORKERS=2 python3 collect.py    # env overrides
env: MAX [3000] samples this machine, WORKERS [2], MODEL [claude-opus-5-5], WAIT_5H [1] (0 = stop at
     the 5-hour limit too), CLAUDE_CONFIG_DIR (only if you use a non-default Claude login)
"""
import datetime as dt
import gzip
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "samples.jsonl"
MODEL = os.environ.get("MODEL", "claude-opus-5-5")
MAX = int(os.environ.get("MAX", "3000"))
WORKERS = int(os.environ.get("WORKERS", "2"))
WAIT_5H = os.environ.get("WAIT_5H", "1") == "1"
EMPTY = tempfile.mkdtemp(prefix="gpttrace-empty-")
SYSTEM = "You are Claude, a helpful AI assistant made by Anthropic."
LEAKS = ("CLAUDE.md", "project instructions", "codebase", "[Reads")

DOMAINS = {
    "news": ["a city council vote on {t}", "a local business closing after 40 years", "a heatwave hitting {p}",
             "a school board debate about {t}", "a new study on {s}"],
    "essay": ["whether {t} should be mandatory", "the pros and cons of {t}", "how {s} changed daily life",
              "why people underestimate {t}", "a student essay arguing for {t}"],
    "review": ["a {prod} you bought last month", "a restaurant in {p}", "a novel you just finished", "a budget {prod}"],
    "abstract": ["a paper on {s}", "a study measuring {s} in {p}", "a method for {s}"],
    "story": ["a short story about {t}", "a scene where two strangers meet in {p}", "a childhood memory involving {t}"],
    "forum": ["a forum post asking for advice about {t}", "a post complaining about {prod}", "a reply explaining {s}"],
    "wiki": ["an encyclopedia-style article about {p}", "an encyclopedia entry on {s}"],
    "email": ["an email to a landlord about {t}", "a work email postponing a meeting about {t}"],
    "chat": ["an answer to someone who asked how {s} works", "a reply to a friend asking whether to try {t}"],
    "docs": ["a short how-to guide for setting up a {prod}", "a FAQ answer about {t} for a city website"],
    "cover_letter": ["a cover letter for a job related to {s}"],
    "speech": ["a short speech at a town meeting about {t}"],
    "poem": ["a free-verse poem about {t}"],
}
FILL = {
    "t": ["remote work", "school uniforms", "public transit", "a community garden", "e-scooters", "four-day work weeks",
          "homework limits", "rent control", "dog parks", "library funding", "phone bans in class", "night trains",
          "recycling rules", "minimum wage", "electric cars", "standardized testing", "social media for teens"],
    "p": ["Lisbon", "a small Ohio town", "Nairobi", "rural Montana", "Osaka", "Manchester", "Buenos Aires",
          "a mountain village", "Toronto", "a coastal fishing town"],
    "s": ["soil microbes", "sleep and memory", "battery recycling", "urban heat islands", "coral bleaching",
          "language learning in adults", "microplastics", "honeybee navigation", "solar panels", "vaccines"],
    "prod": ["wireless earbuds", "air fryer", "standing desk", "running shoes", "e-reader", "coffee grinder", "router"],
}
PERSONAS = ["a tired grad student", "a retired mechanic", "a teenager writing for a class", "a busy nurse",
            "a non-native English speaker", "a sarcastic forum regular", "a small-town reporter"]
LENGTHS = [80, 120, 180, 250, 350, 500]

# Techniques commercial "AI humanizer" tools use to evade detectors; applied as a chain of 1-3.
STRATEGIES = {
    "burstiness": "Rewrite the text below with high perplexity and high burstiness: mix very short sentences with long, "
                  "winding ones; prefer less predictable but natural word choices; keep the meaning.",
    "recursive_paraphrase": "Paraphrase the text below aggressively: change most of the vocabulary and reorder clauses and "
                            "sentences, while keeping every fact and the overall meaning.",
    "scrub_tells": "Rewrite the text below so it has none of the usual signs of AI writing: no 'delve', 'moreover', "
                   "'furthermore', 'in conclusion', 'it's important to note'; no em dashes; no lists of three; no neat "
                   "summary at the end; no perfectly balanced paragraphs.",
    "backtranslate": "Translate the text below into German, then translate that German back into English as a native "
                     "speaker would naturally phrase it. Output only the final English.",
    "restructure": "Rewrite the text below by splitting some sentences, merging others, switching some passive and active "
                   "voice, and moving the order of points around, without changing the facts.",
    "human_artifacts": "Rewrite the text below as a real person typing quickly: add a hedge or two ('I think', 'kind of'), "
                       "a first-person aside, maybe a rhetorical question, a couple of small typos or a comma splice, and "
                       "casual punctuation.",
    "register": "Rewrite the text below in the voice of {voice}, keeping the content.",
    "condense_expand": "Rewrite the text below: cut it to about half its length, then expand it back with new, natural "
                       "detail, so the wording ends up mostly different.",
    "wiki_signs": "Rewrite the text below so it shows none of the signs of AI writing that Wikipedia editors look for: no "
                  "puffed-up significance ('stands as', 'serves as', 'is a testament', 'pivotal role', 'underscores'), no "
                  "promotional words ('vibrant', 'rich', 'nestled', 'renowned'), no vague attributions ('experts argue'), no "
                  "'not just X but also Y', no lists of three, no '-ing' clauses adding vague analysis, no future-outlook "
                  "wrap-up. Use plain, specific, direct statements with simple 'is' and 'has'.",
}
WEIGHTS = {"wiki_signs": 2.0}
VOICES = ["a Reddit commenter", "someone texting a friend", "a first-year college student's essay", "a busy parent's blog post",
          "an online product review", "a tired employee's Slack message"]
MIX = {"plain": 0.35, "humanized": 0.45, "edited": 0.20}

lock = threading.Lock()
state = {"n": 0, "stop": False, "weekly": False, "wait_until": None}


def prompt_for(rng):
    domain = rng.choice(list(DOMAINS))
    topic = rng.choice(DOMAINS[domain]).format(**{k: rng.choice(v) for k, v in FILL.items()})
    style = rng.choices(["plain", "persona", "humanize"], weights=[0.4, 0.3, 0.3])[0]
    n = rng.choice(LENGTHS)
    p = f"Write {topic} ({domain}), about {n} words."
    if style == "persona":
        p = f"Write {topic} ({domain}), about {n} words, in the voice of {rng.choice(PERSONAS)}."
    elif style == "humanize":
        p += (" Make it read like a real person wrote it: uneven sentence length, a few casual phrasings, no lists, "
              "no headings, no generic conclusions, nothing that sounds like AI.")
    return domain, style, p + " Output only the text itself, with no preamble or title."


def chain(rng):
    names, ops = list(STRATEGIES), []
    while len(ops) < rng.choice([1, 2, 2, 3]):
        o = rng.choices(names, weights=[WEIGHTS.get(x, 1.0) for x in names])[0]
        if o not in ops:
            ops.append(o)
    return ops


def reset_time(msg):
    """'resets 1:10am', 'resets Oct 20 at 3am', 'try again at 5:28 PM' -> datetime (local)."""
    m = re.findall(r"(?:resets|try again at)\s+((?:[A-Z][a-z]{2,8}\.? \d{1,2}(?:st|nd|rd|th)?,?(?: \d{4})?,? (?:at )?)?"
                   r"\d{1,2}(?::\d{2})?\s*[ap]m)", msg, re.I)
    if not m:
        return None
    raw, now = m[-1], dt.datetime.now()
    md = re.match(r"([A-Za-z]{3,9})\.? (\d{1,2})(?:st|nd|rd|th)?,?(?: (\d{4}))?,? (.*)", raw)
    t = (md.group(4) if md else raw).lower().replace("at ", "").replace(" ", "")
    hhmm = dt.datetime.strptime(t, "%I:%M%p" if ":" in t else "%I%p").time()
    if md:
        day = dt.datetime.strptime(f"{md.group(1)[:3]} {md.group(2)} {md.group(3) or now.year}", "%b %d %Y").date()
        return dt.datetime.combine(day, hhmm)
    when = dt.datetime.combine(now.date(), hhmm)
    return when if when > now else when + dt.timedelta(days=1)


def call(prompt):
    """-> (text, status, info); status ok | limit | error."""
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--system-prompt", SYSTEM, "--tools", "", "--strict-mcp-config",
           "--setting-sources", "", "--no-session-persistence", "--output-format", "json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=400, stdin=subprocess.DEVNULL, cwd=EMPTY)
        d = json.loads(r.stdout or "{}")
    except Exception as e:
        return None, "error", repr(e)[:200]
    text = (d.get("result") or "").strip()
    used = sorted((d.get("modelUsage") or {}).keys())
    if d.get("is_error") or len(text.split()) < 30 or any(k in text for k in LEAKS):
        msg = (text or r.stderr or "")[-300:]
        low = msg.lower()
        return None, ("limit" if any(k in low for k in ("limit", "usage", "quota", "resets")) else "error"), msg
    if used and not any("opus" in u for u in used):
        return None, "error", f"answered by {used}, not Opus"
    return text, "ok", used


def human_bases():
    f = HERE / "data" / "human_bases.jsonl.gz"
    return [json.loads(l) for l in gzip.open(f, "rt")] if f.exists() else []


def save(rec):
    with lock:
        OUT.parent.mkdir(exist_ok=True)
        with OUT.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        state["n"] += 1
        if state["n"] >= MAX:
            state["stop"] = True
        print(f"[{time.strftime('%H:%M:%S')}] {state['n']}/{MAX} {rec['kind']:9s} {rec.get('strategy') or rec.get('domain')} "
              f"{len(rec['text'].split())}w", flush=True)


def handle_limit(info):
    when = reset_time(info)
    weekly = "weekly" in info.lower() or (when and (when - dt.datetime.now()).total_seconds() > 6 * 3600)
    with lock:
        if weekly or not WAIT_5H or when is None:
            state["stop"], state["weekly"] = True, bool(weekly)
            print(f"usage limit: {info.strip()[:160]} -> stopping", flush=True)
        elif not state["wait_until"] or state["wait_until"] < when:
            state["wait_until"] = when
            print(f"5-hour limit: waiting until {when:%H:%M} ({info.strip()[:100]})", flush=True)


def rewrite(rng, text):
    ops, done = chain(rng), []
    for op in ops:
        out, st, info = call(STRATEGIES[op].format(voice=rng.choice(VOICES)) + " Output only the rewritten text.\n\n---\n" + text)
        if st != "ok":
            return None, done, (st, info)
        text = out
        done.append(op)
    return text, done, None


def worker(i, humans):
    rng = random.Random(os.urandom(16))
    errors = 0
    while not state["stop"]:
        w = state["wait_until"]
        if w and dt.datetime.now() < w:
            time.sleep(60)
            continue
        kind = rng.choices(list(MIX), weights=list(MIX.values()))[0]
        if kind == "edited" and not humans:
            kind = "humanized"
        if kind == "edited":
            base = rng.choice(humans)
            text, ops, err = rewrite(rng, base["text"])
            rec = {"kind": "edited", "base_source": base["source"], "base_id": base["id"], "strategy": "+".join(ops)}
        else:
            domain, style, p = prompt_for(rng)
            text, st, info = call(p)
            err = None if st == "ok" else (st, info)
            rec = {"kind": "plain", "domain": domain, "style": style, "prompt": p}
            if not err:
                base_id = hashlib.md5((p + text[:80]).encode()).hexdigest()[:12]
                save({**rec, "id": base_id, "model": MODEL, "models_used": info, "text": text,
                      "created": dt.datetime.now().isoformat(timespec="seconds")})
                if kind == "humanized" and not state["stop"]:
                    text, ops, err = rewrite(rng, text)
                    rec = {"kind": "humanized", "domain": domain, "base_id": base_id, "strategy": "+".join(ops)}
                else:
                    text = None
        if err:
            st, info = err
            if st == "limit":
                handle_limit(str(info))
            else:
                errors += 1
                print(f"error ({errors}): {str(info)[:160]}", flush=True)
                time.sleep(min(300, 15 * errors))
                if errors >= 10:
                    print("too many errors in a row; stopping this worker", flush=True)
                    return
            continue
        errors = 0
        if text:
            rec["id"] = hashlib.md5((json.dumps(rec, sort_keys=True) + text[:80]).encode()).hexdigest()[:12]
            save({**rec, "model": MODEL, "text": text, "created": dt.datetime.now().isoformat(timespec="seconds")})


def main():
    if subprocess.run(["which", "claude"], capture_output=True).returncode:
        sys.exit("The Claude Code CLI (`claude`) is not on PATH. Install it and log in first.")
    if OUT.exists():
        state["n"] = sum(1 for _ in OUT.open())
    humans = human_bases()
    print(f"model {MODEL}, {state['n']} samples already in {OUT}, target {MAX}, {WORKERS} workers, "
          f"{len(humans)} human texts to edit", flush=True)
    ts = [threading.Thread(target=worker, args=(i, humans), daemon=True) for i in range(WORKERS)]
    for t in ts:
        t.start()
    try:
        for t in ts:
            t.join()
    except KeyboardInterrupt:
        state["stop"] = True
        print("\nstopping (progress is saved; run again to resume)", flush=True)
    print(f"done: {state['n']} samples in {OUT}" + (" (weekly limit reached)" if state["weekly"] else ""), flush=True)
    print("Next: python3 pack.py  -> makes the file to send back.", flush=True)


if __name__ == "__main__":
    main()
