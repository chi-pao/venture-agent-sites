# 値段クイズ AI アバター版（Q01-v3）の作り方

全部無料・この作業場所の中だけで作る。ChatGPT は使わない（人物の素材だけ、のぼるさんが最初に1回用意）。

1. セリフ: `lines.json`（[番号, 話す人, 声に渡す文（漢字まじりの普通の文）, 画面の字幕]）
2. 声: AivisSpeech 1.2.0（速さ1.0〜1.05・抑揚1.15・テンポの強弱1.15）。司会＝阿井田 茂（Shout）、ケンジ＝fumifumi、ミホ＝morioki、ソウタ＝まお（ふつー）、ハナ＝コハク。すべて ACML 1.0（商用可）
3. しゃべる映像: SadTalker（Apache 2.0・商用可）。顔写真＝`ops/sns/characters/avatar/*-face.png`、`--preprocess full --size 256 --expression_scale 1.25（司会 1.4）`。待ち時間の顔は無音3秒で作る（まばたき・小さな動き）。CPU で1秒あたり約1.5分
4. 時間割: `tl.py` → `tl.json`
5. 背景・文字・紙吹雪: `layers.html` を `rl.js` で1枚ずつ撮る（背景 bg と前面 fg の2層）
6. 組み立て: `assemble.py`（話す人のアップをゆっくり寄せ／引き、横すべり・円形の切り替え、曲と効果音を重ねる）
