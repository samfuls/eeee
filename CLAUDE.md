# Viral remake studio

This repo copies a proven viral short scene by scene and swaps in our niche: same cuts, camera,
timing and beats, with new people, product and setting. Generation runs on the Higgsfield MCP. Every
free, mechanical step goes through `remake.py`. Follow the `niche-swap-remake` skill for the creative
rules (prompts, product rules), but **the user's preferences below override it**.

## User preferences (from the first remake, "pinktent")
- **Talk style:** short and direct. Before every paid step, show what's being made, the prompt, and the exact cost.
- **Ask before each part.** Start frame, end frame and clip are separate gos. A redo also needs a go.
  "go", "fix", "redo", "touch up" and obvious typos like "Gp" count as a go for the thing just pitched.
  Locking a scene and starting the next scene's start frame can share one go.
- **Confirm every detail before generating anything.** First pitch the plan as a scene table, plus a numbered list
  of open questions: where people appear, logo swap, brand name, lighting, outfits, caption, audio, and photo permission.
- **Scene board in the side panel.** Publish `projects/<name>/board.html` as an Artifact on day one,
  then republish after every new frame or clip so the user can watch progress. It's a static page,
  so pass every media file it references in `files` with `root` = the project folder.
  Keep each file under 15 MB; for the final, publish a 720p `final_web.mp4` at the `final_preview.mp4` path.
- **Frames:** `nano_banana_pro`, **2K**, 9:16, `use_unlim: false`, 2 credits each.
  Unlimited generations don't work from Claude Code (Higgsfield refuses), so credits are the plan.
  The job status says "nano_banana_2"; that's just the internal name and the price is the Pro price.
- **Clips:** regular **Wan 3.0** (`wan3_0`) at **720p**, never Prime (user's standing order).
  1.75 credits/s (2s = 3.5, 3s = 5.25, 4s = 7). Always `resolution: "720p"`, `generate_audio: false`, `enable_thinking: true`.
- **No text in any generation.** The caption goes in CapCut as an editable subtitle: set it with
  `remake.py set <name> --caption "..."`, and `assemble` writes `capcut/captions.srt`.
- **Keep the original's sound** (`his/audio.m4a`). Mention once that a track with music can get muted.
- **Lighting:** match what the user asks for (pinktent was deep dusk everywhere). Skip `colormatch` when the user's
  look is meant to differ from his (e.g. night vs his daytime), since it would undo it.
- **Final deliverables**, all sent with `SendUserFile` (`display: attach` for the files):
  - a side-by-side (his | ours) with sound;
  - `final_preview.mp4` at **720×1280** (clips are 720p now, so upscaling adds nothing; keep his resolution
    if his is 720p, otherwise set the project to `width 720, height 1280` and re-run every beatmatch before assembling);
  - `<Name>_CapCut.zip` of the `capcut/` folder;
  - the audio on its own as `.m4a` and `.mp3`.
  You can't operate CapCut from the cloud, so say so and give the 4 import steps.

## The loop
1. **Breakdown (free).** `python3 remake.py breakdown <name> <his_video> --title "..." --model "Wan 3.0"`.
   - Scene detection at 0.3 misses fast cuts. Also run `select='gt(scene,0.15)'`, check those times on a
     5-fps contact sheet, then pin the real cuts with `--cuts ... --min-len 0.3 --force`. Pinktent had 8 scenes, not 5.
   - After `--force`, the project fields are reset. Back up `project.json` first and restore the desc/plan/caption fields.
   - Fill in each scene: `set <name> NN --desc "his beat" --camera "..." --plan "our version"`.
   - Copy the user's reference photos into `projects/<name>/refs/` (they show on the board).
   - Send a numbered overview sheet of his start frames (ffmpeg `xstack` + `drawtext`).
2. **Upload to Higgsfield (free):** `media_upload` → `curl -X PUT -H "Content-Type: image/jpeg" -H "If-None-Match: *"`
   → `media_confirm`. Batch his frames for all scenes while a clip renders. Retry a 520 PUT, then confirm.
   Log every media ID in `project.json` under `higgsfield`.
3. **Per scene, in order.** Start frame → check → end frame → check → clip → check → beatmatch → side-by-side → lock.
   - START: image 1 = his start frame, then the person ref, then the setting ref / our earlier approved frame for the look.
   - END: image 1 = his end frame, image 2 = our approved start.
   - For a touch-up, pass our frame's **job ID** as image 1: "Keep everything pixel-identical... Change ONLY: 1) 2)".
   - Very short scenes where his start ≈ his end (e.g. a 0.5s sofa close-up): skip the end frame and run
     Wan with `start_image` only. That saves 2 credits.
   - Clip length: his length rounded up plus headroom, min 2. Then `beatmatch` with `--his-beat/--our-beat`
     or `--in/--speed` (keep 1.0–1.7x). Find the key beat on 10–15 fps contact sheets of both clips.
   - After every clip, send a side-by-side mp4 (his | ours); add a 3–4x slow-mo version when a glitch needs judging.

## Lessons (what went wrong and the fix)
- **Never pass a rejected attempt as a reference**: the model copies its framing. Use his frame + refs only.
- **Background bleed:** the model copies his background through windows and doors (a lake, pines).
  Name the setting explicitly for windows: "through the windows show the backyard at dusk... no lake".
- **Leftovers:** always zoom in for his clothes and props left in the frame (camo pants and boots under a table, a camo
  floor strip in a corner). Free fix when it's at an edge: punch in ~8–10% from the top center and scale back up.
- **"Pop-up" makes the model draw a small dome tent.** Describe the shape instead: "a big flat sheet of folded fabric lying
  on the grass like a tarp, only one corner lifted".
- **"Half-inflated" barely works** on an existing frame; get the inflating effect from a fuller end frame instead.
- **Dimming via the model is weak.** Darken locally for free (gamma ~1.6 × 0.82 on the midtones, protect the brightest
  pixels so lanterns and string lights still glow), then upload that file as the start frame.
- **Wan dissolves** when there's too much change for the clip length (scene 2 ghosting). In the prompt: "solid and fully
  opaque at every moment... no fades, no dissolves, no morphing, no double exposure; every frame is a real physical moment",
  and spell out the motion piece by piece. If it still snaps, a longer clip (4s) gives it room.
- **Lights-on scenes:** "the lights switch on, they do not fade the scene" → got a clean snap.
- Wan 3.0 renders take 4–10 min; poll `jobs_wait` and give the user a one-line status every few polls.
- **Watermarks on reference photos:** crop them off before uploading (e.g. the bottom 4.5%) so the model can't copy them.
- **Too-wide framing from the model:** crop in for free on the 2K frame (~70% crop, scale back up) and upload that file.
  2K has plenty of detail left for a 720p clip.
- **Product boxes:** the model copies his box's feature strip (icons + gibberish small print). Ask for "only the scene and
  the wordmark, no icons, no small print" up front; touching it up afterward works too (2 credits).
- Lighting drifts between frames (sky too bright). Pass the approved deep-dusk frame as the look reference each time.

## Hook-only jobs (from "pinkhook")
- The user may want only the hook. Trim the original to the hook first (`ffmpeg -t <hook end>`), then run breakdown on that
  file. Split a single continuous shot at its whip pan into 2 parts: the blur hides the join, and part 2's start
  frame = part 1's approved end frame (free).
- Silent hook: set `project.json` `audio` to null, so `assemble` makes a video with no sound track. Drop the SRT and audio
  files from the zip, and include the joined full hook in it.
- The budget the user names (e.g. 30–40 credits) is a hard ceiling. Pinkhook came in at 18.5.

## Environment
- Cloud environment "eeee" allows `upload.higgsfield.ai`, `d2ol7oe51mr4n9.cloudfront.net`, `d8j0ntlcm91z4.cloudfront.net`
  (results CDN). If a result URL is on a new host, add it with `update_environment`.

## Hard rules
- No paid generation without a clear go. A question is not a go.
- Check every render zoomed in before showing it, and say what missed. Never hide a miss.
- Never change the shot count, order, lengths or camera.
- Never put his original footage in the final. Missing scenes become grey slates.
- Never reproduce real brands or logos; swap them for original designs (pinktent: a pink bow).
- People in the user's photos must be people the user has permission to use (pinktent: family, confirmed).
