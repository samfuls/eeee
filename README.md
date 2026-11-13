# Viral remake studio

Scene-by-scene remakes: break a viral video into scenes, regenerate each scene in your niche with
Higgsfield (through Claude), then cut everything to the original's exact timing for CapCut.

Needs Python 3 with `numpy` + `Pillow`, and `ffmpeg`.

```bash
python3 remake.py breakdown kidsbike ~/Downloads/viral.mp4 --title "Kids Bike"
open projects/kidsbike/board.html          # the scene board
python3 remake.py set kidsbike 01 --start-frame ours.jpg --raw-clip kling.mp4
python3 remake.py colormatch --project kidsbike --scene 01
python3 remake.py beatmatch kidsbike 01 --his-beat 0.45 --our-beat 1.4
python3 remake.py assemble kidsbike         # -> projects/kidsbike/capcut/ + final_preview.mp4
```

Or just tell Claude: "remake this video for my niche: <file>". `CLAUDE.md` holds the workflow.
