# Prompts

What you type to the main Hermes agent. Plain language is enough; the worker
and the rules in AGENTS.md do the rest.

**Farm a video and make it chattable**
> Create a NotebookLM notebook about this video: <youtube-url>. Use Argus for it.

**Farm several at once**
> Use Argus to farm these three videos into raw/, then put all three in one
> NotebookLM notebook called "<topic>": <url-1> <url-2> <url-3>

**Ask the wiki**
> What did we decide about <thing>? Read the log tail first.

**File something new**
> <client> replied and accepted the price. Update their page and log it.

**Any video: a reel, a TikTok, a file on your disk**
> /path/to/my-old-reel.mp4 instagram.com/reels/DdR7QJBpxH4
> tiktok.com/@hardknockspod/video/7672869091467644173
> process all of these videos for me and launch argus to create notebook lms about each
