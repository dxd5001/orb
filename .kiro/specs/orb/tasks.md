# 実装計画: Obsidian RAG Chatbot

## 概要

本実装計画は、requirements.md と design.md に基づき、ソロ開発者MVPとして現実的な粒度でタスクを定義する。
アーキテクチャ層の依存関係順（基盤 → Ingestion → Indexing → Retrieval → Generation → Interface → Docker）に沿って実装を進める。

## タスク

- [ ] 1. プロジェクト基盤のセットアップ
  - [ ] 1.1 ディレクトリ構成と`requirements.txt`を作成する
    - `backend/`, `frontend/`, `tests/` ディレクトリを作成する
    - `backend/requirements.txt` に依存ライブラリ（fastapi, uvicorn, chromadb, sentence-transformers, langchain, python-dotenv, keyring, hypothesis, pytest 等）を記載する
    - `.env.example` を作成し、全設定項目のテンプレートを記載する
    - `.gitignore` を作成し、`.env`・`__pycache__`・`chroma_db/` 等を除外する
    - _Requirements: 1.4, 1.7_

  - [ ] 1.2 `ConfigManager`（`backend/config.py`）を実装する
    - `python-dotenv` で `.env` を読み込む `ConfigManager` クラスを実装する
    - 必須設定項目（`VAULT_PATH`, `LLM_PROVIDER`, `LLM_MODEL`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `VECTOR_STORE_PATH`）の存在チェックと、未設定項目を列挙するバリデーション関数 `validate_config` を実装する
    - `USE_KEYRING=true` の場合に `keyring` ライブラリ経由でAPIキーを取得・保存する `get_api_key` / `set_api_key` メソッドを実装する
    - Vaultパスが存在するディレクトリかどうかを検証する `validate_vault_path` 関数を実装する
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [ ]\* 1.3 `ConfigManager` のプロパティテストを書く（hypothesis）
    - **Property 1: Vaultパスバリデーション** — 任意のパス文字列に対して `validate_vault_path` が存在するディレクトリのみを有効と判定することを検証する
    - **Property 2: 設定バリデーションの完全性** — 任意の設定項目の組み合わせに対して `validate_config` が未設定の必須項目をすべて列挙することを検証する
    - **Validates: Requirements 1.2, 1.3, 1.8**

  - [ ] 1.4 データモデル（`backend/models.py`）を実装する
    - `NoteDocument`, `Chunk`, `Scope`, `ChatRequest`, `ChatTurn`, `Citation`, `ChatResponse`, `IngestResult`, `IndexResult` を定義する
    - Pydantic `BaseModel` と `@dataclass` を設計書の定義に従って実装する
    - _Requirements: 2.2, 3.1, 5.1, 5.3, 8.2, 8.3_

- [ ] 2. Source Ingestion Layer（`ObsidianIngestor`）の実装
  - [ ] 2.1 `BaseIngestor` 抽象クラス（`backend/ingestion/base.py`）を実装する
    - `ingest(source_path: str) -> IngestResult` の抽象メソッドを定義する
    - _Requirements: 2.6_

  - [ ] 2.2 `ObsidianIngestor`（`backend/ingestion/obsidian.py`）を実装する
    - Vault配下の `.md` ファイルを再帰的に探索して読み込む
    - `python-frontmatter` または正規表現で Frontmatter を解析・分離し、`body` と `frontmatter` を独立して保持する
    - `title`（Frontmatterの `title` フィールド、なければファイル名）、`tags`、`last_modified` を抽出する
    - 個別ファイルの読み込み失敗時はログに記録して処理を継続し、`IngestResult.skipped_count` をインクリメントする
    - 処理完了時に総数・スキップ数をログ出力する
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]\* 2.3 `ObsidianIngestor` のプロパティテストを書く（hypothesis）
    - **Property 3: Ingestorのファイル探索完全性** — 任意のディレクトリ構造に対して返される `NoteDocument` リストがすべての `.md` ファイルに対応し、非 `.md` ファイルを含まないことを検証する
    - **Property 4: Frontmatterメタデータ抽出と分離** — 任意の Frontmatter と本文を持つ Markdown に対して `frontmatter` と `body` が正しく分離され、分離の可逆性が保たれることを検証する
    - **Property 5: エラー耐性と処理継続** — 有効・無効ファイルが混在する Vault に対して有効ファイルがすべて処理され、`total_count + skipped_count` が入力ファイル総数と等しいことを検証する
    - **Validates: Requirements 2.1, 2.4, 2.5**

- [ ] 3. Indexing Layer（`EmbeddingBackend` + `Indexer`）の実装
  - [ ] 3.1 `EmbeddingBackend` 抽象クラスと実装（`backend/embedding/`）を作成する
    - `EmbeddingBackend` 抽象クラス（`base.py`）に `embed(texts: List[str]) -> List[List[float]]` を定義する
    - `LocalEmbeddingBackend`（`local.py`）を `sentence-transformers` を使って実装する
    - `OpenAIEmbeddingBackend`（`openai_backend.py`）を OpenAI Embeddings API を使って実装する
    - `ConfigManager` の設定値に基づいてバックエンドを選択するファクトリ関数を実装する
    - _Requirements: 4.4, 4.6_

  - [ ] 3.2 `Indexer`（`backend/indexing/indexer.py`）を実装する
    - `IngestResult` を受け取り、テキストをチャンクサイズ1000文字・オーバーラップ200文字で分割する
    - `EmbeddingBackend.embed` を呼び出してベクトルを生成する
    - `Chunk` にメタデータ（`source_path`, `title`, `tags`, `frontmatter`, `last_modified`, `chunk_index`）を付与して ChromaDB へ upsert する
    - 再実行時は既存コレクションを削除して上書きする（冪等性）
    - 処理完了時に Note 数・Chunk 数をログ出力する
    - Vault ディレクトリが存在しない場合はエラーを出力して中断する
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]\* 3.3 `Indexer` のプロパティテストを書く（hypothesis）
    - **Property 6: チャンク分割サイズ制約** — 任意の長さのテキストに対して生成される全 Chunk のテキスト長が1000文字以下であり、隣接 Chunk 間のオーバーラップが200文字以下であることを検証する
    - **Property 7: メタデータ伝播ラウンドトリップ** — 任意の `NoteDocument` に対して生成される全 Chunk の `source_path`, `title`, `tags`, `frontmatter` が元の `NoteDocument` と一致することを検証する
    - **Property 8: インデックス化の冪等性** — 任意の Vault に対して `Indexer.index` を2回連続実行した後の Vector Store の状態が1回実行後と等しいことを検証する
    - **Property 13: チャンク分割の完全性** — 任意の本文テキストに対して生成される全 Chunk のテキストを結合した結果が元の本文テキストを包含することを検証する
    - **Property 14: Vector Storeラウンドトリップ** — 任意の Chunk を Vector Store に保存して取得した場合、取得した Chunk のテキストが保存前と一致することを検証する
    - **Validates: Requirements 3.1, 3.3, 3.6, 10.1, 10.2**

- [ ] 4. Retrieval Layer（`Retriever`）の実装
  - [ ] 4.1 `Retriever`（`backend/retrieval/retriever.py`）を実装する
    - `retrieve(query: str, scope: Optional[Scope], top_k: int = 5) -> List[Chunk]` を実装する
    - クエリを `EmbeddingBackend.embed` でベクトル化し、ChromaDB の `similarity_search` を呼び出す
    - `Scope.folder` が指定された場合は `metadata.source_path` のプレフィックスフィルタを適用する
    - `Scope.tags` が指定された場合は `metadata.tags` のフィルタを適用する
    - `Scope` が `None` の場合は Vault 全体を検索対象とする
    - _Requirements: 5.1, 6.1, 6.2, 6.3_

  - [ ]\* 4.2 `Retriever` のプロパティテストを書く（hypothesis）
    - **Property 9: 検索結果数の制約** — 任意のクエリと Vector Store の状態に対して `Retriever.retrieve` が返す Chunk リストの長さが `top_k` 以下であることを検証する
    - **Property 12: スコープフィルタの正確性** — 任意の `Scope` に対して返される全 Chunk が指定フォルダパスで始まる `source_path` を持つ（フォルダスコープ）、または指定タグをすべて含む（タグスコープ）ことを検証する
    - **Validates: Requirements 5.1, 6.1, 6.2**

- [ ] 5. Generation Layer（`LLMBackend` + `Generator`）の実装
  - [ ] 5.1 `LLMBackend` 抽象クラスと実装（`backend/llm/`）を作成する
    - `LLMBackend` 抽象クラス（`base.py`）に `generate(prompt: str) -> str` を定義する
    - `LocalLLMBackend`（`local.py`）を OpenAI 互換ローカル API（Ollama、LM Studio 等）を使って実装する
    - `OpenAILLMBackend`（`openai_backend.py`）を OpenAI API を使って実装する
    - LLM 接続失敗時は例外をキャッチしてエラー内容を含む例外を再 raise する
    - `ConfigManager` の設定値に基づいてバックエンドを選択するファクトリ関数を実装する
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6_

  - [ ] 5.2 `Generator`（`backend/generation/generator.py`）を実装する
    - `generate(query, chunks, history) -> ChatResponse` を実装する
    - 取得した Chunk をコンテキストとして、会話履歴（最大5ターン）とともにプロンプトを構築する
    - `LLMBackend.generate` を呼び出して回答テキストを生成する
    - 各 Chunk から `Citation`（`file_path`, `title`, `snippet`）を生成して `ChatResponse.citations` に含める
    - Vault に関連情報がない場合（Chunk が空）は「Vaultに関連する情報が見つかりませんでした」を返す
    - _Requirements: 5.2, 5.3, 5.4, 5.7_

  - [ ]\* 5.3 `Generator` のプロパティテストを書く（hypothesis）
    - **Property 10: Citation生成の完全性** — 任意の Chunk リストに対して `Generator.generate` が返す `citations` の各 `file_path` が対応する `Chunk.source_path` と一致し、`snippet` が `Chunk.text` の部分文字列であることを検証する
    - **Property 11: 会話履歴の制限** — 任意の長さの会話履歴に対して LLM に渡すプロンプトに含まれる会話ターン数が最大5ターンであることを検証する
    - **Validates: Requirements 5.3, 5.4**

- [ ] 6. チェックポイント — 全テストの通過確認
  - 全プロパティテストと例ベーステストが通過することを確認する。問題があればユーザーに確認する。

- [ ] 7. Interface Layer — FastAPI エンドポイントの実装
  - [ ] 7.1 FastAPI アプリケーションのエントリポイント（`backend/main.py`）を作成する
    - `ConfigManager` を初期化し、必須設定項目のバリデーションを実行する（未設定時はプロセスを終了する）
    - クラウド LLM バックエンドが設定されている場合は起動時に警告ログを出力する
    - デフォルトで `127.0.0.1` にバインドし、`API_PORT` 設定値でリッスンする
    - `frontend/` ディレクトリの静的ファイルを `/` で配信する
    - _Requirements: 1.8, 7.1, 7.6, 8.8, 9.2, 9.3, 9.4_

  - [ ] 7.2 `/api/chat` エンドポイント（`backend/routers/chat.py`）を実装する
    - `POST /api/chat` で `ChatRequest`（`query`, `scope?`, `history?`）を受け取る
    - `query` フィールドが存在しない場合は HTTP 400 を返す
    - Vector Store が空（未インデックス）の場合は「先にインデックス化を実行してください」を返す
    - `Retriever.retrieve` → `Generator.generate` の順で処理し、`ChatResponse` を返す
    - LLM 接続失敗時は HTTP 503 とエラー内容を返す
    - 内部エラー時は HTTP 500 を返す
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.5, 8.1, 8.2, 8.3, 8.6, 8.7_

  - [ ] 7.3 `/api/index` エンドポイント（`backend/routers/index.py`）を実装する
    - `POST /api/index` で `ObsidianIngestor.ingest` → `Indexer.index` を実行する
    - 処理結果（`status`, `notes`, `chunks`）を JSON で返す
    - Vault パスが存在しない場合は HTTP 400 を返す
    - _Requirements: 3.5, 8.4_

  - [ ] 7.4 `/api/status` エンドポイント（`backend/routers/status.py`）を実装する
    - `GET /api/status` で `index_status`, `total_notes`, `total_chunks`, `last_indexed`, `vector_store_path` を返す
    - _Requirements: 8.5_

  - [ ] 7.5 `/api/config` エンドポイント（`backend/routers/config.py`）を実装する
    - `GET /api/config` で現在の設定値（APIキー等の機密情報を除く）を返す
    - `PUT /api/config` で設定値を更新し、Vault パスの検証を行う
    - Vault パスが無効な場合は HTTP 400 を返す
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ]\* 7.6 API エンドポイントの例ベーステストを書く（pytest）
    - `query` フィールドなしのリクエストに対する HTTP 400 を検証する
    - 空の Vector Store に対するチャットリクエストのレスポンスを検証する
    - 無効な Vault パスに対する HTTP 400 を検証する
    - 内部エラー発生時の HTTP 500 を検証する
    - **Property 15: APIレスポンス形式の一貫性** — 任意の有効な `query` と `scope` を持つリクエストに対してレスポンスが `answer`（非空文字列）と `citations`（リスト）を含むことを検証する
    - **Validates: Requirements 8.1, 8.6, 8.7**

- [ ] 8. Interface Layer — Web UI の実装
  - [ ] 8.1 チャット画面（`frontend/index.html`, `frontend/app.js`, `frontend/style.css`）を実装する
    - チャット入力フォーム・会話履歴表示・Citation 表示（ファイルパス・タイトル・スニペット）を含む画面を実装する
    - `/api/chat` への fetch リクエストと、レスポンスの `answer` と `citations` の表示ロジックを実装する
    - フォルダパスまたはタグを Scope として指定できる UI コンポーネントを実装する
    - _Requirements: 7.2, 7.3, 6.4_

  - [ ] 8.2 設定画面とインデックス化 UI を実装する
    - Vault パス・LLM バックエンド設定を変更できる設定フォームを実装する（`/api/config` と連携）
    - インデックス化ボタンと実行状況（進捗・完了・エラー）のリアルタイム表示を実装する（`/api/index` と `/api/status` と連携）
    - _Requirements: 7.4, 7.5, 1.1_

- [ ] 9. Docker Compose 対応
  - [ ] 9.1 `Dockerfile`（`backend/Dockerfile`）を作成する
    - Python ベースイメージで `requirements.txt` をインストールする
    - `backend/` をコピーして `uvicorn` でサーバーを起動するエントリポイントを設定する

  - [ ] 9.2 `docker-compose.yml` をプロジェクトルートに作成する
    - `backend` サービスを定義し、Vault ディレクトリと ChromaDB データディレクトリをボリュームマウントする
    - `.env` ファイルを `env_file` として読み込む
    - `API_PORT` で指定したポートをホストに公開する
    - _Requirements: 7.1, 7.6, 9.2_

- [ ] 10. 統合テストと最終チェックポイント
  - [ ]\* 10.1 統合テストを書く（pytest + unittest.mock）
    - `LLMBackend` のモックを使用した `Generator` の動作確認テストを書く
    - `EmbeddingBackend` のモックを使用した `Indexer` と `Retriever` の動作確認テストを書く
    - ローカルの一時ディレクトリを使用した ChromaDB への実際の保存・取得テストを書く
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ] 10.2 最終チェックポイント — 全テストの通過確認
    - 全プロパティテスト・例ベーステスト・統合テストが通過することを確認する。問題があればユーザーに確認する。

- [ ] 11. 検索モード（`Auto` / `Diary` / `General`）の追加
  - [ ] 11.1 データモデルに `SearchMode` を追加する
    - `backend/models.py` に `SearchMode` 列挙型を追加する
    - `ChatRequest` に `search_mode` フィールドを追加し、デフォルト値を `auto` にする
    - _Requirements: 11.2, 11.6, 8.2_

  - [ ] 11.2 `Retriever` に検索モード分岐を実装する
    - `retrieve(query, scope, top_k, search_mode)` シグネチャに更新する
    - `diary` モードでは日付正規化と日記ファイル名ベース検索を優先する
    - `general` モードでは意味検索を優先し、日記ファイル名検索を強制しない
    - `auto` モードではクエリ内容から日記検索優先か汎用検索優先かを自動判定する
    - _Requirements: 11.3, 11.4, 11.5, 11.7_

  - [ ] 11.3 `/api/chat` で検索モードを受け渡す
    - `backend/routers/chat.py` で `search_mode` を受け取り、`Retriever` と `Generator` に反映する
    - 検索モード未指定時は `auto` を使用する
    - _Requirements: 11.2, 11.6, 8.2_

  - [ ] 11.4 Web UI に検索モード選択UIを追加する
    - `frontend/index.html` に `Auto` / `Diary` / `General` の選択コンポーネントを追加する
    - `/api/chat` への送信ペイロードに `search_mode` を含める
    - _Requirements: 11.1, 11.2, 7.2_

  - [ ]\* 11.5 検索モードの例ベーステストを追加する
    - `diary` モードで日付クエリがファイル名ベース検索優先になることを検証する
    - `general` モードで意味検索が継続して使われることを検証する
    - `auto` モード未指定時に `auto` が使われることを検証する
    - _Requirements: 11.3, 11.4, 11.5, 11.6, 11.7_

- [ ] 12. メタデータ活用型ハイブリッド検索の実装
  - [ ] 12.1 メタデータ分析ヘルパー関数を実装する
    - Retriever に `_is_diary_source_path()` と `_prioritize_diary_chunks()` を追加
    - 時系列順序付けのための `_sort_chunks_by_date()` を実装
    - 複雑なクエリから検索語を特定する `_extract_main_keyword()` を追加
    - 時間ベースの質問（初めて/最後/いつ）を検出する `_is_temporal_query()` を追加
    - _Requirements: 検索精度の向上_

  - [ ] 12.2 「初めて/最後/いつ」クエリの時系列検索を実装する
    - 時間キーワード（初めて, 最後, いつ, 最初, 登場）を含むクエリを検出
    - メイン検索語を抽出（例：「oxiosという名前が初めて登場したのはいつ？」から「oxios」）
    - メイン語に対して広範な意味検索を実行
    - `last_modified` メタデータでソートして最古/最新の出現を検出
    - 時系列コンテキスト付きで時系列順に並べたチャンクを返す
    - _Requirements: 時系列分析能力_

  - [ ] 12.3 キーワード出現頻度分析を実装する
    - ドキュメント間の出現回数をカウントする `_analyze_keyword_frequency()` を追加
    - ピークアクティビティ期間を特定する `_find_concentration_periods()` を実装
    - トレンド分析のための月次/週次集計関数を追加
    - パフォーマンス最適化のため分析結果をキャッシュ
    - _Requirements: 統計分析機能_

  - [ ] 12.4 時系列ソートと集約を実装する
    - 時系列グループ化のための `_group_chunks_by_time_period()` を追加
    - 「初めての出現」クエリ用の `_find_earliest_occurrence()` を実装
    - 最も詳細な議論を特定する `_find_deepest_analysis()` を追加
    - 集中期間の時系列サマリー生成を作成
    - _Requirements: 高度な時系列推論_

  - [ ] 12.5 メタデータ活用型検索のテストを追加する
    - 時系列クエリの検出と処理をテスト
    - 時系列ソートの正確性を検証
    - サンプルデータでのキーワード頻度分析をテスト
    - 集中期間検出を検証
    - ハイブリッド検索シナリオの統合テストを追加
    - _Requirements: 検索の信頼性と正確性_

## 注意事項

- `*` が付いたサブタスクはオプションであり、MVP として優先度を下げて実装できる
- 各タスクは対応する requirements の番号を参照しており、トレーサビリティを確保している
- チェックポイントタスク（6, 10.2）で段階的な品質確認を行う
- プロパティテストは `hypothesis` を使用し、各テストに対応する Property 番号をコメントで記載する
- 統合テストでは外部 LLM・Embedding API への実際の呼び出しはモックで代替する
