# trex

Coding agents talking to each other inside [Rex](https://www.superlogical.com/rex).
Claude Code, Codex, OpenCode and Mistral Vibe each run as their normal TUI in a Rex pane;
`trex` finds those panes, starts new ones, and passes messages between them.

> **A proof of concept.** trex is an experiment that shows one way agents can
> work together using nothing but the terminal they already run in. It is not
> a finished tool: expect rough edges and no stable interface. Take the idea
> and build on it.

## Install

The script is Python, stdlib only. Link it onto your `PATH` and the skill
where the agents look for it (Codex and OpenCode: `~/.agents/skills`, Claude
Code: `~/.claude/skills`):

```sh
ln -s "$PWD/trex" ~/.local/bin/trex
ln -s "$PWD/skills/trex" ~/.agents/skills/trex
ln -s "$PWD/skills/trex" ~/.claude/skills/trex
```

`trex-watch.lua` stays beside the script. Settings are at the top of `trex`.

## Usage

```sh
trex ls                    # agents in this session, children under their starter
trex ls -a                 # agents in every session
trex spawn codex "review the diff in src/auth.rs"
trex spawn claude -n reviewer -m opus --split right "…"
trex spawn -n mistral --add-dir ../shared vibe "review the diff"
trex spawn codex -m gpt-5 -e high -w fix-retry "…"   # new worktree + branch
trex send codex "which test covers the retry path?"
git diff | trex send reviewer
trex reply "done: 3 files changed"   # from a spawned agent, to its starter
trex wait codex --for 300  # until its turn ends; prints its state
trex read codex -n 60      # tail of its pane
trex stop codex            # interrupt its turn; the pane stays
trex close codex
```

A target is a pane's name (`-n` at spawn, else the agent kind) or a block id.
A name reaches only the caller's session; a block id reaches any.

## How it works

Almost everything trex knows is what Rex already knows: which process runs
in which pane and the status each agent reports (`working`, `idle`, `done`,
`blocked`).

- **Messages.** `send` pastes the text into the recipient's prompt and
  presses Enter. The message is wrapped with who it is from and the exact
  command to answer with, so the recipient needs no skill to reply. An agent
  started with `spawn` gets its starter's block id in `TREX_PARENT` and
  answers with `trex reply`.
- **Inbox.** A root Claude Code (one the user started and types in) gets
  messages in `~/.local/state/trex/inbox/` instead of a paste over what the
  user is typing; it picks them up with `trex inbox --wait` run in the
  background.
- **Who started whom.** `spawn` records links in
  `~/.local/state/trex/links.json`. `ls` prints them as a tree, and
  `trex-watch.lua` (started by `spawn`) labels tabs:
  `✉1 ⟳1 ✓1 ⚠1 · title` on the starter's (unread, working, finished, needing
  you), `↳ name · title` on each child's.
- **Worktrees.** `-w NAME` runs the agent in worktree `../worktrees/<repo>/NAME`
  on branch `NAME`, made when missing and reused when present.

## Permission modes

| `--mode` | Claude Code | Codex | OpenCode | Vibe |
|---|---|---|---|---|
| `own` | nothing added | nothing added | nothing added | nothing added |
| `auto` (default) | `--permission-mode auto` | `--approve-for-me` | `--auto` | `--trust --smart-approve` |
| `full` | `--dangerously-skip-permissions` | `--dangerously-bypass-approvals-and-sandbox` | `--auto` | `--trust --auto-approve` |

Only a person at a shell can start an agent in `full`.

Vibe support targets 3.1.3 (including its `vibe-rs` process). `auto` uses its
risk classifier and can still ask about risky actions; `full` approves every
tool call. `--trust` trusts the selected working directory for this invocation.
`--add-dir` adds directories Vibe may access. Authentication stays with Vibe:
run `vibe --setup` or set `MISTRAL_API_KEY` in the launching environment.

`-m ALIAS` selects Vibe's interactive model through `VIBE_ACTIVE_MODEL`, without
editing its config. Vibe's `--model` and `--thinking` flags are headless-only;
`-e` is refused for Vibe. Set thinking in its model config or with `/model`.
The initial prompt is positional so the TUI stays open for `send` and `reply`.

Vibe reports native program statuses to Rex over OSC 7501: no screen scraping
or completion hook is needed. `wait` and the tab watcher consume these reports,
including errors and approval prompts. A finished turn means the chat is ready
for follow-up; it does not certify that the requested code change is correct.

## Things to know

- A `blocked` target is refused: Enter would answer its prompt.
- A paste lands in whatever is being typed, so don't type in a pane trex
  started while a message may arrive.
- Codex needs network access in its sandbox to reach Rex's socket; `spawn`
  turns it on. Its sandbox keeps `.git` read-only, so git writes need
  escalation.
- `read` shows the pane as drawn; for Codex and OpenCode that is one screen.

## Tests

Run the stdlib test suite with `python3 -m unittest discover -s tests -v`.
It covers launch arguments, permission modes, process recognition, status handling
and blocked-message protection for all four agents, using mocked Rex responses.

## License

GPL-3.0, see [LICENSE](LICENSE).
