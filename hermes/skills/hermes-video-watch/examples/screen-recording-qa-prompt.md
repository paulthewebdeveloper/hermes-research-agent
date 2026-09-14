# Example: Screen-Recording QA Prompt

Use when a user shares a product demo, bug report, usability recording, or workflow screen capture.

```text
Analyze this screen recording as a QA artifact.

Video file: <local path or URL>

Focus on:
- visible UI state changes
- errors, warnings, loading states, or broken layout
- mismatches between narration and what appears on screen
- timestamps where the issue can be reproduced
- screenshots that would help an engineer understand the bug

Deliver:
- timeline of observed actions and states
- likely issue summary
- reproduction clues
- selected frame paths/timestamps for evidence
- confidence and limitations
```
