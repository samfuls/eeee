#!/usr/bin/env python3
"""remake.py - local toolkit for scene-by-scene viral remakes.

Paid generation (frames, clips) happens through the Higgsfield MCP inside Claude.
This script does everything free and mechanical around it:

  breakdown  split the original into scenes: cut times, start/end frames, clips, contact sheets, audio
  board      build the scene board (board.html): theirs vs ours, scene by scene
  set        record a scene's description, on-screen text, status or our files
  colormatch Reinhard LAB color transfer (our frame -> his frame look)
  beatmatch  cut our raw clip to his exact scene length (in-point + even speed)
  assemble   numbered clips + his audio + cue sheet for CapCut, plus a full preview mp4

Project layout: projects/<name>/{original.*, project.json, his/, ours/, capcut/, board.html}
"""
import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "projects"


# ---------- helpers ----------
def run(cmd, capture=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"command failed: {' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r.stdout + r.stderr if capture else None


def probe(path):
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)], True)
    info = json.loads(out[out.index("{"):])
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    num, den = map(int, v["r_frame_rate"].split("/"))
    w, h = int(v["width"]), int(v["height"])
    rot = int((v.get("tags") or {}).get("rotate", 0) or 0)
    for sd in v.get("side_data_list", []):
        rot = int(sd.get("rotation", rot) or rot)
    if abs(rot) % 180 == 90:
        w, h = h, w
    return {
        # the video stream's length, not the container's: audio often runs a bit longer
        "duration": min(float(v.get("duration") or info["format"]["duration"]), float(info["format"]["duration"])),
        "fps": round(num / den, 3) if den else 30.0,
        "width": w, "height": h,
        "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
    }


def proj_dir(name):
    d = ROOT / name
    if not (d / "project.json").exists():
        sys.exit(f"no project '{name}' (expected {d/'project.json'}); run breakdown first")
    return d


def load(name):
    d = proj_dir(name)
    return d, json.loads((d / "project.json").read_text())


def save(d, p):
    (d / "project.json").write_text(json.dumps(p, indent=2))


def tc(t):
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


def scene(p, sid):
    for s in p["scenes"]:
        if s["id"] == sid:
            return s
    sys.exit(f"no scene {sid}; have {[s['id'] for s in p['scenes']]}")


# ---------- breakdown ----------
def detect_cuts(src, threshold):
    out = run(["ffmpeg", "-hide_banner", "-i", str(src), "-filter:v",
               f"select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"], True)
    return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", out)]


def cmd_breakdown(a):
    src = Path(a.video).expanduser().resolve()
    if not src.exists():
        sys.exit(f"not found: {src}")
    d = ROOT / a.name
    if (d / "project.json").exists() and not a.force:
        sys.exit(f"project exists: {d} (use --force to redo the breakdown)")
    for sub in ("his", "ours", "capcut"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    orig = d / f"original{src.suffix.lower()}"
    if src != orig:
        shutil.copy2(src, orig)
    info = probe(orig)
    dur, fps = info["duration"], info["fps"]

    if a.cuts:
        cuts = sorted(float(x) for x in a.cuts.split(","))
    else:
        cuts = detect_cuts(orig, a.threshold)
    # drop cuts too close to each other or to the ends
    bounds = [0.0]
    for c in cuts:
        if c - bounds[-1] >= a.min_len and dur - c >= a.min_len:
            bounds.append(c)
    bounds.append(dur)

    frame = 1.0 / fps
    scenes = []
    for i, (s0, s1) in enumerate(zip(bounds, bounds[1:]), 1):
        sid = f"{i:02d}"
        hs = d / "his"
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s0:.3f}", "-i", str(orig), "-frames:v", "1", "-q:v", "2", str(hs / f"s{sid}_start.jpg")])
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(s0, s1 - 2 * frame):.3f}", "-i", str(orig), "-frames:v", "1", "-q:v", "2", str(hs / f"s{sid}_end.jpg")])
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s0:.3f}", "-i", str(orig), "-t", f"{s1 - s0:.3f}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-c:a", "aac", "-movflags", "+faststart", str(hs / f"s{sid}.mp4")])
        for k in ("start", "end"):
            if not (hs / f"s{sid}_{k}.jpg").exists():
                sys.exit(f"could not grab scene {sid} {k} frame")
        # contact sheet: one frame every 0.25s, 4 per row
        n = max(1, int((s1 - s0) / 0.25))
        rows = (n + 3) // 4
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s0:.3f}", "-i", str(orig), "-t", f"{s1 - s0:.3f}",
             "-vf", f"fps=4,scale=270:-2,tile=4x{rows}", "-frames:v", "1", str(hs / f"s{sid}_sheet.jpg")])
        scenes.append({
            "id": sid, "start": round(s0, 3), "end": round(s1, 3), "dur": round(s1 - s0, 3),
            "desc": "", "text": "", "camera": "", "status": "planned",
            "his": {k: f"his/s{sid}{suf}" for k, suf in
                    (("start_frame", "_start.jpg"), ("end_frame", "_end.jpg"), ("clip", ".mp4"), ("sheet", "_sheet.jpg"))},
            "ours": {"start_frame": None, "end_frame": None, "raw_clip": None, "clip": None,
                     "in_point": None, "speed": None, "attempts": []},
        })

    if info["has_audio"]:
        run(["ffmpeg", "-v", "error", "-y", "-i", str(orig), "-vn", "-c:a", "aac", "-b:a", "192k", str(d / "his" / "audio.m4a")])

    p = {
        "name": a.name, "title": a.title or a.name, "source": orig.name,
        "duration": round(dur, 3), "fps": fps, "width": info["width"], "height": info["height"],
        "audio": "his/audio.m4a" if info["has_audio"] else None,
        "mode": "RECREATE", "model": a.model, "brand": "", "changes": "",
        "scenes": scenes,
    }
    save(d, p)
    build_board(d, p)
    print(f"{len(scenes)} scenes -> {d}")
    for s in scenes:
        print(f"  scene {s['id']}  {tc(s['start'])} -> {tc(s['end'])}  ({s['dur']:.2f}s)")
    print(f"board: {d/'board.html'}")


# ---------- set ----------
def cmd_set(a):
    d, p = load(a.name)
    if a.scene is None:  # project-level fields
        for k in ("title", "brand", "changes", "model", "mode", "caption"):
            v = getattr(a, k, None)
            if v is not None:
                p[k] = v
    else:
        s = scene(p, a.scene.zfill(2))
        for k in ("desc", "text", "camera", "status", "plan"):
            v = getattr(a, k, None)
            if v is not None:
                s[k] = v
        for k in ("start_frame", "end_frame", "raw_clip"):
            v = getattr(a, k, None)
            if v is not None:
                s["ours"][k] = import_file(d, v, f"s{s['id']}_{k}")
        if a.attempt:
            s["ours"]["attempts"].append(a.attempt)
    save(d, p)
    build_board(d, p)
    print("saved; board rebuilt")


def import_file(d, path, stem):
    src = Path(path).expanduser().resolve()
    if not src.exists():
        sys.exit(f"not found: {src}")
    dst = d / "ours" / f"{stem}{src.suffix.lower()}"
    if src != dst:
        shutil.copy2(src, dst)
    return str(dst.relative_to(d))


# ---------- colormatch ----------
def _rgb2lab(rgb):
    import numpy as np
    c = rgb / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _lab2rgb(lab):
    import numpy as np
    fy = (lab[..., 0] + 16) / 116
    fx, fz = fy + lab[..., 1] / 500, fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    M = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])
    c = np.clip(xyz @ M.T, 0, 1)
    c = np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)
    return (c * 255).round().clip(0, 255).astype("uint8")


def _stats(lab, skip):
    import numpy as np
    h = lab.shape[0]
    rows = np.ones(h, bool)
    if skip:
        rows[int(skip[0] * h):int(skip[1] * h)] = False
    px = lab[rows].reshape(-1, 3)
    return px.mean(0), px.std(0) + 1e-6


def colormatch(src, ref, out, width=1536, skip=(0.12, 0.37)):
    import numpy as np
    from PIL import Image
    s_img, r_img = Image.open(src).convert("RGB"), Image.open(ref).convert("RGB")
    small = lambda im: np.asarray(im.resize((300, max(1, round(im.height * 300 / im.width)))), float)
    sm, ss = _stats(_rgb2lab(small(s_img)), skip)
    rm, rs = _stats(_rgb2lab(small(r_img)), skip)
    big = s_img.resize((width, round(s_img.height * width / s_img.width)), Image.LANCZOS)
    lab = (_rgb2lab(np.asarray(big, float)) - sm) * (rs / ss) + rm
    Image.fromarray(_lab2rgb(lab)).save(out, quality=95)


def cmd_colormatch(a):
    if a.name:
        d, p = load(a.name)
        s = scene(p, a.scene.zfill(2))
        done = []
        for k in ("start_frame", "end_frame"):
            ours = s["ours"][k]
            if not ours:
                continue
            out = d / "ours" / f"s{s['id']}_{k}_cm.jpg"
            colormatch(d / ours, d / s["his"][k], out, a.width, None if a.no_skip else (0.12, 0.37))
            s["ours"][k] = str(out.relative_to(d))
            done.append(out.name)
        if not done:
            sys.exit("no ours start/end frame on that scene yet (use `set --start-frame/--end-frame`)")
        save(d, p)
        build_board(d, p)
        print("color matched:", ", ".join(done))
    else:
        if not (a.src and a.ref and a.out):
            sys.exit("give --project/--scene, or --src --ref --out")
        colormatch(a.src, a.ref, a.out, a.width, None if a.no_skip else (0.12, 0.37))
        print("wrote", a.out)


# ---------- beatmatch ----------
def cmd_beatmatch(a):
    d, p = load(a.name)
    s = scene(p, a.scene.zfill(2))
    raw = s["ours"]["raw_clip"]
    if not raw:
        sys.exit("no raw clip on that scene (use `set --raw-clip`)")
    raw_info = probe(d / raw)
    speed, inp = a.speed, a.in_point
    if a.his_beat is not None and a.our_beat is not None and speed is None:
        # put our beat on his beat: our_beat - in = his_beat * speed, and
        # in + dur*speed <= raw length. pick the smallest speed that fits, at least 1.0
        speed = 1.0
        while True:
            inp = a.our_beat - a.his_beat * speed
            if inp >= 0 and inp + s["dur"] * speed <= raw_info["duration"] + 1e-3:
                break
            speed = round(speed + 0.05, 2)
            if speed > 3.0:
                sys.exit("can't land the beat within 3x speed; pick --in/--speed by hand")
    speed = speed or 1.0
    inp = inp or 0.0
    span = s["dur"] * speed
    # keep one frame of margin so the cut never runs off the end of the raw clip
    limit = raw_info["duration"] - 1.0 / raw_info["fps"]
    if inp + span > limit:
        if span <= limit:
            new_in = max(0.0, limit - span)
            print(f"note: in-point moved {inp:.2f}s -> {new_in:.2f}s so the cut fits the raw clip", file=sys.stderr)
            inp = new_in
        else:
            print(f"warning: needs {span:.2f}s of source, raw clip is {raw_info['duration']:.2f}s - raise --speed", file=sys.stderr)
    fps = p["fps"]
    frames = round(s["dur"] * fps)
    out = d / "ours" / f"s{s['id']}_cut.mp4"
    W, H = p["width"], p["height"]
    vf = (f"setpts=(PTS-STARTPTS)/{speed},fps={fps},"
          f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1")
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{inp:.3f}", "-i", str(d / raw), "-vf", vf,
         "-frames:v", str(frames), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out)])
    frz = run(["ffmpeg", "-hide_banner", "-i", str(out), "-vf", "freezedetect=n=0.003:d=0.3", "-f", "null", "-"], True)
    s["ours"].update(clip=str(out.relative_to(d)), in_point=round(inp, 3), speed=speed)
    if s["status"] in ("planned", "frames ready", "clip ready"):
        s["status"] = "cut"
    save(d, p)
    build_board(d, p)
    print(f"scene {s['id']}: in={inp:.2f}s speed={speed}x -> {frames} frames ({s['dur']:.2f}s) {out.name}")
    if "freeze_start" in frz:
        print("warning: freezedetect found a frozen stretch - check the tail", file=sys.stderr)


# ---------- assemble ----------
def cmd_assemble(a):
    d, p = load(a.name)
    cap = d / "capcut"
    if cap.exists():
        shutil.rmtree(cap)
    cap.mkdir()
    W, H, fps = p["width"], p["height"], p["fps"]
    parts, missing, cues = [], [], []
    for s in p["scenes"]:
        target = cap / f"{s['id']}_scene.mp4"
        frames = round(s["dur"] * fps)
        if s["ours"]["clip"]:
            shutil.copy2(d / s["ours"]["clip"], target)
        else:
            missing.append(s["id"])
            # slate so the timeline keeps his exact timing; never his footage
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x222222:s={W}x{H}:r={fps}",
                 "-frames:v", str(frames), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target)])
        parts.append(target)
        cues.append(f"{s['id']}  {tc(s['start'])} -> {tc(s['end'])}  ({s['dur']:.2f}s)"
                    + (f"\n    text: {s['text']}" if s["text"] else "")
                    + (f"\n    beat: {s['desc']}" if s["desc"] else ""))
    if p["audio"]:
        shutil.copy2(d / p["audio"], cap / "audio_his.m4a")
    if p.get("caption"):
        srt = lambda t: f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(round(t%1*1000)):03d}"
        (cap / "captions.srt").write_text(f"1\n{srt(0)} --> {srt(p['duration'])}\n{p['caption']}\n")
    (cap / "CUES.txt").write_text(
        f"{p['title']}  -  {len(p['scenes'])} scenes, {p['duration']:.2f}s, {W}x{H} @ {fps}fps\n\n"
        "CapCut: new project -> import this folder -> drag 01..NN onto the timeline in order\n"
        "(each file is already his exact scene length, so cuts land on his beats) ->\n"
        "drop audio_his.m4a under it -> Text > Local captions > Import captions.srt\n"
        "(editable caption; restyle it to match his).\n\n"
        + (f"CAPTION (whole video): {p['caption']}\n\n" if p.get("caption") else "")
        + "\n".join(cues) + "\n")
    lst = cap / ".concat.txt"
    lst.write_text("".join(f"file '{x.name}'\n" for x in parts))
    preview = d / "final_preview.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst)]
    if p["audio"]:
        cmd += ["-i", str(cap / "audio_his.m4a"), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-shortest"]
    cmd += ["-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={fps}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", str(preview)]
    run(cmd)
    lst.unlink()
    p["final"] = str(preview.relative_to(d))
    save(d, p)
    build_board(d, p)
    print(f"capcut folder: {cap}")
    print(f"preview: {preview}")
    if missing:
        print(f"slates (no cut clip yet) for scenes: {', '.join(missing)}")


# ---------- board ----------
STATUS_COLORS = {"planned": "#6b7280", "frames ready": "#e0a500", "clip ready": "#3b82f6",
                 "cut": "#22c55e", "locked": "#22c55e", "redo": "#ef4444"}


def media(src, kind, label):
    if not src:
        return f'<figure class="m empty"><div>{label}<br><small>not yet</small></div><figcaption>{label}</figcaption></figure>'
    src = html.escape(src)
    if kind == "video":
        el = f'<video src="{src}" muted loop playsinline preload="metadata"></video>'
    else:
        el = f'<img src="{src}" loading="lazy" alt="{label}">'
    return f'<figure class="m">{el}<figcaption>{label}</figcaption></figure>'


def refs_html(d):
    refs = sorted((d / "refs").glob("*.*")) if (d / "refs").exists() else []
    if not refs:
        return ""
    items = "".join(f'<figure><img src="refs/{html.escape(r.name)}" alt="{html.escape(r.stem)}"><figcaption>{html.escape(r.stem)}</figcaption></figure>' for r in refs)
    return f'<div class="refs"><span class="side ours">Refs</span>{items}</div>'


def build_board(d, p):
    esc = html.escape
    done = sum(1 for s in p["scenes"] if s["ours"]["clip"])
    n = len(p["scenes"])
    bars = "".join(f'<i class="{"on" if s["ours"]["clip"] else ""}"></i>' for s in p["scenes"])
    rows = []
    for s in p["scenes"]:
        o = s["ours"]
        col = STATUS_COLORS.get(s["status"], "#6b7280")
        cut = f' · in {o["in_point"]}s @ {o["speed"]}x' if o["clip"] and o["in_point"] is not None else ""
        attempts = "".join(f"<li>{esc(x)}</li>" for x in o["attempts"])
        rows.append(f"""
<section class="scene" data-start="{s['start']}" data-end="{s['end']}">
  <header><b>Scene {s['id']}</b><span class="tc">{tc(s['start'])} → {tc(s['end'])} · {s['dur']:.2f}s</span>
    <span class="badge" style="--c:{col}">{esc(s['status'].upper())}</span></header>
  <p class="desc">{esc(s['desc']) or '<em>describe the beat: camera, people, action</em>'}</p>
  {f'<p class="plan"><b>Ours:</b> {esc(s["plan"])}</p>' if s.get('plan') else ''}
  {f'<p class="txt">On-screen: “{esc(s["text"])}”</p>' if s['text'] else ''}
  <div class="row"><span class="side">Theirs<br><small>reference</small></span>
    {media(s['his']['start_frame'], 'img', 'Start frame')}{media(s['his']['end_frame'], 'img', 'End frame')}{media(s['his']['clip'], 'video', 'Clip')}</div>
  <div class="row"><span class="side ours">Ours<br><small>{esc(p.get('model',''))}{cut}</small></span>
    {media(o['start_frame'], 'img', 'Start frame')}{media(o['end_frame'], 'img', 'End frame')}{media(o['clip'] or o['raw_clip'], 'video', 'Clip')}</div>
  {f'<ul class="att">{attempts}</ul>' if attempts else ''}
</section>""")
    page = f"""<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="claude:viewport-fit-sides" content="cover">
<title>{esc(p['title'])} Scene Board</title><style>
/* editing-suite board: one committed dark look */
:root{{--bg:#17161a;--card:#211f25;--line:#322f37;--fg:#ece9ee;--mut:#a29da8;--acc:#f5b400;--ours:#ff7eb6;color-scheme:dark}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding-block:24px 80px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}}
.plan{{margin:0 0 8px;color:var(--ours)}}.plan b{{color:var(--ours)}}
.kicker{{color:var(--mut);font-size:11px;letter-spacing:.12em;text-transform:uppercase}}
h1{{margin:4px 0 16px;font-size:30px}}.top{{display:grid;grid-template-columns:1fr auto;gap:20px}}
.meta span{{margin-right:16px;color:var(--mut)}}.meta b{{color:var(--fg)}}
.bars{{display:flex;gap:6px;margin:14px 0}}.bars i{{flex:1;height:4px;border-radius:2px;background:var(--line)}}.bars i.on{{background:var(--acc)}}
.full{{display:flex;gap:10px}}.full figure{{width:120px;margin:0}}.full video,.full .ph{{width:120px;aspect-ratio:9/16;border-radius:8px;background:#000;object-fit:cover;display:grid;place-items:center;color:var(--mut);font-size:12px;text-align:center}}
figcaption{{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin-top:4px}}
.scene{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:18px 0}}
.scene header{{display:flex;gap:12px;align-items:baseline}}.tc{{color:var(--mut);font-family:ui-monospace,monospace;font-size:12px}}
.badge{{margin-left:auto;border:1px solid var(--c);color:var(--c);font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px}}
.desc{{margin:6px 0}}.txt{{color:var(--acc);margin:0 0 8px}}
.row{{display:grid;grid-template-columns:70px repeat(3,1fr);gap:10px;margin-top:10px;align-items:start}}
.side{{color:var(--mut);font-size:12px}}.side.ours{{color:var(--ours)}}
.m{{margin:0}}.m img,.m video{{width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:8px;background:#000;display:block}}
.m.empty div{{aspect-ratio:9/16;border:1px dashed var(--line);border-radius:8px;display:grid;place-items:center;text-align:center;color:var(--mut)}}
.att{{color:var(--mut);font-size:12px;margin:10px 0 0}}
.refs{{display:flex;gap:10px;align-items:start;flex-wrap:wrap;margin:6px 0 4px}}.refs figure{{margin:0;width:90px}}.refs img{{width:90px;aspect-ratio:3/4;object-fit:cover;border-radius:8px;display:block}}
.ctl{{position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:2;display:flex;gap:8px}}
button{{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 12px;cursor:pointer}}
@media(max-width:640px){{.top{{grid-template-columns:1fr}}.row{{grid-template-columns:repeat(3,1fr)}}.side{{grid-column:1/-1}}}}
</style></head><body><main>
<div class="kicker">{esc(p['title'])} · competitor copy, scene by scene</div>
<h1>{esc(p['title'])} Scene Board</h1>
<div class="top"><div>
  <div class="meta"><span>Brand <b>{esc(p.get('brand') or 'TBD')}</b></span><span>Scenes <b>{done}/{n}</b> cut</span>
  <span>Mode <b>{esc(p.get('mode','RECREATE'))}</b></span><span>Model <b>{esc(p.get('model',''))}</b></span></div>
  <p><b>Changes</b> {esc(p.get('changes') or '—')} Backgrounds, timing, camera = exact reference. Start frames first, clips after your OK.</p>
  <div class="bars">{bars}</div>
</div><div class="full">
  <figure><video src="{esc(p['source'])}" muted loop playsinline controls></video><figcaption>Theirs · full</figcaption></figure>
  <figure>{f'<video src="{esc(p["final"])}" muted loop playsinline controls></video>' if p.get('final') else '<div class="ph">Final video lands here</div>'}<figcaption>Ours · final</figcaption></figure>
</div></div>
{refs_html(d)}
<div class="ctl"><button id="play">▶ Play all scenes</button><button id="slow">Slow-mo</button><button id="snd">Sound off</button></div>
{''.join(rows)}
</main><script>
const vids=()=>[...document.querySelectorAll('.scene video')];
let slow=false,sound=false,playing=false;
play.onclick=()=>{{playing=!playing;vids().forEach(v=>{{playing?v.play():v.pause()}});play.textContent=playing?'❚❚ Pause':'▶ Play all scenes'}};
slow.onclick=()=>{{slow=!slow;vids().forEach(v=>v.playbackRate=slow?.25:1);slow.textContent=slow?'Normal speed':'Slow-mo'}};
snd.onclick=()=>{{sound=!sound;document.querySelectorAll('video').forEach(v=>v.muted=!sound);snd.textContent=sound?'Sound on':'Sound off'}};
document.querySelectorAll('.scene').forEach(sc=>sc.querySelectorAll('video').forEach(v=>{{v.onmouseenter=()=>v.play();v.onmouseleave=()=>{{if(!playing)v.pause()}}}}));
</script>"""
    (d / "board.html").write_text(page)


def cmd_board(a):
    d, p = load(a.name)
    build_board(d, p)
    print(d / "board.html")


# ---------- cli ----------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    b = sp.add_parser("breakdown", help="split the original into scenes")
    b.add_argument("name"); b.add_argument("video")
    b.add_argument("--title"); b.add_argument("--model", default="Wan 3.0")
    b.add_argument("--threshold", type=float, default=0.3, help="scene-change sensitivity (lower = more cuts)")
    b.add_argument("--min-len", type=float, default=0.4, help="ignore cuts closer than this (s)")
    b.add_argument("--cuts", help="manual cut times, e.g. 2.0,3.5,6.1 (overrides detection)")
    b.add_argument("--force", action="store_true")
    b.set_defaults(f=cmd_breakdown)

    s = sp.add_parser("set", help="record info / our files on the project or a scene")
    s.add_argument("name"); s.add_argument("scene", nargs="?")
    for k in ("title", "brand", "changes", "model", "mode", "caption", "desc", "text", "camera", "status", "plan", "attempt"):
        s.add_argument(f"--{k}")
    s.add_argument("--start-frame", dest="start_frame"); s.add_argument("--end-frame", dest="end_frame")
    s.add_argument("--raw-clip", dest="raw_clip")
    s.set_defaults(f=cmd_set)

    c = sp.add_parser("colormatch", help="match our frames' color to his")
    c.add_argument("--project", dest="name"); c.add_argument("--scene")
    c.add_argument("--src"); c.add_argument("--ref"); c.add_argument("--out")
    c.add_argument("--width", type=int, default=1536); c.add_argument("--no-skip", action="store_true", help="don't skip the caption band")
    c.set_defaults(f=cmd_colormatch)

    m = sp.add_parser("beatmatch", help="cut our raw clip to his exact scene length")
    m.add_argument("name"); m.add_argument("scene")
    m.add_argument("--in", dest="in_point", type=float); m.add_argument("--speed", type=float)
    m.add_argument("--his-beat", type=float, help="key beat time inside HIS scene (s)")
    m.add_argument("--our-beat", type=float, help="same beat inside OUR raw clip (s)")
    m.set_defaults(f=cmd_beatmatch)

    x = sp.add_parser("assemble", help="build the CapCut folder + preview")
    x.add_argument("name"); x.set_defaults(f=cmd_assemble)

    bd = sp.add_parser("board", help="rebuild board.html"); bd.add_argument("name"); bd.set_defaults(f=cmd_board)

    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
