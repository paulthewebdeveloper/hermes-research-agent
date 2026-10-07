# A daily-metrics routine, end to end

A routine is a cron that creates an issue and assigns it to an agent. Every run is an issue, so it
has a brief, a budget and an audit trail. That is the reason to use a routine and not the agent's own
cron tool: the agent's cron bypasses the trail, and work you cannot read is work you cannot correct.

The order is **goal → project → routine → trigger**, because a routine needs a `projectId` and a
project is easier to read when it hangs off a goal. Four calls against your local Paperclip API. The
UI does the same thing; this is here so you can diff it.

## 1. The goal

```http
POST /api/companies/{companyId}/goals
```
```json
{ "title": "Grow the channel", "level": "company", "status": "active" }
```

## 2. The project

```json
POST /api/companies/{companyId}/projects
{ "name": "YouTube channel", "goalId": "<goalId>", "status": "in_progress", "icon": "target" }
```

## 3. The routine

The `description` **is the agent's brief for every run**. Write it as the whole instruction, because
nothing else is attached: the agent wakes with this text and an empty issue.

```json
POST /api/companies/{companyId}/routines
{
  "title": "Daily numbers + upload review",
  "projectId": "<projectId>",
  "goalId": "<goalId>",
  "assigneeAgentId": "<the researcher agent id>",
  "priority": "medium",
  "status": "active",
  "concurrencyPolicy": "coalesce_if_active",
  "catchUpPolicy": "skip_missed",
  "description": "Every day:\n1. **Numbers.** Pull channel statistics and the last 10 uploads' views, likes and comments through the API. Compare the last 3 uploads with the channel's average views per video.\n2. **Upload review.** Take any upload 48 hours old or more with no line in the playbook yet. Review it against the channel average using its dashboard analytics (impressions, CTR, average view duration, average percentage viewed, traffic sources, any A/B result), and name the likely reason (title, topic, thumbnail, length). The dashboard is read-only. Append one dated lesson line with the evidence, then commit the playbook only.\n3. **Outliers.** Run the trends script with the default queries and list any video from this week at 1x its channel's subscriber count or more.\n\nReport on this issue. Quote every figure from the tool output in this run. When a call fails, write FAIL with the error."
}
```

## 4. The schedule trigger

```json
POST /api/routines/{routineId}/triggers
{ "kind": "schedule", "cronExpression": "0 8 * * *", "timezone": "Europe/Malta", "enabled": true }
```

## The two policies worth understanding

- **`concurrencyPolicy: coalesce_if_active`** — if yesterday's run is still going, today's folds into
  it instead of starting a second one. Fire the routine twice by hand and you get one issue. That is
  the behaviour you want, and it is the default.
- **`catchUpPolicy: skip_missed`** — the machine was asleep at 08:00, so that day is skipped rather
  than replayed at 11:00 with stale framing. A metrics routine that catches up lies about when it
  looked.

## Two things to check after the first run

1. **Did it produce an issue, and did anyone read it?** A routine writing into a void is worse than
   no routine.
2. **Are the figures quoted from tool output in that run?** If the brief does not demand it, an
   agent will happily report last week's number from memory.
