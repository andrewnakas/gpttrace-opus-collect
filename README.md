# GPTTrace Opus 5.5 text collection

Thanks for helping! This repo uses **your own Claude subscription** (through Claude Code) to write
Claude Opus 5.5 text: new texts, the same texts run through "AI humanizer" rewrites, and human-written
texts rewritten by Opus. Andrew uses it to train [GPTTrace](https://gpttrace.com)'s AI-text detector to
catch text from the newest models, including text that people try to disguise.

## What it does and doesn't do

- **Usage:** it calls `claude -p` with Opus 5.5, so it uses your plan's usage. It pauses at the
  5-hour limit and carries on after the reset. It **stops at your weekly limit** and never resets
  anything. You choose how much with `MAX`.
- **Privacy:** every call runs in an empty temporary folder, with no tools, no MCP servers, none of
  your settings or CLAUDE.md files, no saved session, and a neutral system prompt. The only things
  saved are the writing prompts and Opus's replies. Nothing from your computer is read or recorded.
- **Output:** one file, `out/opus55-<your-name>-<date>.jsonl.gz`, which you send to Andrew.

## The easy way: let Claude Code run it

Open a terminal in this folder, start `claude`, and say:

> Read CLAUDE.md and run the collection.

## By hand

```sh
python3 collect.py              # runs until your weekly limit or 3000 samples (Ctrl-C to stop anytime)
python3 pack.py yourname        # makes out/opus55-yourname-<date>.jsonl.gz
```

Options: `MAX=1000 python3 collect.py` caps the number of samples. `WORKERS=1` is gentler on
rate limits. `WAIT_5H=0` stops at the first 5-hour limit instead of waiting.

To keep it running after you close the terminal, use
`nohup python3 collect.py > collect.log 2>&1 &`. Check on it with `tail collect.log`.

Requirements: Python 3.9+ and Claude Code logged in to a plan that includes Opus 5.5. Check with
`claude -p --model claude-opus-5-5 "say hi"`.

## Licence of the bundled human texts

`data/human_bases.jsonl.gz` contains 4,000 short excerpts from Wikipedia (CC BY-SA 4.0), PubMed Central
open-access articles (commercial-use subset, CC BY), arXiv abstracts (CC0 metadata) and Project
Gutenberg (public domain). They're used only as material for Opus to rewrite.
