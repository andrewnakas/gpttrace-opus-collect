# Instructions for Claude Code

The user wants to contribute Claude Opus 5.5 text to their friend Andrew's AI-text-detection training
data. Your job is to run `collect.py` for them, keep it running, and hand them the packed file at the
end. Everything you need is in this folder. Do not edit `collect.py` unless it fails, and never change
what it records.

## Steps

1. **Check the setup** (and tell the user what you find):
   - `python3 --version` shows 3.9 or newer.
   - `claude -p --model claude-opus-5-5 --output-format json "Reply with the word ok."` succeeds, and its
     `modelUsage` names an Opus 5.5 model. If Opus 5.5 is not available on their plan, stop and say so.
     Do not switch models.
2. **Ask the user two things**, with these defaults:
   - their first name, for the output file name;
   - how many samples to make (`MAX`, default 3000). It stops earlier at their weekly limit.
     Explain that it uses their plan's Opus usage, waits through 5-hour limits, and stops at the
     weekly limit. It never resets anything.
3. **Do a 3-sample smoke test:** `MAX=3 WORKERS=1 python3 collect.py`. Show the user one sample from
   `out/samples.jsonl` (it should be ordinary prose, not a refusal and not a chat preamble). Then delete
   `out/samples.jsonl` so the real run starts clean.
4. **Start the real run in the background:**
   `MAX=<their number> nohup python3 collect.py > collect.log 2>&1 &`
5. **Keep an eye on it.** Check `tail -n 5 collect.log` from time to time. It prints one line per
   sample, and a line when it waits for a 5-hour reset. If the process has stopped before the target
   and the log does not say "weekly limit" or "done", start it again with the same command: it resumes.
   If errors repeat (other than usage limits), read them and fix only the environment (PATH, login).
6. **When it says `done`** (target reached or weekly limit): run `python3 pack.py <first name>` and tell
   the user the path of `out/opus55-<name>-<date>.jsonl.gz`, how many samples it holds, and that they
   should send that one file to Andrew (email, Google Drive, Dropbox or AirDrop all work).

## Rules

- Use only `collect.py` and `pack.py`. Do not write extra prompts to Claude yourself or add other data.
- Never apply, request or work around a usage-limit reset. Stopping at the weekly limit is expected.
- Don't upload the file anywhere yourself. The user sends it.
