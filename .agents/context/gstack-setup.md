# gstack setup (pinned — same version on every machine)
The sprint below needs [gstack](https://github.com/garrytan/gstack) **1.91.2.0** (commit `01593aa`)
installed with the `gstack-` prefix. If a session starts with a "gstack is NOT installed" or
"pinned to" warning (scripts/rnd/check-gstack.sh), tell the user; never upgrade it yourself.
```bash
git clone https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
cd ~/.claude/skills/gstack && git checkout 01593aa && \
  ./setup --host claude --prefix --no-team --no-plan-tune-hooks --no-timeline-stop-hook
```
Upgrading is a deliberate team decision: upgrade on one machine, run `make verify` and one
sprint, then bump the version and commit here and in scripts/rnd/check-gstack.sh together.

