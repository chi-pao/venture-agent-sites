# のぼるさんのパソコンで使った道具（2026-11-17・試しの1場面）

パソコン: RTX 4070 SUPER（12GB）／メモリ 32GB／Windows 11。道具はすべて D ドライブの `D:\ai\` に入れた（空きは約1.9TB）。

## できた物
- `test/out-05.mp4`：1280×704、毎秒24コマ、約5秒。家族4人が相談している動きの中で、1.0秒目からケンジ（左のお父さん）が「いや、Aじゃないか？」と話す
- 文字・数字は入れていない。カメラは動かしていない

## 使った道具と決まり（ライセンス）

### 動きを作る
| 道具 | 版 | 決まり | お金のからむ使い方 |
|---|---|---|---|
| ComfyUI（ポータブル版・NVIDIA用） | v0.45.0 | GPL-3.0（道具の決まり。作った動画には及ばない） | 可 |
| Wan 2.2 TI2V-5B（`wan2.2_ti2v_5B_fp16.safetensors`） | Comfy-Org の再配布版 | Apache 2.0 | 可 |
| Wan 2.2 VAE（`wan2.2_vae.safetensors`） | 同上 | Apache 2.0 | 可 |
| 文章を読む部品 umT5-XXL（`umt5_xxl_fp8_e4m3fn_scaled.safetensors`） | Comfy-Org の再配布版 | Apache 2.0 | 可 |

設定: 1280×704、121コマ、20段、CFG 5、uni_pc、shift 8、seed 42。かかった時間は約6分。
手順は `scripts/wan_run.py`（ComfyUI に頼んで、終わるまで待つ）。

### 口を声に合わせる
| 道具 | 版 | 決まり | お金のからむ使い方 |
|---|---|---|---|
| MuseTalk 1.5（本体のプログラム） | GitHub の最新（0a89dec） | MIT（「学術にも商用にも制限なし」と明記） | 可 |
| MuseTalk 1.5 の学習済みデータ（`musetalkV15/unet.pth`） | Hugging Face TMElyralab/MuseTalk | MIT（「商用を含むどんな目的にも使える」と明記） | 可 |
| sd-vae-ft-mse（絵を小さくまとめる部品） | stabilityai | MIT | 可 |
| whisper-tiny（声を読む部品） | openai | MIT | 可 |
| face-parsing BiSeNet（`79999_iter.pth`、顔の部分分け） | zllrunning/face-parsing.PyTorch | MIT | 可 |
| resnet18（上の部品の土台） | PyTorch 公式配布 | BSD-3（torchvision） | 可 |
| face-alignment（顔の位置と68点） | 1.5.0（2DFAN4・S3FD の重みつき） | BSD-3 | 可 |

かかった時間は1分ほど。手順は `scripts/lipsync_one.py`。
元の MuseTalk は顔の位置決めに DWPose（mmpose）を使うが、Windows で入れにくいため、同じ68点を出す face-alignment で置きかえた。4人のうち、指定した位置にいちばん近い顔（ケンジ）だけを動かし、声のある間だけ口を作りかえている。

## 使わなかった物と理由
- **LatentSync（ByteDance）**：本体は Apache 2.0、学習済みデータは openrail++。ただし、顔を見つける部品に insightface を使っている。insightface の学習済みデータ（buffalo_l など）は研究目的に限る決まりのため、お金のからむ使い方には使えないと判断した
- **DWPose・SyncNet**：MuseTalk の付属だが、今回の手順では使わない（SyncNet は学習用）

## わかったこと・次への注意
- 1場面（5秒）は、動き6分＋口合わせ1分で作れる
- Wan 2.2 は、ケンジがうつむいたり目を閉じたりする動きも作る。話す場面では、顔が正面を向き続けるよう指示をもっと強める必要がある
- 「手を挙げたまま」の指示は守られず、男の子は途中で手を下ろした
- 口の開き方はやや控えめ。もっと大きく動かしたいときは、MuseTalk の代わりの道具を試すか、話す人の顔を大きく写した絵を使う
- のぼるさんのパソコンで ComfyUI を動かすには `D:\ai\ComfyUI_windows_portable\run_nvidia_gpu.bat` をダブルクリックする（画面は http://127.0.0.1:8188 ）
