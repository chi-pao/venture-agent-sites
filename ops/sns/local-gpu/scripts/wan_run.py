# ComfyUI に Wan 2.2 TI2V-5B の「絵 → 5秒の動画」を頼み、終わるまで待つ
import json, sys, time, urllib.request

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
prefix = sys.argv[2] if len(sys.argv) > 2 else "wan05"
pos = ("A Japanese family of four sitting behind a quiz show desk, quietly discussing the answer together. "
       "The father on the left keeps his hand on his chin, thinking, with small natural head movements and blinking. "
       "The mother nods gently and smiles. The boy keeps his hand raised and smiles. The girl looks at them and smiles. "
       "Subtle, natural, realistic body movement and breathing. Everyone stays in place and faces the same direction. "
       "Static camera, fixed shot, no camera movement, no zoom, no pan.")
neg = ("camera movement, zoom, pan, shaking, text, subtitles, watermark, logo, distorted face, deformed hands, "
       "extra fingers, extra people, blurry, low quality, jpeg artifacts, flicker, morphing, static image, frozen")
wf = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
    "4": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 8.0}},
    "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": pos}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": neg}},
    "7": {"class_type": "LoadImage", "inputs": {"image": "family704.png"}},
    "8": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["3", 0], "width": 1280, "height": 704, "length": 121, "batch_size": 1, "start_image": ["7", 0]}},
    "9": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["8", 0],
                                               "seed": seed, "steps": 20, "cfg": 5.0, "sampler_name": "uni_pc", "scheduler": "simple", "denoise": 1.0}},
    "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
    "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": prefix}},
}
req = urllib.request.Request("http://127.0.0.1:8188/prompt", data=json.dumps({"prompt": wf}).encode(), headers={"Content-Type": "application/json"})
pid = json.load(urllib.request.urlopen(req))["prompt_id"]
print("受付:", pid, flush=True)
t = time.time()
while True:
    time.sleep(15)
    h = json.load(urllib.request.urlopen(f"http://127.0.0.1:8188/history/{pid}"))
    if pid in h:
        st = h[pid].get("status", {})
        print("おわり", st.get("status_str"), round(time.time() - t), "秒", flush=True)
        if st.get("status_str") != "success":
            print(json.dumps(st, ensure_ascii=False)[:3000])
        break
