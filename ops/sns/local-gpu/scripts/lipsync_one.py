# 動画の中の「1人だけ」の口を、声に合わせる（MuseTalk 1.5 を使う）
# 元の MuseTalk の顔の位置決め（mmpose/DWPose）の代わりに face-alignment（BSD-3）の68点を使う
# 使い方: python lipsync_one.py 動画 声.wav 出力.mp4 顔のだいたいのx 顔のだいたいのy [声が始まる秒]
import sys, os, math, copy, subprocess, tempfile
import cv2, numpy as np, torch, librosa
from transformers import WhisperModel
import face_alignment

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from musetalk.utils.utils import load_all_model
from musetalk.utils.audio_processor import AudioProcessor
from musetalk.utils.face_parsing import FaceParsing
from musetalk.utils.blending import get_image

vid, wav, out, tx, ty = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5])
offset = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0
dev = torch.device("cuda")

cap = cv2.VideoCapture(vid)
fps = cap.get(cv2.CAP_PROP_FPS)
frames = []
while True:
    ok, f = cap.read()
    if not ok:
        break
    frames.append(f)
cap.release()
N = len(frames)
H, W = frames[0].shape[:2]
print("frames", N, "fps", fps, "size", W, H)

# 声を動画の長さに合わせる（始まりの前と後ろは無音）
y, _ = librosa.load(wav, sr=16000)
full = np.zeros(int(N / fps * 16000) + 1600, dtype=np.float32)
s0 = int(offset * 16000)
full[s0:s0 + len(y)] = y[: len(full) - s0]
tmpd = tempfile.mkdtemp()
padded = os.path.join(tmpd, "voice.wav")
import soundfile as sf
sf.write(padded, full, 16000)
speech = (int(offset * fps) - 2, int((offset + len(y) / 16000) * fps) + 3)  # 口を動かすフレームの範囲

# 顔の位置（68点）
fa = face_alignment.FaceAlignment(face_alignment.LandmarksType.TWO_D, flip_input=False, device="cuda")
boxes = []
prev = (tx, ty)
for f in frames:
    lms = fa.get_landmarks_from_image(f[:, :, ::-1].copy())
    if not lms:
        boxes.append(None)
        continue
    lm = min(lms, key=lambda l: (l[:, 0].mean() - prev[0]) ** 2 + (l[:, 1].mean() - prev[1]) ** 2)
    prev = (lm[:, 0].mean(), lm[:, 1].mean())
    lm = lm.astype(np.int32)
    half = lm[29]
    half_dist = np.max(lm[:, 1]) - half[1]
    upper = max(0, half[1] - half_dist)
    boxes.append([int(np.min(lm[:, 0])), int(upper), int(np.max(lm[:, 0])), int(np.max(lm[:, 1]))])
# 見つからなかったフレームは前後で埋め、少しならす
for i in range(N):
    if boxes[i] is None:
        j = next((k for k in range(N) if boxes[k] is not None), None)
        near = min((k for k in range(N) if boxes[k] is not None), key=lambda k: abs(k - i))
        boxes[i] = list(boxes[near])
b = np.array(boxes, dtype=np.float32)
k = 2
sm = np.array([b[max(0, i - k): i + k + 1].mean(0) for i in range(N)]).astype(np.int32)
print("顔の枠（最初）", sm[0].tolist())

vae, unet, pe = load_all_model(unet_model_path="models/musetalkV15/unet.pth", vae_type="sd-vae",
                               unet_config="models/musetalkV15/musetalk.json", device=dev)
pe = pe.half().to(dev); vae.vae = vae.vae.half().to(dev); unet.model = unet.model.half().to(dev)
ap = AudioProcessor(feature_extractor_path="models/whisper")
whisper = WhisperModel.from_pretrained("models/whisper").to(dev, dtype=torch.float16).eval()
feats, ln = ap.get_audio_feature(padded)
chunks = ap.get_whisper_chunk(feats, dev, torch.float16, whisper, ln, fps=fps,
                              audio_padding_length_left=2, audio_padding_length_right=2)
fp = FaceParsing(left_cheek_width=90, right_cheek_width=90)
margin = 10
outd = os.path.join(tmpd, "f"); os.makedirs(outd)
t0 = torch.tensor([0], device=dev)
with torch.no_grad():
    for i in range(N):
        fr = frames[i]
        if speech[0] <= i <= speech[1] and i < len(chunks):
            x1, y1, x2, y2 = sm[i].tolist()
            y2 = min(y2 + margin, H)
            crop = cv2.resize(fr[y1:y2, x1:x2], (256, 256), interpolation=cv2.INTER_LANCZOS4)
            lat = vae.get_latents_for_unet(crop).to(torch.float16)
            af = pe(chunks[i:i + 1].to(dev))
            pred = unet.model(lat, t0, encoder_hidden_states=af).sample
            rec = vae.decode_latents(pred)[0]
            rec = cv2.resize(rec.astype(np.uint8), (x2 - x1, y2 - y1))
            fr = get_image(copy.deepcopy(fr), rec, [x1, y1, x2, y2], mode="jaw", fp=fp)
        cv2.imwrite(os.path.join(outd, f"{i:05d}.png"), fr)

subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(fps), "-i", os.path.join(outd, "%05d.png"),
                "-i", padded, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", "-c:a", "aac", "-b:a", "160k",
                "-shortest", out], check=True)
print("できた:", out, "口を動かした範囲", speech)
