# Watching the agent drive

Every Anchor session comes with a live view URL. `first_user.py` prints it as
soon as the browser is up:

```
[first-user] watch live: https://live.anchorbrowser.io/...
```

That link is safe to share. It shows the browser, not your key. (The CDP URL
the scripts use to drive the browser *does* contain your key, which is why
`shared/anchor_session.py` never prints it.)

## Put it next to the Sprite

A Sprite has its own URL. The pattern that works well:

1. Start the agent in the Sprite.
2. Post both links in your team channel: the Sprite (what the agent is doing in
   its terminal) and the live view (what it's doing in the browser).
3. Watch it sign up, fumble onboarding, and file the bug.

The live view stays up for as long as the session does. The scripts set a
short `idle_timeout`, so once the agent finishes the session closes and the
link goes dead. That's on purpose.

## Recording a GIF for the post

Sessions are recorded by default (`recording: {"active": true}` in
`shared/anchor_session.py`). Grab the recording from Anchor's dashboard after
the run, or screen-record the live view while it plays.
