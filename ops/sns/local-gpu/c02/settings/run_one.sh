# 1本ぶん: 動画を作る → 毎秒24コマにする → 確認用の絵
# 使い方: bash run_one.sh 名前 seed
cd D:/ai/work/c02
n=$1; s=$2; O=D:/ai/ComfyUI_windows_portable/ComfyUI/output
python -c "import json;c=json.load(open('$n.json',encoding='utf-8'));c['seed']=$s;c['prefix']='${n}_s$s';json.dump(c,open('_cur.json','w',encoding='utf-8'),ensure_ascii=False)"
python wan_cfg.py _cur.json | tee -a gen.log
ffmpeg -y -v error -framerate 16 -i $O/${n}_s${s}_%05d_.png -c:v libx264 -crf 14 -pix_fmt yuv420p ${n}_s${s}_16.mp4
TORCHDYNAMO_DISABLE=1 D:/ai/MuseTalk/.venv/Scripts/python.exe -I rife_fps.py ${n}_s${s}_16.mp4 ${n}_s${s}.mp4 24
ffmpeg -y -v error -i ${n}_s${s}_16.mp4 -vf "select='not(mod(n\,16))',scale=288:-1,tile=6x1" -frames:v 1 ${n}_s${s}_tile.png
echo "$n seed$s できた"
