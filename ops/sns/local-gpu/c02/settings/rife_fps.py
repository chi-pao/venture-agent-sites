# 動画のコマの間を RIFE 4.7 で埋めて、指定のコマ数/秒にする（声なし）
# 使い方: python rife_fps.py 入力.mp4 出力.mp4 コマ数
import sys, os, types, subprocess, tempfile
import cv2, numpy as np, torch
RD = r"D:\ai\ComfyUI_windows_portable\ComfyUI\custom_nodes\ComfyUI-Frame-Interpolation"
mm = types.ModuleType("comfy.model_management"); mm.get_torch_device = lambda: torch.device("cuda")
sys.modules["comfy"] = types.ModuleType("comfy"); sys.modules["comfy.model_management"] = mm
sys.path.insert(0, os.path.join(RD, "vfi_models", "rife"))
from rife_arch import IFNet
src, out, OF = sys.argv[1], sys.argv[2], int(sys.argv[3])
cap = cv2.VideoCapture(src); fps = cap.get(cv2.CAP_PROP_FPS); fr = []
while True:
    ok, f = cap.read()
    if not ok: break
    fr.append(f)
net = IFNet(arch_ver="4.7")
net.load_state_dict(torch.load(os.path.join(RD, "ckpts", "rife", "rife47.pth"), weights_only=False))
net.eval().cuda()
t = lambda im: torch.from_numpy(im[:, :, ::-1].astype(np.float32).copy() / 255).permute(2, 0, 1)[None].cuda()
tmp = tempfile.mkdtemp(); n = int((len(fr) - 1) / fps * OF) + 1
with torch.inference_mode():
    for k in range(n):
        p = k / OF * fps; i = min(int(p), len(fr) - 2); a = p - i
        if a < 1e-3: im = fr[i]
        elif a > 1 - 1e-3: im = fr[i + 1]
        else:
            x = net(t(fr[i]), t(fr[i + 1]), torch.tensor([[[[a]]]], device="cuda"), [8, 4, 2, 1], False, True)
            im = (x[0].permute(1, 2, 0).clamp(0, 1).cpu().numpy() * 255).round().astype(np.uint8)[:, :, ::-1]
        cv2.imwrite(os.path.join(tmp, f"{k:05d}.png"), im)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(OF), "-i", os.path.join(tmp, "%05d.png"),
                "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", out], check=True)
print("コマ数", len(fr), "→", n)
