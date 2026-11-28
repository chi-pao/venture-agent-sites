# -*- coding: utf-8 -*-
"""ノボログ：パソコンの GPU（ComfyUI）で、投稿用の AI 画像・AI 動画を作る。

- 画像：FLUX.1 schnell（Apache 2.0）。4ステップで速い。
- 動画：Wan 2.2 TI2V 5B（Apache 2.0）。AI 画像から 2〜3 秒の動く場面を作る。
- どちらも無料・パソコンの中で動く。ComfyUI が起動していなければ自動で起動する。
- 作る絵は「暮らしの場面」だけ。商品そのものは描かない（実物と違う絵で誤解させないため）。
  文字・ロゴ・実在の人物は入れない（文字はあとからこちらで入れる）。

ComfyUI の場所は config.json の comfy_dir（決まりは C:/AI/comfy/ComfyUI_windows_portable）。
"""
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMFY_DIR = Path("C:/AI/comfy/ComfyUI_windows_portable")
HOST = "http://127.0.0.1:8188"
# 絵の雰囲気（2026-11-27 のぼるさん：アニメ風でも、写真風でも、動画でもよい）
STYLES = {
    "photo": "photorealistic, natural soft light, cozy Japanese home, 35mm photo, high detail",
    "anime": ("Japanese anime illustration, slice-of-life anime still, clean line art, soft cel shading, "
              "warm pastel colors, cozy Japanese home"),
}
STYLE = ("photorealistic, natural soft light, cozy Japanese home, 35mm photo, high detail, "
         "no text, no letters, no logo, no watermark")
NEGATIVE = "text, letters, words, logo, watermark, brand name, deformed hands, blurry, low quality"


class AIError(RuntimeError):
    pass


def _req(path, data=None, timeout=30):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(HOST + path, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def alive():
    try:
        _req("/system_stats", timeout=3)
        return True
    except Exception:
        return False


def start(comfy_dir=COMFY_DIR, wait=180):
    """ComfyUI が動いていなければ、画面を出さずに起動して待つ。"""
    if alive():
        return
    py = comfy_dir / "python_embeded" / "python.exe"
    main = comfy_dir / "ComfyUI" / "main.py"
    if not py.exists():
        raise AIError(f"ComfyUI が見つかりません: {comfy_dir}")
    log = open(comfy_dir / "comfy_server.log", "a", encoding="utf-8")
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    subprocess.Popen([str(py), "-s", str(main), "--windows-standalone-build", "--listen", "127.0.0.1",
                      "--port", "8188"], cwd=str(comfy_dir), stdout=log, stderr=log, creationflags=flags)
    for _ in range(wait // 3):
        time.sleep(3)
        if alive():
            return
    raise AIError("ComfyUI が起動しませんでした（comfy_server.log を見てください）")


def upload(path):
    """画像を ComfyUI の input に送る。"""
    boundary = uuid.uuid4().hex
    data = Path(path).read_bytes()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{Path(path).name}\"\r\n"
            f"Content-Type: image/png\r\n\r\n").encode() + data + \
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(HOST + "/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["name"]


def run(workflow, timeout=1800):
    """ワークフローを流して、できた画像ファイルの一覧を返す。"""
    pid = _req("/prompt", {"prompt": workflow, "client_id": "noborog"})["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(2)
        h = _req(f"/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                raise AIError(f"AI の生成に失敗しました: {str(msgs)[:300]}")
            files = []
            for out in h[pid].get("outputs", {}).values():
                for img in out.get("images", []):
                    q = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img["subfolder"],
                                                "type": img["type"]})
                    files.append(q)
            return files
    raise AIError("AI の生成が時間内に終わりませんでした")


def fetch(q, out):
    with urllib.request.urlopen(HOST + "/view?" + q, timeout=60) as r:
        Path(out).write_bytes(r.read())
    return out


def style_text(art):
    return STYLES.get(art or "photo", STYLES["photo"]) + ", no text, no letters, no logo, no watermark"


def image(prompt, out, width=896, height=1120, seed=None, art="photo", init=None, denoise=0.7):
    """FLUX.1 schnell で1枚作る（縦長 4:5）。art: "photo"（写真風）か "anime"（アニメ風）。
    init：もとにする絵（使う前の絵から、同じ場所の「使った後」を作るとき）。denoise が小さいほど、もとの絵に近い。"""
    seed = seed if seed is not None else int(time.time() * 1000) % 2**32
    if init is not None:
        name = upload(init)
        wf = {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-schnell-fp8.safetensors"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": f"{prompt}, {style_text(art)}", "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
            "4": {"class_type": "LoadImage", "inputs": {"image": name}},
            "8": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["1", 2]}},
            "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                                                       "latent_image": ["8", 0], "seed": seed, "steps": 8, "cfg": 1.0,
                                                       "sampler_name": "euler", "scheduler": "simple",
                                                       "denoise": float(denoise)}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "noborog_img"}},
        }
        files = run(wf, timeout=600)
        if not files:
            raise AIError("画像ができませんでした")
        return fetch(files[0], out)
    wf = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1-schnell-fp8.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": f"{prompt}, {style_text(art)}", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
        "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                                                   "latent_image": ["4", 0], "seed": seed, "steps": 4, "cfg": 1.0,
                                                   "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "noborog_img"}},
    }
    files = run(wf, timeout=600)
    if not files:
        raise AIError("画像ができませんでした")
    return fetch(files[0], out)


EDIT_MODEL = "qwen_image_edit_2511_fp8mixed.safetensors"
EDIT_LORA = "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"


def can_edit():
    """「絵を見せて直す」AI（Qwen-Image-Edit、Apache 2.0）が入っているか。"""
    m = COMFY_DIR / "ComfyUI" / "models"
    return (m / "diffusion_models" / EDIT_MODEL).exists() and (m / "loras" / EDIT_LORA).exists()


def edit(scene, prompt, out, product=None, seed=None, steps=4):
    """Qwen-Image-Edit 2511 で、scene の絵を直す（場所はそのまま）。product（楽天の商品写真）を渡すと、
    その形の商品を絵の中で使わせられる（楽天の写真そのものは加工しない。参考に見せるだけ）。"""
    seed = seed if seed is not None else int(time.time() * 1000) % 2**32
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": EDIT_MODEL, "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": EDIT_LORA,
                                                              "strength_model": 1.0}},
        "3": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["2", 0], "shift": 3.1}},
        "4": {"class_type": "CFGNorm", "inputs": {"model": ["3", 0], "strength": 1.0}},
        "5": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                                                     "type": "qwen_image", "device": "default"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "7": {"class_type": "LoadImage", "inputs": {"image": upload(scene)}},
        "8": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["7", 0], "upscale_method": "lanczos",
                                                                  "megapixels": 1.0, "resolution_steps": 1}},
        "10": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["5", 0], "prompt": prompt,
                                                                       "vae": ["6", 0], "image1": ["8", 0]}},
        "11": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["5", 0], "prompt": "",
                                                                       "vae": ["6", 0], "image1": ["8", 0]}},
        "14": {"class_type": "VAEEncode", "inputs": {"pixels": ["8", 0], "vae": ["6", 0]}},
        "15": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["12", 0], "negative": ["13", 0],
                                                    "latent_image": ["14", 0], "seed": seed, "steps": steps, "cfg": 1.0,
                                                    "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
        "16": {"class_type": "VAEDecode", "inputs": {"samples": ["15", 0], "vae": ["6", 0]}},
        "17": {"class_type": "SaveImage", "inputs": {"images": ["16", 0], "filename_prefix": "noborog_edit"}},
    }
    if product is not None:
        wf["9"] = {"class_type": "LoadImage", "inputs": {"image": upload(product)}}
        wf["10"]["inputs"]["image2"] = ["9", 0]
        wf["11"]["inputs"]["image2"] = ["9", 0]
    for k, src in (("12", "10"), ("13", "11")):
        wf[k] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
                 "inputs": {"conditioning": [src, 0], "reference_latents_method": "index_timestep_zero"}}
    files = run(wf, timeout=1200)
    if not files:
        raise AIError("画像ができませんでした")
    return fetch(files[0], out)


def video(start_image, prompt, out_dir, frames=73, width=704, height=896, seed=None, art="photo"):
    """Wan 2.2 5B で、1枚の画像から動く場面（24fps・frames 枚）を作り、連番 PNG で返す。"""
    seed = seed if seed is not None else int(time.time() * 1000) % 2**32
    name = upload(start_image)
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors",
                                                     "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                                                     "type": "wan", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": f"{prompt}, {style_text(art)}, gentle natural motion, static camera",
                                                         "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE + ", fast motion, camera shake, morphing",
                                                         "clip": ["2", 0]}},
        "6": {"class_type": "LoadImage", "inputs": {"image": name}},
        "7": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["3", 0], "width": width, "height": height,
                                                                  "length": frames, "batch_size": 1,
                                                                  "start_image": ["6", 0]}},
        "8": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
        "9": {"class_type": "KSampler", "inputs": {"model": ["8", 0], "positive": ["4", 0], "negative": ["5", 0],
                                                   "latent_image": ["7", 0], "seed": seed, "steps": 20, "cfg": 5.0,
                                                   "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": "noborog_vid"}},
    }
    files = run(wf, timeout=3600)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, q in enumerate(files):
        paths.append(fetch(q, out_dir / f"f{i:04d}.png"))
    if not paths:
        raise AIError("動画のコマができませんでした")
    return paths
