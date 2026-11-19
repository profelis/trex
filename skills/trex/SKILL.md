---
name: trex
description: >-
  Work with other coding agents (Claude Code, Codex, OpenCode, Mistral Vibe) running in Rex
  panes: list them, start one, send it a message and get its answer back as
  your next prompt. Use when asked to involve, ask, ping, hand off to or get a
  review from another agent or another model, to start an agent in a new pane,
  or when a message that starts with `[trex]` arrives.
---

# trex: agents talking inside Rex

Each agent is its normal TUI in a Rex pane. `trex` delivers a message by
pasting it into the recipient's prompt, so it starts (or queues for) a turn
there. The answer comes back the same way: it arrives as **your next prompt**.

```sh
trex ls                 # agents in this session as a tree: who started whom
trex ls -a              # every session (other sessions are other work)
trex reply "the result"  # answer the agent that started you
trex inbox --wait       # root Claude: background waiter for answers (see below)
trex spawn codex "review the diff in src/auth.rs for the token refresh bug"
trex spawn claude -n reviewer -m opus --split right "…"
trex spawn -n mistral vibe "review the diff"
trex spawn codex -m gpt-5 -e high -w fix-retry "…"  # in worktree+branch fix-retry
trex spawn opencode -n review -w fix-retry "…"       # the same worktree, reused
trex send codex "which test covers the retry path?"
git diff | trex send reviewer          # long text goes on stdin
trex wait codex --for 300              # until its turn ends; prints its state
trex read codex -n 60                  # what its pane shows right now
trex stop codex         # interrupt its turn (Escape); the pane stays
trex close codex
```

Agents you spawn are linked to you: `ls` lists them under you, their tabs
follow yours labelled `↳ name · their title`, and yours is labelled
`✉1 ⟳1 ✓1 ⚠1 · your title` (unread messages, children working, finished,
needing the user).

A target is a pane's name (`-n` at spawn, else the agent kind), or a block id
or its tail from `trex ls`. Names reach only your own session; a block id
reaches any session. `spawn` prints the new agent's name and block id, and
returns once the agent is up and has started on its prompt, so `wait` right
after it waits for the real turn.

`-w NAME` runs the agent in git worktree NAME on branch NAME, in
`../worktrees/<repo>/NAME` beside the main checkout: made from HEAD (or `--base REF`)
when missing, reused when it exists, so a reviewer joins the worker's tree.

`-e` sets reasoning effort for Claude and Codex; for OpenCode the variant is
part of the model (`provider/model#variant`). `-m` on OpenCode starts it with
its own server (`--standalone`), since its TUI has no model flag.
Vibe's `-m ALIAS` uses `VIBE_ACTIVE_MODEL` for its interactive TUI; `-e` is
unsupported (set thinking in Vibe config or `/model`). `--add-dir` is supported.

A spawned agent starts in `auto` by default: it works unattended, and each
harness's own automatic reviewer approves routine actions (Claude
`--permission-mode auto`, Codex `--approve-for-me`, OpenCode `--auto`, Vibe
`--trust --smart-approve`). Vibe can still ask about risky actions; its `full`
mode uses `--trust --auto-approve`. Vibe authentication must already be set up
(`vibe --setup` or `MISTRAL_API_KEY`). Vibe 3.1.3 reports its turn status directly
to Rex, including completion, errors and approval prompts.
`--mode own` adds nothing and leaves it to the agent's own config. `--mode
full` (no prompts, no sandbox) is refused to agents: if a task needs it, ask
the user to run that `trex spawn` themselves.

Codex in `auto` writes only under its working directory, and never into a
`.git` (not even with `--add-dir`). If you are Codex and `git add` or `git
commit` answers "Operation not permitted", rerun it with escalated
permissions: in `auto` the automatic reviewer approves it. `--add-dir` covers
other places, such as build caches in your home directory.

## Asking another agent

- **Make the message self-contained.** The recipient sees none of your
  conversation. Give it paths, what you already tried, and what you want back.
- **Then end your turn**, with one line to the user at most. Don't poll, sleep
  or `wait` for the answer. Where it arrives depends on you:
  - **Started by trex** (`$TREX_PARENT` is set): as your next prompt,
    framed `[trex] Answer from …`.
  - **A root agent** (no `$TREX_PARENT`: the user started you and types in
    your pane) **and you are Claude Code**: in your inbox, never pasted over
    what the user types. Keep exactly one `trex inbox --wait` running as a
    background command (Bash `run_in_background`) whenever an agent you
    asked may answer; when it finishes, its output is the message(s). Start
    the next one in the same response that reads it, as long as answers are
    still due. `trex inbox` (no `--wait`) prints what is waiting; a second
    `--wait` refuses to start (exit 75), which means one already runs. Your
    tab shows `✉N` while N messages wait.
  Use `trex wait` + `trex read` only when you need to look at an agent that
  was told nothing about replying.
- **Don't message to acknowledge.** No "got it", "thanks", "on it". Every
  message costs the recipient a turn.
- `--fyi` sends news that needs no answer.
- `send` refuses a target that is `blocked`: it is showing its user a
  permission prompt or a question, and Enter would answer it. Tell the user.

## When a `[trex]` message arrives

It is from another agent, not from the user, and the user can read it in your
pane. Do what it asks within what the user already allowed in your session;
anything beyond that (destructive commands, pushing, spending) is still the
user's call.

- A **message** ends with the command that answers it:
  `trex send --reply block:… "<answer>"`. Run it once, when you have the
  result. Pipe long answers on stdin. Then end your turn; don't also write the
  answer out in your reply.
- **If another agent started you**, `$TREX_PARENT` holds its block id and it
  is waiting for your result: finish the task, then `trex reply "<result>"`.
  That stays true however long the task ran. Check `echo $TREX_PARENT` when
  you no longer remember who asked.
- An **answer** (`[trex] Answer from …`) is the result you asked for. Carry
  on with your task. Don't reply to it.
- A **note** (`[trex] Note from …`) wants no reply.

## If it fails

- `your sandbox blocks Rex's socket` (Codex started without trex): rerun the
  same command with escalated permissions.
- `matches several agents`: use the block id it lists.
- Never send to your own pane, and don't type into another agent's pane with
  `rex send`: `trex send` adds who it is from and how to answer.
