# Viral remake studio

This repo copies a proven viral short scene by scene and swaps in our niche: same cuts, camera,
timing and text, new people, product and setting. Generation runs on the Higgsfield MCP. Every free,
mechanical step goes through `remake.py`. Follow the `niche-swap-remake` skill for the creative
rules (prompts, product rules, credit costs).

## The loop
1. **Breakdown (free).** `python3 remake.py breakdown <name> <his_video>`.
   - Read every `his/sNN_sheet.jpg`. Check that each detected cut is real; a whip pan can look like a cut.
     Fix it with `--cuts 2.0,3.5,... --force` if needed.
   - Fill in each scene: `remake.py set <name> NN --desc "..." --text "exact on-screen words" --camera "..."`.
   - Set the project: `remake.py set <name> --brand ... --changes "what we swap"`.
   - Show the user `projects/<name>/board.html`.
2. **Per scene, in order. Never skip ahead.**
   - Pitch the swap and the method, and **quote the credit cost**. Wait for an explicit "go".
   - START frame: Higgsfield `generate_image` (nano_banana_pro, 9:16). Image 1 is HIS `his/sNN_start.jpg`.
     Upload it with `media_upload` → PUT → `media_confirm`.
     Save the result: `remake.py set <name> NN --start-frame <file> --status "frames ready"`. Wait for the user's OK.
   - END frame: same method, with image 1 = HIS end frame and image 2 = OUR approved start. Wait for an OK.
   - `remake.py colormatch --project <name> --scene NN` (free; fixes the warm AI look).
   - Clip: Higgsfield `generate_video` (kling3_0 pro, start_image + end_image, sound off).
     Quote the cost and wait for a go. Save it with `--raw-clip <file> --status "clip ready"`.
   - Beat match: `remake.py beatmatch <name> NN --his-beat X --our-beat Y`, or `--in/--speed`.
     Our clip now has his exact length.
   - Log every attempt: `--attempt "v2 ❌ mask duplicated onto both"`. Use `--status locked` once the user says it's perfect.
3. **Assemble.** `remake.py assemble <name>` → `capcut/` (numbered clips, his audio, CUES.txt) plus `final_preview.mp4`.
   In CapCut: import the folder, lay out 01..NN, put the audio under it, and add the text from CUES.txt.

## Hard rules
- No paid generation without a clear go. A question is not a go.
- Check every render zoomed in before showing it, and say what missed.
- Never change the shot count, order, lengths or camera.
- Never put his original footage in the final. Missing scenes become grey slates.
