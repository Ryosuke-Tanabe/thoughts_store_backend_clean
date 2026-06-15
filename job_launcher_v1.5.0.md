# Job Launcher v1.5.0

---

## 0. はじめに（非互換宣言）
本書は、Job Launcher 運用仕様 **v1.5.0** を定義するものである。  
本仕様は、SSOT / Gate / Full Rebuild を前提とした **新世界線**に基づき策定されている。

### 非互換宣言
本仕様は **v1.4.x 系運用仕様と非互換**である。
- v1.4.x との併用は想定しない
- 移行手順は提供しない
- 旧仕様は参照用途としてのみ存続する
本書は、現行実装の事実を正として記述する。  
新たな運用ルールの追加や、既存挙動の再解釈は行わない。

---

## 1. 前提世界線（SSOT / Full Rebuild）

### 1.1 SSOT（Single Source of Truth）

SSOT とは、

**`journal_by_day/` 配下に保存される NDJSON イベント列**

を指す。

例：
journal_by_day/YYYY/MM/YYYY-MM-DD.ndjson

- SSOT は唯一の正（Truth）である。
- SSOT は append-only とする。
- SSOT 以外はすべて派生物とする。
- 以後、SSOT の既定ルートは thoughts\journal_by_day に固定する。

---

### 1.2 一次情報と派生物の分離
以下を厳密に分離する。
- 一次情報  
  - NDJSON イベント（SSOT）
- 派生物  
  - 索引
  - 集計
  - 可視化データ

派生物は正にならない。  
正は常に **SSOT にのみ存在**する。

---

### 1.3 Full Rebuild 原則
派生物（索引・マップ・キャッシュ）は差分更新しない。
- 差分パッチや逐次的な部分更新は行わない。
- 再生成は常に Full Rebuild とする。
- 運用上は「保存成功後に Full Rebuild を起動して再生成する」ことを許容する。
- 生成物は破損時にいつでも再構築可能でなければならない。

---

## 2. Job Launcher の責務と境界

### 2.1 Job Launcher の役割
Job Launcher は、以下を担う **実行ハブ**である。
- SSOT へのイベント保存処理の起点
- Gate を通過したイベントの確定
- 派生ジョブ（索引生成等）の起動

Job Launcher は **SSOT を直接書き換えない**。  
常に Gate を通じて処理を行う。

---

### 2.2 Job Launcher がやること
Job Launcher が行うのは、以下に限定される。
- 入力イベントの受領
- Gate への引き渡し
- Gate 通過後の処理起動
- 成否結果の通知

---

### 2.3 Job Launcher がやらないこと
Job Launcher は、以下を行わない。
- イベント内容の意味解釈
- スレッドの論理整合性判断
- 業務ルール・ポリシーの評価
- 不正データの修復・補正

これらは **Job Launcher の責務外**である。

---

### 2.4 責務境界の明確化
Job Launcher は以下の境界を持つ。
- **前段**  
  - 人間・AI によるイベント生成
- **中核**  
  - Gate による契約検証
- **後段**  
  - 索引・派生物の生成（Full Rebuild 前提）

この分離により、  
Job Launcher は **構造的に単純で壊れにくい存在**となる。

---

## 2.5 Schema Enforcement（Launcher 実装拘束）
本章は、Launcher 実装における Schema Enforcement の唯一の正規定義であり、
これに反する実装はすべて仕様違反とみなされる。

---

### 2.6 起動時 Schema ロード（必須）
- Job Launcher は起動時に、SSOT 用 JSON Schema を **必ずロード**する
- Schema のロードは、入力生成・入力受付・Preflight より **前段**で行われる
- Schema のロードに失敗した場合、Launcher は **即時エラーで停止**する
- Schema 未ロードのまま処理が継続する分岐は **存在してはならない**

---

### 2.7 Schema 適用の強制性
- Schema 適用の有無を切り替える設定・フラグ・環境変数は **存在しない**
- テスト・デバッグ目的で Schema を無効化する経路は **存在しない**
- Schema は **常に有効**であり、任意適用という概念は存在しない

---

### 2.8 入力生成経路（AI / 自動生成）
- AI または自動処理によって生成される入力は、  
  **Schema 制約下の構造を前提**として生成される
- Schema に適合しない生成結果は、  
  Gate に到達する前に **即時拒否**される
- Schema 不適合な入力を「とりあえず Gate に渡す」経路は存在しない

---

### 2.9 入力受付経路（人間入力 / Bridge）
- 人間によって貼り付けられた入力は、  
  Gate に渡される前に **必ず Schema 検証を受ける**
- Schema 不適合な入力は、  
  Gate に到達する前に **拒否される**
- Schema 検証を省略して Gate に渡す経路は存在しない

---

### 2.10 Gate との関係（拘束の重なり）
- Schema 検証と Gate（E1xxx エラー契約）は **両方必須**である
- Schema に適合していても、Gate 契約に違反した場合は保存されない
- Gate 契約を満たしていても、Schema に不適合な場合は保存されない
- SSOT への保存は、  
  **Schema 検証および Gate 契約の双方を満たした場合にのみ成立**する

---

### 2.11 テスト・検証経路
- テストコード・検証コードにおいても、  
  Schema は **常に適用される**
- テストベクタは、  
  Schema 検証が正しく機能していることを確認する目的に限定される
- テスト目的で Schema を回避する実装は認められない

---

### 2.12 実装違反の扱い
以下のいずれかが存在する場合、  
当該実装は **本仕様および SSOT/README.md に違反する**。
- Schema をロードしない実行経路
- Schema 適用を任意化する設定・分岐
- Schema 検証を経ずに Gate に入力を渡す処理
- Gate のみで保存を成立させる処理

---

### 2.13 本章の位置づけ
- 本章は **実装詳細を規定しない**
- 本章は **実装結果として満たすべき条件を規定する**
- 実装方法は自由だが、結果は拘束される

---

### 2.14 索引優先原則（Index-First Principle）
参照および検索は必ず  
**indexes 配下の索引から開始する。**
SSOT は直接探索の対象とはならない。  
索引から取得した `source={file,line}` により  
SSOT のイベントへ復帰して参照する。

---

### 2.15 タグ選定指針（Deep Tagging & Canonicalization）
Launcher は、record.tags の生成または補助において、単なる表面的分類ではなく、
後続の検索・再利用・知識接続に資するタグ付けを推奨する。タグ選定は、以下の観点に従うことが望ましい。

#### 1.概念抽出（Thinking First）
- 入力テキストを読解し、管理上の分類（スレッドID等）を除いた、
　本質的な課題、具体的な成果物、確立された原則を優先して抽出する。
- Update、Migration 等の汎用的抽象語は避け、本文内の固有名詞、メソッド名、エラー名等の具体的名称を優先する。

#### 2.既存タグ参照（Canonical Search）
- 可能な場合、indexes/thought_map.json 等の既存タグセットを参照し、既存概念との重複を避ける。既存タグと実質的に同一　概念である場合、新規タグの乱立を避け、既存のタグ表記を優先することが望ましい。

#### 3.最終選定（Final Selection）
- record.tags は 3〜5個程度を推奨する。
- タグは意味的絞り込みに有効なものを優先し、広すぎる単語や管理専用語の過剰付与を避ける。
- SSOT、AI、NDJSON 等、システム全体の前提条件であり検索上の絞り込みに寄与しない語は、
　それ自体が主題である場合を除き、常用タグとしないことが望ましい。

# 3. 書き込み経路としての Gate

## 3.1 Gate の位置づけ
Gate は、Job Launcher における **SSOT 書き込みの唯一の入口**である。  
SSOT（thoughts\journal_by_day 配下の NDJSON イベント）に対する **あらゆる永続化操作は Gate を経由しなければならない**。

Gate は以下を目的として設計されている。
- SSOT の汚染防止
- イベント順序の保証
- 不正データの Fail-Fast 拒否
- 後続処理（索引・派生物生成）の安全性担保

Gate は **意味解釈・再解釈を行わない**。  
Gate が判断するのは **構造・形式・契約への適合性のみ**である。

---

## 3.2 Gate が保証するもの
Gate を通過したイベントについて、以下が保証される。
1. NDJSON として機械的に完全に解釈可能である  
2. SSOT 契約（E1xxx）に違反していない  
3. 後続の Full Rebuild において破壊的影響を与えない  

これにより、  
索引生成・履歴確定・分析・再構築といったすべての派生処理は  
**「Gate を通過した」という事実のみを信頼すればよい**。

---

## 3.3 Gate の判定基準（固定）
Gate は、SSOT への書き込みに際し、`safe_ndjson_reader.py` に定義された  
**E1xxx エラー契約（付録A）を唯一の判定基準として適用する。**

本文中の説明と付録Aに差異がある場合、**付録Aを正とする。**

この契約により、Gate の挙動は以下の性質を持つ。
- 実装と仕様の乖離を許さない  
- 将来の仕様変更は **コード → 付録A** の順で反映される  
- 本文は概念説明として安定し続ける  

---

## 3.4 Fail-Fast 原則
Gate は **Fail-Fast** を原則とする。
- NDJSON ファイル内に **1行でも** E1xxx 違反が存在した場合  
  → **即座に処理を停止**する  
- 部分的な保存・スキップ・補正は一切行わない  
- エラーは **位置（file / line_no）付き**で返される  

これは以下を防ぐためである。
- SSOT 内の「部分的に壊れた状態」
- 索引や派生物が壊れた前提で生成される事故
- 後続フェーズでの原因不明エラー

---

## 3.5 Gate が拒否する操作（概要）
Gate が拒否する代表的な操作には、以下が含まれる。
- NDJSON として成立しない入力
- 空行・複数 JSON 混入
- デバッグ痕跡や非イベント文字列の混入
- `record` / `record.type` の欠落
- `thread_event` における `record.thread` 欠落
  - 不正な phase  
  - 不正な date_local  

詳細な拒否条件は **付録A（E1xxx エラー契約一覧）**に完全に列挙される。

---

## 3.6 Gate を経由しない書き込みの扱い
以下の操作は **仕様上、成立しない**。
- Gate を経由せずに SSOT を直接編集する行為
- 外部ツールによる NDJSON の直接追記
- ローカルファイルの状態を  
  正否判定に用いる行為

これらは **Unsupported Operation** として扱われ、  
Job Launcher の運用対象外である。

---

## 3.7 Gate と Full Rebuild の関係

Gate は **Full Rebuild を成立させるための前段装置**である。
- Gate が保証するのは「イベントが壊れていない」ことのみ
- 派生物（memory_map / log_index 等）は  
  Gate 通過後に **常に再生成可能**であることを前提とする  

したがって、
- 派生物の欠損・不整合は **SSOT の破損を意味しない**
- 正の判定は常に  
  **Gate 通過済み NDJSON イベント**に対して行われる  

---

## 3.8 Gate の責務外事項

Gate は以下を行わない。
- イベント内容の意味的検証
- スレッドの論理的一貫性チェック
- 業務ルール・ポリシーの正当性判断
- 人間向けの補正・警告・修復

これらはすべて **Gate の外側の責務**である。

---

## 3.9 本章のまとめ
- Gate は **SSOT 書き込みの唯一の入口**
- 判定基準は **E1xxx エラー契約のみ**
- 1行でも違反があれば **Fail-Fast 停止**
- Gate を通過したイベントのみが  
  **Full Rebuild の入力として信頼される**

---

### 3.10 Thought Capture & Retrieval（スレッド外思想の保存と検索）
本節では、スレッドに属さない「思想（thought）」を SSOT（journal_by_day/*.ndjson）に安全かつ継続的に保存し、
後から確実に検索・再利用できるようにするための、Launcher の責務と振る舞いを定義する。

本機能の目的は、**人間が「脱線」や「未整理」を理由に記録を諦めることを防ぎ、  
あらゆる思考を知識資産として回収可能にすること**である。

---

### 3.10.1 thought レコードの位置づけ（設計原則）
- thought は **thread_event と並ぶ第一級の記録単位**である
- thought は **thread_id を持たない状態で保存されることを正式に許容**する
- スレッド中に発生した脱線的思考であっても、thread に紐づける義務はない

この設計により、
「今のスレッドとは関係ないが、失いたくない思考」を  
**文脈整理なしで即座に SSOT に刻み込める**ことを保証する。

---

### 3.10.2 thought 保存時の基本契約（Launcher の義務）
Launcher は thought 保存時に、以下の契約を必ず満たさなければならない。
- `record.type` は `"thought"` とする
- `record.thread` フィールドは **付与しない**（thread_id を継承しない）
- `record.text` は必須とする
- `record.tags` は **最低1つ以上必須**とする
- `record.tags` は **3〜5個程度を推奨（最大5）**とする

これにより、thread 文脈への誤吸着を構造的に防止する。

加えて、上記の拘束は SSOT 正本スキーマ（events_ndjson_line.schema.json）により実行時に強制される。
本文の説明とスキーマ定義が矛盾する場合、スキーマ定義を正とする。

---

### 3.10.3 Quick Capture（とりあえず保存）フロー
Launcher は、意味が未確定な思考を即座に保存するための
**Quick Capture（クイック・キャプチャ）**を提供しなければならない。

Quick Capture の要件は以下の通り。
- 入力は本文のみでも保存可能とする
- 保存時に Launcher が以下を自動付与する
  - tags: `Thought`, `Capture`, `NoThread`
  - title が空の場合は `(quick capture)` を自動設定
- 人間に「適切な分類」や「文脈整理」を要求しない

このフローは、
**保存を遅らせないことを最優先**とする。

---

### 3.10.4 保存後フィードバック（可視性の保証）
thought の保存が成功した場合、Launcher は以下を実行する。
- SSOT（NDJSON）を正として、派生ビューを Full Rebuild する
- `indexes/thought_map.json` 及び`indexes/log_index.md`を再生成する
- 再生成結果の一部を UI / CLI 上に表示し、
  「正しく保存された」ことを人間が視覚的に確認できるようにする

これにより、保存結果に対する不信感を防止する。

---

### 3.10.5 検索対象
- 対象は thoughts/journal_by_day/**/*.ndjson の全 record とする。
- thread_id に依存しない全文検索を可能とする。
- 主検索対象は record.text とする。
- 階層（YYYY/MM）を前提に再帰走査する。

---

### 3.10.6 本節の Done 条件（受け入れテスト）
以下をすべて満たした場合、本節の要件は完了とみなす。
- スレッド進行中に脱線した内容を thought として保存できる
- 保存された thought に thread_id が付与されていない
- 保存直後に `thoughts_no_thread.md` に反映される
- thread_id を指定しなくてもキーワード検索で該当 thought がヒットする
- 検索結果を AI に貼り付けて再利用できる

これらを満たす限り、内部実装の詳細は問わない。

---

## 4. イベントモデル
本章では、SSOT を構成する **NDJSON イベントのモデル**を定義する。  
ここで扱う内容は、Job Launcher が **事実として前提にしている構造**であり、  
意味解釈や業務的妥当性には踏み込まない。

---

### 4.1 NDJSON イベントの基本原則
SSOT は、NDJSON（Newline Delimited JSON）形式のイベント列として構成される。

NDJSON イベントは、以下の原則に従う。
- **1行 = 1イベント**
- 各行は **単一の JSON object** である
- 複数イベントを1行に含めてはならない
- 空行は許可されない

これらの原則に違反する入力は、Gate により **Fail-Fast で拒否される**。

---

### 4.2 イベントの識別単位
SSOT における最小の永続化単位は **イベント1件**である。
- イベントは行番号によって識別される
- イベント間の意味的な関係性は  
  SSOT 自体には保持されない
- 関係性の解釈は **派生処理側の責務**である

SSOT は「出来事の列」であり、  
「状態」や「構造」を直接表現するものではない。

---

### 4.3 イベント共通構造
すべてのイベントは、最上位に `record` フィールドを持つ。
```json
{
  "record": {
    ...
  }
}
```
record は必須であり、
存在しない、または object でない場合、Gate により拒否される。

---

### 4.4 record.type
record.type は、イベントの種別を表す。
record.type は 必須
文字列でなければならない
空文字は許可されない
現行実装において、
Gate が受理する record.type は以下のみである。

thread_event
thought

未知の record.type は、
Gate により拒否される。

---

### 4.5 thread_event
thread_event は、
スレッド運用（Start / Update / End）を表すイベントである。

record.type = "thread_event" の場合、
record.thread フィールドが必須となる。

---

### 4.6 record.thread
record.thread は、
thread_event に関する最小限の識別情報を保持する object である。

"thread": {
  "thread_id": "T0123",
  "phase": "start",
  "date_local": "2026-01-23"
}

record.thread が存在しない、
または object でない場合、Gate により拒否される。

---

### 4.7 thread_id
thread.thread_id は、
スレッドを一意に識別する文字列である。
必須
空文字は許可されない

命名規則や意味的整合性はGate の責務外とする。

### 4.8 phase

thread.phase は、
スレッド内でのイベントの位置づけを表す。

許可される値は以下のみである。
start
update
end

これ以外の値が指定された場合、
Gate により拒否される。

---

### 4.9 end フェーズの特別な意味
phase = "end" のイベントは、
スレッドの クローズを示す特別なイベントである。
索引生成のトリガーとなる
スレッド履歴確定の基準点となる

この意味付けは 派生処理側の責務であり、
Gate は phase の妥当性のみを検証する。

---

### 4.10 date_local
thread.date_local は、
イベントが属する ローカル日付を表す。
形式は YYYY-MM-DD

実在しない日付は許可されない

形式または値が不正な場合、
Gate により拒否される。

---

### 4.11 イベントモデルの非責務事項
イベントモデルは、以下を保証しない。
start / update / end の順序正当性
start や end の存在数
スレッドの論理的一貫性
業務的な正しさ

これらはすべて イベントモデルの外側で扱われる。

---

### 4.12 拒否条件の所在
本章で述べた各種拒否条件の 完全な一覧は、
付録A「E1xxx エラー契約一覧」に定義される。

本文と付録Aに差異がある場合、
付録Aを正とする。

---

### 4.13 本章のまとめ
SSOT は NDJSON イベント列で構成される
1行 = 1イベントが最小単位である
record.type = thread_event / thought が現行の受理対象
Gate は構造のみを検証し、意味を解釈しない

---

## 5. 運用フロー（事実ベース）

本章では、Job Launcher v1.5.0 における  
**実際の運用フロー**を事実ベースで記述する。

ここに記載される内容は、  
「こう使うべき」という指針ではなく  
**「現にそう動いている」処理の流れ**である。

---

### 5.1 入力イベントの生成
Job Launcher に入力されるイベントは、  
人間または AI によって生成される。

- イベントは NDJSON 1行分の JSON object として生成される
- この時点では SSOT には未保存である
- 入力内容の意味的正当性は問われない

AI による生成を含む入力イベントは、Schema Preflight により必ず検疫される。
したがって、生成結果は Schema 制約下の構造を前提とし、
Schema 不適合な生成結果は入力として成立しない（Gate へ渡される前に拒否される）。

---

### 5.2 Preflight（事前チェック）

Gate に到達する前段として、  
入力イベントは **Preflight** を通過する。

Preflight は以下を目的とする。

- 明らかに壊れた入力の早期排除
- 保存事故（空行・複数 JSON 等）の防止

Preflight において確認される内容は、  
Gate の検証項目と **重複してもよい**。

Preflight は、NDJSON としての事故防止に加えて、
Schema Preflight（JSON Schema 検証）を含む検疫工程として運用される。

Schema 不適合な入力は Gate に到達させず、Preflight 段階で Fail-Fast に拒否される。

---

### 5.2.1 Schema Preflight（スキーマ検疫）
Preflight の一部として、入力イベントは **Schema Preflight** を通過する。

Schema Preflight は以下を目的とする。
- SSOT 用 JSON Schema による **構造制約の強制**
- 「Schema 不適合な入力を Gate に到達させない」こと（検疫義務）
- 「Schema の存在＝Schema の執行」を実行経路として固定すること

Schema Preflight における扱いは以下で固定する。
- Job Launcher は起動時に SSOT 用 JSON Schema を **必ずロード**する  
  （Schema 未ロードの実行経路は存在しない）
- 入力イベント（人間入力 / AI生成 / 自動生成を含む）は、Gate に渡す前に **必ず Schema 検証**を受ける
- Schema 不適合な入力は **Gate に渡さず即時拒否**する（Fail-Fast）
- SSOT への保存成立条件は **Schema 検証および Gate 契約（E1xxx）の双方を満たすこと**である  
  （Schema のみ OK / Gate のみ OK の片方成立は存在しない）

本節は `SSOT/README.md 3.2 Schema Enforcement` に従属し、本文と差異がある場合は SSOT/README を正とする。

---

### 5.3 Gate による検証

Preflight を通過したイベントは Gate に渡される。

Gate は以下を行う。

- NDJSON としての成立性検証
- E1xxx エラー契約に基づく構造検証
- Fail-Fast による即時拒否

Gate は **意味解釈を一切行わない**。

---

### 5.4 保存の確定

Gate を通過したイベントのみが  
SSOT（journal_by_day 配下）に保存される。

- 保存は追記のみで行われる
- 既存イベントの修正・削除は行わない
- 保存結果は Drive 側を正とする

---

### 5.5 派生ジョブの起動

SSOT 保存成功後、派生ジョブ（Index / Map 生成）を起動する。

#### 5.5.1 保存＝即時 Full Rebuild

- Bridge による保存成功後、Anchor を実行する。
- Anchor は SSOT を全走査し、Full Rebuild を実行する。
- 差分更新は行わない。

#### 5.5.2 indexes 出力先（固定）

Full Rebuild の生成物は以下に出力する：

indexes/

生成物：
- locator.jsonl
- thread_map.json
- thought_map.json
- log_index.md

これらはすべて派生物であり、正ではない。

旧生成物は以下に退避する：

indexes/old\

破損時は Full Rebuild により再生成する。

---

### 5.6 成否判定基準

Job Launcher における成否判定は、  
以下の基準で行われる。

- Gate を通過し、SSOT に保存されたか
- Drive 側で file_id が確定したか

ローカル同期状態や  
ファイルの可視性は判定基準に含めない。

---

### 5.7 失敗時の扱い

Gate で拒否されたイベントは、  
SSOT に **一切影響を与えない**。

- 部分保存は行われない
- 巻き戻し処理は不要
- 再試行は入力側の責務とする

---

#### 5.7.1 エラー表示の原則（表示・誘導）
失敗時の表示は、原因を以下の二系統に分類して返す。
- Schema Error（Schema Preflight による拒否）  
  - 入力は Gate に到達していない
  - 対処は「Schema に適合する JSON を 1 行で再生成すること」
- Gate Error（E1xxx エラー契約による拒否）  
  - 入力は Gate に到達したが契約違反
  - 対処は「エラーコード（E1xxx）と位置情報（file/line_no）に従い修正して再実行すること」

いずれの場合も Fail-Fast とし、部分保存・補正・スキップは行わない。

---

## 6. 索引と参照構造

本章では、SSOT から生成される  
**索引および参照用データ**の位置づけを定義する。

---

### 6.1 索引の役割
索引は以下を目的として生成される。
- 人間による俯瞰
- スレッドや成果物の参照性向上
- 後続処理の補助
索引自体は **正ではない**。

---

### 6.2 memory_map.md
memory_map.md は、  
思想・スレッド・成果物の関係を俯瞰するための  
参照用ドキュメントである。
- SSOT から再生成可能
- 欠損・不整合は SSOT の破損を意味しない

---

### 6.3 log_index.md
log_index.md は、  
スレッド単位の履歴を一覧するための索引である。
- phase=end イベントを基準に生成される
- 再生成可能であり、正にはならない

---

### 6.4 索引の非正性
以下はいずれも **正ではない**。
- memory_map.md
- log_index.md
- 派生ビュー
- 集計データ
正は常に **SSOT の NDJSON イベント列**である。

---

### 6.5 Full Rebuild との関係
索引は Full Rebuild により生成される。
- 差分更新は行わない
- 生成失敗は致命的ではない
- 再実行により回復可能である

---

## 6.6 Engine 生成物（機械の地図）
Full Rebuild により、indexes 配下に以下を生成する。

### locator.jsonl
Record Locator（イベント座標索引）
保持情報：
- id
- type
- tags
- text_head
- source={file,line}
`source={file,line}` は SSOT 内のイベントを参照する  
**Record Coordinate（イベント座標）**である。
この座標は SSOT 内のイベントを  
物理的に特定するための参照情報である。
`source.line` は **Full Rebuild 実行時点の物理座標**である。
この座標は **安定IDではない**。
SSOT の再整形や再生成により変化する可能性がある。  
そのため indexes は Full Rebuild により再生成される。

---

### thread_map.json
縦の地図（進行管理）
- thread 単位でイベントを集約
- start / update / end を含む
- スレッドの進行文脈を提供する

---

### thought_map.json
横の地図（思想結合）
- thought ノード
- edges（shared_tag 等）
思想やメモの関連関係を保持する。

---

### log_index.md
人間および AI が閲覧する **View 層**である。
- スレッド履歴の俯瞰
- 参照性の向上

---

これらはすべて **派生物**であり、  
SSOT ではない。
すべての索引は
source = {file,line}
を通じて **SSOT のイベントへ復帰可能**でなければならない。

---

## 6.7 検索の位置づけ
検索は SSOT を直接変更しない参照操作である。

### 検索原則

- 検索は SSOT を正とする
- 検索は派生物（indexes 配下）を利用してよい
- 検索結果は必ず `source={file,line}` を通じて SSOT に戻れること
- 検索は必ず **indexes → SSOT 復帰** の順序で行う

### 6.7.1 検索ルートの選択
検索は対象に応じてルートを選択する。  
検索は単一路線ではなく、対象に応じて入口を変える。

---

#### Thread 検索（スレッドの目的・進行・成果）
log_index.md
↓
thread_map.json
↓
locator.jsonl
↓
SSOT（NDJSON）

---

#### Thought 検索（思想・メモ・洞察）
thought_map.json
↓
locator.jsonl
↓
SSOT（NDJSON）

---

#### Audit / 検証
SSOT（NDJSON）
↓
indexes 再生成（Full Rebuild）

---

### 検索の非責務
検索は以下を行わない。
- 意味解釈
- 業務判断
- SSOT 更新
検索は **参照操作のみ**を行う。

---

### 禁止事項
検索において以下を行ってはならない。
- 索引を確認せずに外部検索へ依存する
- SSOT に復帰できない結果を事実として扱う
- 検索結果をもとに意味解釈を行う

---

## 6.8 Retrieval Gate
検索を開始する際、AI は以下の手順に従う。

### Query Classification
まず質問の対象を分類する。
- THREAD  
  スレッドの目的・進行・成果を参照する場合
- THOUGHT  
  思想・メモ・洞察を探索する場合
- AUDIT  
  SSOT や索引の検証を行う場合

---

### Retrieval Entry Rule
検索は必ず **indexes 配下の索引から開始する。**
indexes
↓
source={file,line}
↓
SSOT
SSOT は検索の入口として直接使用してはならない。
検索は必ず indexes を経由し、
`source={file,line}` により SSOT のイベントへ復帰して参照する。

外部検索（Drive / grep 等）は  
**索引破損または欠損時のみ許可される。**

---

### 検索ルート

#### Thread 検索
log_index.md
↓
thread_map.json
↓
locator.jsonl
↓
SSOT

#### Thought 検索
thought_map.json
↓
locator.jsonl
↓
SSOT

#### Audit
SSOT
↓
Full Rebuild

## 7. Legacy の扱い

### 7.1 v1.4.x 資産の位置づけ

v1.4.x 系で生成された以下の資産は、  
**参照用途としてのみ存続**する。

- 個別 start/update/end ログ（.md）
- 各種テンプレート

---

### 7.2 本仕様との関係

- v1.5.0 は v1.4.x と非互換である
- Legacy 資産を v1.5.0 運用に再利用しない
- 混在運用は行わない

---

## 付録A. E1xxx エラー契約一覧（Gate 拒否条件）

本付録は、`safe_ndjson_reader.py` に実装された  
**E1xxx エラー契約の正本**である。

Gate による保存拒否条件は、  
本付録に列挙された契約に完全に準拠する。

---

### A.1 NDJSON 構文・入力レベル（E1100–E1106）

- E1100: NDJSON_DECODE_ERROR  
- E1101: NDJSON_EMPTY_LINE  
- E1102: NDJSON_NOT_OBJECT  
- E1103: NDJSON_JSON_DECODE_ERROR  
- E1104: NDJSON_EXTRA_DATA  
- E1105: NDJSON_FORBIDDEN_TOKEN  
- E1106: NDJSON_FORBIDDEN_ELLIPSIS  

---

### A.2 record / event 最小要件（E1110–E1119）

- E1110: EVENT_MISSING_RECORD  
- E1111: EVENT_RECORD_NOT_OBJECT  
- E1112: EVENT_THREAD_NOT_OBJECT  
- E1113: EVENT_THREAD_ID_MISSING  
- E1114: EVENT_PHASE_INVALID  
- E1115: EVENT_DATE_LOCAL_INVALID  
- E1116: EVENT_TYPE_MISSING  
- E1117: EVENT_TYPE_UNKNOWN  
- E1118: EVENT_THREAD_MISSING  

---

（本付録の内容は実装と1:1で対応しており、  
本文よりも優先される）