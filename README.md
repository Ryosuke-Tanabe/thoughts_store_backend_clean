# thoughts_store_backend

思想・アイデアを Google Drive に NDJSON で記録し、ハッシュチェーンで改ざん検知するバックエンドシステム。

## 概要

- **SSOT（Single Source of Truth）**: `journal_by_day/YYYY/MM/YYYY-MM-DD.ndjson` がすべての正本。インデックスや memory_map はそこから全再構築できる派生物。
- **ハッシュチェーン**: 各レコードに `prev_hash → hash`（SHA256）を連鎖させ、改ざん・欠損を検知。
- **Gate（原子書き込み）**: SSOT への書き込みはすべて `ssot/gate.py` 経由。スキーマ検証 → tempfile → `os.replace` の順で原子的に確定する。
- **Google Drive 連携**: サービスアカウントで Drive v3 API を使い、クラウドに追記保存。
- **スレッドシステム**: `phase=start/update/end` のイベント列で思考の流れを記録。`thread_id` でグループ化。

## ファイル構成

```
thoughts_store_backend_clean/
├── src/thoughts_store/
│   ├── thought_store/thought_store.py   # Google Drive への NDJSON 保存
│   ├── ssot/
│   │   ├── gate.py                      # 原子書き込み & スキーマ検証
│   │   ├── safe_ndjson_reader.py        # Fail-Fast NDJSON リーダー
│   │   ├── build_memory_map_from_events.py
│   │   ├── generate_memory_map.py
│   │   ├── generate_open_threads.py
│   │   └── iter_events.py
│   ├── cli/
│   │   ├── start_thread.py              # スレッド開始ログ生成
│   │   ├── update_thread.py             # スレッド更新ログ生成
│   │   ├── end_thread.py                # スレッド終了ログ & インデックス反映
│   │   ├── save_thread.py               # スレッドを NDJSON に保存
│   │   └── thoughts.py                  # thought の add / verify / tail CLI
│   ├── models/thought.py                # Thought データクラス
│   └── bridge/main_bridge.py            # 外部ツール連携ブリッジ
├── run_official_save.py                 # 正式保存フロー（Drive + memory_map）
├── update_memory_map.py                 # memory_map.md 更新スクリプト
├── requirements.txt
├── .env.example
└── .gitignore
```

## セットアップ

### 1. 依存インストール

```bash
pip install -r requirements.txt
# Google Drive 連携を使う場合
pip install google-api-python-client google-auth
```

### 2. 環境変数を設定

`.env.example` をコピーして `.env` を作成し、値を埋める。

```bash
cp .env.example .env
```

| 変数 | 説明 | 必須 |
|------|------|------|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | サービスアカウント JSON のパス（または JSON 文字列） | Drive 使用時 |
| `GOOGLE_DRIVE_ROOT_ID` | Drive のルートフォルダ ID | Drive 使用時 |
| `JOURNAL_BASE` | `journal_by_day/` のベースパス | 任意 |
| `LOGS_DIR` | ログ出力ディレクトリ | 任意 |
| `LOG_INDEX_PATH` | `log_index.md` のパス | 任意 |
| `MEMORY_MAP_MD` | `memory_map.md` のパス | 任意 |
| `TEMPLATES_DIR` | テンプレートディレクトリ | 任意 |
| `THREAD_OWNER` | スレッドのデフォルト所有者名 | 任意 |
| `THOUGHT_AUTHOR` | thought のデフォルト著者名 | 任意 |

### 3. Google Drive サービスアカウントの準備

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成
2. Drive API を有効化
3. サービスアカウントを作成し、JSON キーをダウンロード
4. 保存先の Drive フォルダをそのサービスアカウントと共有（編集者権限）
5. フォルダ ID を `GOOGLE_DRIVE_ROOT_ID` に設定

## 使い方

### thought を保存（Drive 連携）

```bash
python run_official_save.py \
  --content "今日気づいたこと" \
  --tags "insight,daily" \
  --author "your-name"
```

### スレッドを管理

```bash
# スレッド開始
python -m src.thoughts_store.cli.start_thread \
  --thread-id T0001 \
  --title "アイデアの整理"

# スレッド更新
python -m src.thoughts_store.cli.update_thread \
  --thread-id T0001 \
  --title "途中経過"

# スレッド終了
python -m src.thoughts_store.cli.end_thread \
  --thread-id T0001 \
  --title "アイデアの整理・完了" \
  --save
```

### thought CLI（ローカル NDJSON）

```bash
# 追記
python -m src.thoughts_store.cli.thoughts add \
  --id t_20260615_0001 \
  --text "今日の気づき" \
  --tags "daily"

# ハッシュチェーン検証
python -m src.thoughts_store.cli.thoughts verify

# 末尾5件を表示
python -m src.thoughts_store.cli.thoughts tail --n 5
```

### memory_map を再構築

```bash
python src/thoughts_store/ssot/build_memory_map_from_events.py \
  --journal-base journal_by_day \
  --output logs/memory_map.md
```

## SSOT の原則

- `journal_by_day/*.ndjson` が唯一の正本。直接編集しない。
- `memory_map.md`、`log_index.md` はすべて再構築可能な派生物。
- 書き込みは必ず `gate.py` の `write_events_atomic()` 経由で行う。

## ライセンス

MIT

## 設計思想について

このシステムを作る過程で得た気づきを記事にまとめています。

[記憶は保存するものじゃない——AI外部脳を作って失敗してわかったこと](https://note.com/moral_spirea2538/n/nda51308b710e)
