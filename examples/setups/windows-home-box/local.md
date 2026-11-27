# House rules on this box

This file is the operator layer of the ohflow references. git ignores it at
`references/local.md`. The references of ohflow core hold the product, and this file adds the rules
of this box.

## Campaign escalation reaches the operator through the team board

Set `operator.on_escalate` in `ohflow.settings.local.json` to a command that posts the
escalation file to the team board, with `{file}` where the escalation file's path goes. Every
campaign then reaches the board, including the ones `ohflow construct` writes, which name no
`on_escalate` of their own. A campaign that sets one overrides the setting. The post's subject
and first body line open with `CRUCIAL INFORMATION FOR ALEX:`, which is the
`operator.escalation_marker` setting. Every agent reads the board, and the marker tells them
the post is for a person.

## Sweep the memory store before you report delivery

When `campaign watch` exits `0`, the campaign log's last event is `campaign_delivered`, with the
integration branch and its commit. Before you report the delivery, grep the memory store for the
target repo, the feature and that commit:

```bash
grep -rln -e '<target repo name>' -e '<feature name>' -e '<integration sha, first 7>' <memory store folder> --include=*.md
```

Where a hit restates the repo's state, such as commits ahead or "not pushed", replace the line
with a pointer to the repo. Done when a second run of the grep shows no hit that states a
pre-delivery fact about the delivered work.

## Commits carry no AI attribution

The `commit_checks.no_ai_attribution` setting is on, so every committing step gets the
`no_ai_attribution` gate. A brief tells the agent to write no `Co-Authored-By` trailer and no
"Generated with" line.
