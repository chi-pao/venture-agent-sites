# 怒るの1回目で顔が真っ赤に照らされたので、明るさ（表情）はそのまま、色だけを最初のコマの青い光に戻す
# 使い方: python fix_red.py 入力.mp4 出力.mp4（毎秒16コマの段階で使い、そのあと rife_fps.py で24コマにする）
import sys, cv2, numpy as np
c = cv2.VideoCapture(sys.argv[1]); fr = []
while True:
    ok, x = c.read()
    if not ok: break
    fr.append(x)
ref = cv2.cvtColor(fr[0], cv2.COLOR_BGR2YCrCb).astype(np.float32)
refc = cv2.GaussianBlur(ref[..., 1:], (0, 0), 6)
h, w = fr[0].shape[:2]
out = cv2.VideoWriter(sys.argv[2], cv2.VideoWriter_fourcc(*"mp4v"), 16, (w, h))
for x in fr:
    y = cv2.cvtColor(x, cv2.COLOR_BGR2YCrCb).astype(np.float32); y[..., 1:] = refc
    out.write(cv2.cvtColor(y.clip(0, 255).astype(np.uint8), cv2.COLOR_YCrCb2BGR))
out.release()
