# お買い得物件チェッカー 収益化調査レポート

- 対象: https://okaidokucyekka.streamlit.app（Streamlit Community Cloud）
- 作成: 収益化担当／調査日・確認日: **2026-11-01**（以下の「確認日」はすべてこの日）
- 調査方法と信頼度の注意: この作業環境では個別ページの本文取得（WebFetch／curl）が通信制限で使えず、**Web検索結果の要約・抜粋で確認**した。数字はその抜粋に出ていたものだけを載せている。ASPの報酬額は多くがログイン後の管理画面でしか見られず、**公開情報では確認できないものは「未確認」**とした。出典のない主張には「仮説」と書いた。法令の解釈は一般的な整理であり、法律相談ではない。

---

## (A) 結論：優先順位付きの施策トップ5

### 最初に共有したい重大な前提（リスク）
Streamlitの利用規約は2025-11-17に一本化された。現行の規約では、**Community Cloudのコンテンツで個人情報を扱う場合、利用は「個人的かつ非商用の目的（評価・教育・家庭内利用など）」に限られる**と読める（[streamlit.io/terms-of-use](https://streamlit.io/terms-of-use)、[規約統合の告知](https://discuss.streamlit.io/t/updates-to-terms-of-use-and-privacy-notices/120100)）。旧規約1.4(d)は、Community Cloudを「business or commercial purposes」に使うこと自体を禁じていたと、Streamlitのスタッフがフォーラムで説明している（[フォーラム](https://discuss.streamlit.io/t/streamlit-soc2-documentation/57942)）。
→ **アプリ内に広告やアフィリエイトを増やすほど規約上のリスクが上がる**。OCR用にアップロードされるスクリーンショットに個人情報が含まれうるかどうかで、扱いが変わる可能性がある（仮説）。現行規約の正確な条文は**未確認**（本文を取得できなかった）。施策は「**収益導線はアプリの外（静的LP）に置き、アプリ本体は無料ツールのままにする**」形を基本にした。

| 優先 | 施策 | 期待効果の根拠 | 手間 | リスク |
|---|---|---|---|---|
| 1 | **規約とPR表記の是正（守りの最優先）**。既存の火災保険リンクに「PR／広告」表記を付ける。「お買い得」判定の根拠と限界（参考価格であること、国交省データの加工値であること）を明記する。Streamlit現行規約の非商用条項を本文で確認する。 | ステマ規制（2023-10-01施行）で、アフィリエイトリンクを置く以上「PR」等の明示が必要。A8.netも提携メディアにPR表記を求めている（[A8公式資料](https://support.a8.net/ec/news/202308_01.pdf)）。違反すると広告主が措置命令の対象になり、提携解除につながりうる（仮説）。 | 小（文言修正のみ） | 放置すると提携停止・規約違反の恐れ |
| 2 | **静的ランディングページ（LP）を Cloudflare Pages（無料）に置き、アフィリエイト導線をそこへ集約する**。アプリからは「判定結果の次にやること」としてLPへリンクする。 | Cloudflare Pagesの無料プランは月500ビルド、静的配信の帯域は無制限とされる（[公式 limits](https://developers.cloudflare.com/pages/platform/limits)／帯域は第三者情報）。静的HTMLはJSで描画されるStreamlitより検索エンジンに読まれやすい（一般論。効果の大きさは仮説）。商用の導線をアプリから切り離せる。 | 中（LP数ページの作成とGA設定） | `*.pages.dev` のままだとブランド性が弱い。独自ドメインは有料なので今回の前提外 |
| 3 | **購入者の動線に合う案件を3〜4件だけ追加する**: ①住宅ローン比較・一括事前審査 ②引越し一括見積 ③リフォーム一括見積 ④（売却を同時に検討する人向けに）不動産一括査定。既存の火災保険と合わせて「購入までのチェックリスト」形式でLPに並べる。 | 公開情報で確認できた報酬例: 引越し侍 1,000円（税込1,100円）、タウンライフリフォーム 10,190〜13,000円（掲載ページで差あり）、イエウール 9,257〜9,428円（クローズドASPの情報）。いずれも(B)表を参照。住宅ローン案件の単価は**未確認**。 | 中（ASPごとの提携申請） | 住宅ローンは金融規制と表示ルールに注意（(C)参照）。一括査定は「売却側」なので、購入者には関連が弱い可能性がある（仮説） |
| 4 | **アプリ内の導線改善と計測**: 判定結果の直後に「次のステップ」（ローン事前審査 → インスペクション → 火災保険 → 引越し）を1行リンクで示す（リンク先はLP）。GA4でLPへのクリック数を計測する。 | 費用なしで、どの案件にニーズがあるかの実データが取れる。GAは導入済み。 | 小 | アプリ内のリンクを増やしすぎると、優先1の規約リスクと衝突する |
| 5 | **将来の選択肢: AdSense（LP側）と有料プラン**。AdSenseはアプリ上ではなく、コンテンツを充実させたLP側で申請を検討する。月額課金はトラフィックの実績が出てから検討する。 | streamlit.appのURLはAdSenseに登録できなかったという報告がある（[フォーラム](https://discuss.streamlit.io/t/google-adsense-doesnt-accept-streamlit-app-url/36157)）。AdSenseは「コンテンツのないページ」への広告掲載を禁じている（[Google blog](https://blog.google/products/adsense/how-to-address-insufficient-content/?m=0)）。課金には特商法の表記と最終確認画面が必要（(C)参照）。 | 大 | AdSenseは審査落ちの可能性がある。課金は運営者の住所などの開示と決済手数料（Stripeは国内カード3.6%とされる、[issoh.co.jp](https://www.issoh.co.jp/md/tech/15416)、未公式確認）が発生 |

**期待収益の数字は出していない**。現在のアクセス数・クリック率・成約率のデータがなく、推計すると「作った数字」になるため。GA4でLPのクリック率を1〜2か月計測してから見積もるのが妥当。

---

## (B) 案件・ASP一覧表

凡例: 確認日はすべて2026-11-01。「抜粋」はWeb検索結果に出ていた記述で、ページ本文は直接開けていない。

### B-1. 案件カテゴリ別

| カテゴリ | 案件例 | ASP | 報酬の目安 | 成果条件 | 出典 |
|---|---|---|---|---|---|
| 火災保険一括見積（**既存**） | 保険の窓口インズウェブ、保険スクエアbang!、住宅本舗など（比較記事に登場するサービス） | A8.net（現在の提携先）ほか | **未確認** | **未確認**（利用者向けキャンペーンは「見積もり完了・契約不要」が条件だが、アフィリエイトの成果条件とは別物） | [diamond-fudosan.jp](https://diamond-fudosan.jp/articles/-/1110695)、[selectra.jp](https://selectra.jp/car-insurance/guides/select/campaign) |
| 住宅ローン比較・一括事前審査 | モゲチェック、住宅本舗、一括ローン相談 by SUUMO など | **未確認** | **未確認** | **未確認**。モゲチェックの収益モデルは「利用者が借り換えた金融機関から手数料を受け取る」もの（アフィリエイト報酬とは別） | [mogecheck.jp](https://mogecheck.jp/articles/show/a1ZbO5YpEWejqLwWJxeN)、[digitalpr.jp](https://digitalpr.jp/r/17868) |
| 不動産一括査定（売却側） | イエウール | レントラックス（招待制のクローズドASP）。2019年時点ではLink-Aのみとの記事もある | 9,428円（AFI-ASP.TOKYO）／9,257円（別のまとめ記事）。どちらも抜粋 | **未確認** | [afi-asp.tokyo](https://afi-asp.tokyo/ieuuru-asp/)、[fudousan-iroha.jp](https://fudousan-iroha.jp/realestate-sale/ieul-affiliate/)（2019年情報）、[xn--cckcdp5nyc8gt664awj6b.net](https://xn--cckcdp5nyc8gt664awj6b.net/3694) |
| 不動産一括査定（売却側） | HOME4U | ASPを介さない直接契約とされる | **未確認** | **未確認** | [lab.iyell.jp](https://lab.iyell.jp/news/lab-home4u/) |
| 不動産一括査定（参考レンジ） | HOME4U、イエウール、すまいValue | — | 1,000〜3,000円とする記事と、5,000〜15,000円とする記事がある（**記事間で食い違い、信頼度低**） | **未確認** | [minimini-chuou.jp](https://minimini-chuou.jp/affiliate-asp/)、[sumai-compass.jp](https://sumai-compass.jp/real-estate-affiliate-marketing-start-blog-50k-month-guide/) |
| 不動産売却（タウンライフ） | タウンライフ不動産売却 | タウンライフアフィリエイト（自社ASP） | 10,190円（抜粋） | **未確認** | [townlife-aff.com/recd.html](https://townlife-aff.com/recd.html) |
| リフォーム一括見積 | タウンライフリフォーム | タウンライフアフィリエイト | 13,000円（税込14,300円、特集ページ）／10,190円・税込11,209円（別ページ）→ **掲載ページで差がある** | **未確認** | [townlife-aff.com/special_program.html](https://townlife-aff.com/special_program.html)、[townlife-aff.com/recd.html](https://townlife-aff.com/recd.html) |
| リフォーム一括見積 | リショップナビ（株式会社じげん、加盟4,500社超） | **未確認** | **未確認** | **未確認** | [prtimes.jp](https://prtimes.jp/main/html/rd/p/000000261.000008966.html) |
| 引越し見積 | 引越し侍（エイチームライフデザイン） | タウンライフアフィリエイトに掲載 | 1,000円（税込1,100円）。複数ページで一致 | 「引越し見積り」（詳細な条件は未確認） | [townlife-aff.com/recd.html](https://townlife-aff.com/recd.html)、[townlife-aff.com/special_program.html](https://townlife-aff.com/special_program.html) |
| 引越し見積 | SUUMO引越し見積もり | **未確認**（バリューコマースでの取扱いは未確認） | **未確認** | **未確認** | [ekitan.com](https://ekitan.com/media/moving/suumo/) |
| ホームインスペクション | さくら事務所 ほか | **ASPでの案件は見つからなかった** | **未確認** | **未確認** | [data-max.co.jp](https://data-max.co.jp/article/6266)（事業概要のみ） |
| 中古住宅購入相談・不動産仲介 | **未確認** | **未確認** | **未確認** | **未確認**。紹介料の受け取りそのものは直ちに違法ではないが、宅建業法上の「媒介」にあたると無免許営業になるリスクがある（(C)参照） | [atsoho.com](https://atsoho.com/blog/real-estate-referral-fee-legality) |
| 注文住宅・家づくり（参考） | タウンライフ家づくり | タウンライフアフィリエイト | 12,000円 → 13,000円（税抜）に引き上げ（2022年4月の告知） | **未確認** | [townlife-aff.com お知らせ](https://townlife-aff.com/info.php?id=625f5d32207da&type=news) |

### B-2. ASPの登録・提携審査（サイト要件）

| ASP | 登録審査 | 案件ごとの提携審査 | 支払い条件など | 出典 |
|---|---|---|---|---|
| A8.net | 登録時の審査なし、サイトがなくても登録可とされる（解説記事）。18歳未満は不可 | 案件ごとに提携申請と承認が必要。即時提携かどうかは**未確認** | 成果確定の翌々月15日払い（抜粋）。2023年8月から、提携メディアに「PR」表記を要請 | [xserver.ne.jp](https://www.xserver.ne.jp/blog/about-a8-asp/)、[onamae.com](https://www.onamae.com/server/rs/affiliate/)、[support.a8.net PDF](https://support.a8.net/ec/news/202308_01.pdf) |
| もしもアフィリエイト | **未確認** | **未確認** | 翌々月末払い（個人ブログの解説） | [onamae.com](https://www.onamae.com/column/affiliate/49/) |
| バリューコマース | サイト審査あり。目安は10〜20記事・1記事1,000字以上（**非公式の解説記事**） | **未確認** | 最低支払額1,000円、振込手数料無料 | [onamae.com](https://www.onamae.com/column/affiliate/16/)、[gmotech.jp](https://gmotech.jp/semlabo/affiliate/blog/asp-advertisement/) |
| アクセストレード | 5記事以上で通ったという報告（**SNSからの推測**） | **未確認** | **未確認** | [onamae.com](https://www.onamae.com/column/affiliate/39/) |
| afb | **未確認** | **未確認** | 翌月末払い、最低支払額777円、手数料無料 | [gmotech.jp](https://gmotech.jp/semlabo/affiliate/blog/asp-advertisement/) |
| タウンライフアフィリエイト | 住まい・不動産に特化（2013年開始）。審査難易度は**未確認** | **未確認** | 承認月の翌月25日払い（2020年11月以降） | [koukoku.jp](https://www.koukoku.jp/release/20171004/)、[umazura.net](https://umazura.net/townlife-aff) |
| レントラックス | 招待制のクローズドASP | — | — | [afi-asp.tokyo](https://afi-asp.tokyo/ieuuru-asp/) |

**示唆（仮説）**: Streamlitアプリそのものは「記事数」の基準を満たしにくく、ツールのみのサイトとして審査に落ちる可能性がある。施策2のLPに解説記事（中古住宅購入の流れ、参考価格の読み方など）を数本置くと、ASPの審査にも有利になると考えられる。

---

## (C) 法規制チェックリスト

### C-1. ステルスマーケティング規制（景品表示法、2023-10-01施行）
- [ ] アフィリエイトリンクがあるページに「広告」「PR」「プロモーション」等を明示する。消費者庁の運用基準はこれらの表記を例に挙げている（[keiyaku-watch.jp](https://keiyaku-watch.jp/media/kisochishiki/stealthmarketing/)、[advertimes](https://www.advertimes.com/20231204/article440236/)）。根拠条文は景表法5条3号の指定告示。
- [ ] 表記は、リンクのそばや記事の冒頭など、消費者が気付ける位置に置く（A8.netは「サイト／メディア内にPR等の表記」を要請。[A8 PDF](https://support.a8.net/ec/news/202308_01.pdf)）。
- [ ] 判定結果の画面とアフィリエイト導線を視覚的に分ける。「この判定は広告主から独立している」ことを示す文言を入れる（仮説: 判定の中立性に疑いを持たれるのを防ぐため）。
- [ ] 規制の直接の対象は広告主だが、ASPの規約違反として提携を解除される可能性がある（仮説）。

### C-2. 不動産の表示に関する公正競争規約（表示規約）
- [ ] 表示規約は景表法に基づく業界の自主ルールで、主な対象は宅建業者（公正取引協議会の会員）。このサービスは宅建業者ではないため、**直接の適用は限定的と考えられる（仮説）**。ただし、景表法の不当表示の考え方は参考にする。
- [ ] 「買得」「掘出」「格安」「投げ売り」「破格」「激安」は、著しく安いという印象を与える**特定用語**とされる（規約18条）。使うには合理的・客観的な根拠が必要で、**根拠となる事実の表示**が求められる（[静岡 自主点検表PDF](https://shizuoka.zennichi.or.jp/zswp/wp-content/uploads/2018/03/tenkenhyo180210.pdf)、[mc-law.jp](https://www.mc-law.jp/kigyohomu/24232)）。
- [ ] サービス名と判定ラベルの「お買い得」「割安」は、この特定用語に近い。対策として次の3点を推奨する: (1)「参考価格比 −X%」のように**比較の基準と数値を併記**する (2)「国交省データの加工値に基づく参考値であり、物件の個別事情（状態・権利関係・リフォーム履歴等）は反映していない」と注記する (3) 断定を避けた表現（例:「参考価格より低め」）を使う。「お買い得」自体が特定用語にあたるかは**未確認**。
- [ ] 不動産会社や仲介から報酬を受けて特定物件を「お買い得」と表示する形にはしない。事業者の表示とみなされ、景表法・表示規約の問題が直接生じうる（仮説）。

### C-3. 住宅ローンなど金融商品の広告
- [ ] 金利を表示する場合は、優遇金利の**適用条件**を、強調した金利と著しく異ならない大きさで明瞭に書く。消費者庁は自動車ローンのFAQで同様の考え方を示している（[aftc.or.jp PDF](https://www.aftc.or.jp/content/files/am/kiyaku/kokokuFaq/used/10/used_10_005.pdf)）。住宅ローンへの直接の適用は**未確認**。
- [ ] 「最安」「No.1」等の最上級表現は使わない。使う場合は根拠と調査時点を示す。銀行業の公正競争規約の該当条文は**未確認**。
- [ ] 媒介に当たらない範囲にとどめる。サイトは広告リンクの掲載のみとし、個別の融資の勧誘、条件の説明、申込書の記載補助などはしない。銀行代理業・金融サービス仲介業・貸金業の「媒介」にあたると登録が必要になる。金融庁は2026-07-30に「媒介と媒介に至らない行為」の線引きに関する監督指針の改正案を公表している（[金融庁](https://www.fsa.go.jp/news/r8/sonota/20260730-2/20260730-2.html)、[三宅法律事務所 解説PDF](https://www.miyake.gr.jp/wp-content/uploads/2026/08/金融規制ニュース_媒介と媒介に至らない行為の境界線_監督指針改正案_銀行代理業関係等_令和8年8月1日.pdf)）。**アフィリエイトへの適用の結論は未確認**で、改正案の本文確認が必要。
- [ ] 2022-06-29に改定された「アフィリエイト広告等に関する管理措置指針」により、広告主がアフィリエイターを管理する責任が強まった。ASP経由で表現の修正を求められたら従う（[businesslawyers.jp](https://www.businesslawyers.jp/articles/1200)）。

### C-4. 宅建業法（仲介・購入相談の送客）
- [ ] 不動産会社に顧客を紹介して報酬を受ける場合は、宅建業法2条2号の「媒介」にあたらないよう注意する（あっせんや契約成立への尽力をしない）。無免許営業は禁止されている（12条）（[atsoho.com](https://atsoho.com/blog/real-estate-referral-fee-legality)、[国交省PDF](https://www.mlit.go.jp/sogoseisaku/point/content/001767937.pdf)）。ASPを通した広告リンクの掲載にとどめるのが安全（仮説）。

### C-5. データ出典の表示
- [ ] 国交省の不動産情報ライブラリAPIの利用規約（クレジット表示、商用利用の可否）を本文で確認する。APIが無償公開であることは国交省の報道資料で確認できた（[国交省](https://www.mlit.go.jp/report/press/content/001726227.pdf)）。**規約本文は未確認**。

### C-6. 有料プラン化する場合（将来）
- [ ] 特定商取引法に基づく表記（事業者名、住所、電話番号、価格、支払時期・方法、提供時期、解約条件など）を掲載する。
- [ ] 2022-06-01施行の改正特商法により、申込み直前の**最終確認画面**で、分量・価格・支払時期と方法・提供時期・申込期間・解約に関する事項を表示する義務がある。誤認させる表示は禁止で、消費者に取消権が生じうる（[netshop.impress.co.jp](https://netshop.impress.co.jp/node/9750)、[sogyotecho.jp](https://sogyotecho.jp/tokuteishoutorihikihou-ec/)）。
- [ ] 有料プランの宣伝文句（「プロ版なら精度◯%」等）は、根拠がないと景表法の優良誤認になる。

---

## (D) Streamlit上の制約と回避策

| 制約 | 内容 | 出典 | 回避策 |
|---|---|---|---|
| **規約（商用利用）** | 現行規約: 個人情報を扱う場合は個人的・非商用目的に限る。旧規約1.4(d): 商用目的の利用を禁止（スタッフの説明）。2025-11-17に規約を一本化。 | [terms-of-use](https://streamlit.io/terms-of-use)、[forum](https://discuss.streamlit.io/t/streamlit-soc2-documentation/57942)、[告知](https://discuss.streamlit.io/t/updates-to-terms-of-use-and-privacy-notices/120100) | 収益導線は静的LPへ切り離す。アプリ内のアフィリエイトは最小限にするか、LPへのリンクのみにする。将来本格的に収益化するなら、別ホスティングへの移行を検討する（有料になる可能性あり）。**現行条文の本文確認が必須**。 |
| **AdSense** | streamlit.appのURLを入力すると「有効なトップレベルドメインではない」と警告されたという報告。Streamlit側の回答者は、Community Cloud以外でのホスティングを推奨。AdSenseが登録を受け付けるのはドメインと、公開サフィックスリスト（PSL）に載ったプラットフォーム上のサブドメイン等に限られる。 | [forum 36157](https://discuss.streamlit.io/t/google-adsense-doesnt-accept-streamlit-app-url/36157)、[AdSense Help](https://support.google.com/adsense/answer/12170421?hl=en-AU)、[onamae.com](https://www.onamae.com/column/adsense/24/) | AdSenseはLP側で申請する。`pages.dev` サブドメインが審査対象になるかは**未確認**（PSL掲載の有無を要確認）。確実なのは独自ドメインだが、有料のため今回の前提外。`components.html` による埋め込みで広告を表示したという報告もあるが、規約・ポリシー上のリスクがあり非推奨（仮説）。 |
| **SEO** | 公開アプリは週次で自動クロールされる。メタタイトルは `st.set_page_config(page_title=...)` で設定し、冒頭の `st.header`／`st.text` がメタディスクリプションに使われうる。インデックスまで1か月以上かかった例や、「You need to enable JavaScript」画面だけが読まれる問題が報告されている。Search Consoleでの所有権確認が難しい。 | [docs: indexability](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app/indexability)、[forum 121310](https://discuss.streamlit.io/t/continued-lack-of-search-engine-indexing/121310)、[forum 37516](https://discuss.streamlit.io/t/you-need-to-enable-javascript-to-run-this-app/37516) | ①`page_title` とアプリ冒頭の説明文を整える（無料、即日） ②静的LP（HTML）で検索流入を受け、アプリへ誘導する ③LPならSearch Consoleで所有権確認ができる。 |
| **スリープ** | 12時間アクセスがないとスリープする（以前は7日）。初回アクセス時に起動待ちが発生する。 | [docs: manage your app](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app)、[forum](https://discuss.streamlit.io/t/web-apps-keeps-on-sleeping-after-30-minutes-or-a-day-of-inactivity/97350) | 起動待ちの間に離脱しても、LPに「起動に数十秒かかる」と案内を置けば影響を抑えられる（仮説）。 |
| **リソース** | CPU 0.078〜2コア、メモリ690MB〜2.7GB（2024年2月時点の記載。予告なく変わりうる）。 | [docs: status](https://docs.streamlit.io/deploy/streamlit-community-cloud/status) | OCRが重い場合はキャッシュを使う。 |
| **独自ドメイン** | Community Cloudは非対応とする第三者情報あり（公式の記載は**未確認**）。 | [livemy.app](https://livemy.app/blog/deploy-streamlit-app) | LP側でブランドを確立する。 |

**推奨構成（無料の範囲）**
```
検索・SNS → 静的LP（Cloudflare Pages: xxx.pages.dev）
              ├ 使い方／参考価格の読み方／購入チェックリスト（解説記事）
              ├ PR表記つきアフィリエイト導線（火災保険・ローン・引越し・リフォーム）
              └ 「無料で判定する」→ okaidokucyekka.streamlit.app
アプリ → 判定結果の下に「次にやること（LPへ）」の1行リンクのみ
```
Cloudflare Pagesの無料プラン: 月500ビルド（アカウント全体）、同時ビルド1、ビルドは20分でタイムアウト、静的配信の帯域は無制限（第三者情報）。[公式 limits](https://developers.cloudflare.com/pages/platform/limits)、[community](https://community.cloudflare.com/t/cloudflare-pages-limits-free-plan/431961)。代替として GitHub Pages も候補だが、今回は**未調査**。

---

## (E) 未確認事項（次に確認すべきこと）

1. **Streamlit現行利用規約の条文**: 非商用条項の正確な文言と、広告・アフィリエイトの扱い。最優先。
2. **各ASPの報酬額と成果条件**: A8.net・もしも・バリューコマース・アクセストレード・afbの住宅ローン／火災保険／引越し／リフォーム／一括査定案件。管理画面にログインして確認する必要がある。現在提携中のA8火災保険案件の単価・条件も、このレポートでは未確認。
3. **住宅ローン案件の有無と単価**（モゲチェック、住宅本舗、SUUMO一括ローン相談など）。
4. **ホームインスペクション案件**: ASPでの取扱いが見つからなかった。事業者に直接提携できるかも未確認。
5. **中古住宅の購入相談・仲介への送客案件**: 案件の存在と、宅建業法上の扱い。
6. 「お買い得」が表示規約の特定用語にあたるか（所管の公正取引協議会に確認）。
7. 金融庁の監督指針改正案（2026-07-30公表）が、アフィリエイトの住宅ローン紹介に与える影響。
8. 国交省 不動産情報ライブラリAPIの利用規約（クレジット表示、商用利用）。
9. `pages.dev` サブドメインでAdSenseを申請できるか（PSL掲載の有無とAdSenseの運用）。
10. Stripe Billing（サブスク）の公式手数料と、個人事業主での利用条件。3.6%は比較サイトの情報。
11. もしもアフィリエイトとafbの登録審査基準。
12. 本レポートの数字は、検索結果の抜粋から拾ったものでページ本文は未読。採用前に出典ページを直接開いて再確認すること。
