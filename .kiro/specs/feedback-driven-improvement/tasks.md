# タスクリスト: フィードバック駆動型自己改善機能

## Tasks

- [x] 1. データモデルの追加
  - [x] 1.1 `backend/models.py` に `FeedbackRequest`、`ImprovementRule`、`FeedbackRuleResponse` モデルを追加する
  - [x] 1.2 `FeedbackRequest` に `message_id`、`query`、`answer`、`feedback_type`（Literal["positive","negative"]）、`improvement_request`（Optional）フィールドを定義する
  - [x] 1.3 `ImprovementRule` に `id`、`query_text`、`answer_text`、`improvement_request`、`created_at` フィールドを定義する
  - [x] 1.4 `FeedbackRuleResponse` に `id`、`query_text`、`improvement_request`、`created_at` フィールドを定義する

- [x] 2. FeedbackStore の実装
  - [x] 2.1 `backend/feedback/` ディレクトリと `__init__.py` を作成する
  - [x] 2.2 `backend/feedback/store.py` に `FeedbackStore` クラスを実装する
  - [x] 2.3 `__init__` で `improvement_rules` テーブルと `feedback_logs` テーブルを CREATE TABLE IF NOT EXISTS で作成する
  - [x] 2.4 `save_rule(query_text, answer_text, improvement_request, embedding)` メソッドを実装し、Embedding を `pickle.dumps` で BLOB 保存する
  - [x] 2.5 `log_feedback(message_id, query_text, feedback_type)` メソッドを実装する
  - [x] 2.6 `get_all_rules()` メソッドを実装し、`List[ImprovementRule]` を返す
  - [x] 2.7 `delete_rule(rule_id)` メソッドを実装し、存在しない場合は `False` を返す
  - [x] 2.8 `get_rules_with_embeddings()` メソッドを実装し、`List[Tuple[ImprovementRule, List[float]]]` を返す

- [x] 3. RuleRetriever の実装
  - [x] 3.1 `backend/feedback/retriever.py` に `RuleRetriever` クラスを実装する
  - [x] 3.2 `retrieve_rules(query, top_k)` メソッドを実装する
  - [x] 3.3 `EmbeddingBackend.embed([query])` でクエリの Embedding を生成する
  - [x] 3.4 `numpy` を使ってコサイン類似度を計算し、降順ソートして上位 `top_k` 件を返す
  - [x] 3.5 `top_k <= 0` または空ストアの場合は空リストを返す
  - [x] 3.6 例外発生時は空リストを返し、ログに記録する（例外を伝播させない）

- [-] 4. Generator へのルール注入機能の追加
  - [x] 4.1 `Generator.__init__` に `rule_retriever: Optional[RuleRetriever] = None` 引数を追加する
  - [x] 4.2 `Generator.generate` 内で `rule_retriever` が存在する場合に `retrieve_rules(query, top_k=3)` を呼び出す
  - [x] 4.3 `Generator._build_prompt` に `improvement_rules` 引数を追加し、CONTEXT セクションの前に IMPROVEMENT RULES セクションを挿入するロジックを実装する
  - [x] 4.4 `_estimate_tokens(text)` メソッドを実装する（`len(text) // 2`）
  - [x] 4.5 `_trim_rules_to_fit(rules, base_prompt, max_tokens=4096)` メソッドを実装し、トークン上限を超えないようにルール件数を削減する
  - [x] 4.6 ルール取得失敗時は空リストで継続し、例外を伝播させない

- [-] 5. フィードバック API ルーターの実装
  - [x] 5.1 `backend/routers/feedback.py` を作成し、FastAPI `APIRouter` を定義する
  - [x] 5.2 `POST /feedback` エンドポイントを実装する
    - `feedback_type == "negative"` かつ `improvement_request` が非空の場合、Embedding を生成して `save_rule` を呼び出す
    - すべてのリクエストで `log_feedback` を呼び出す
    - `{"status": "ok"}` を返す
  - [x] 5.3 `GET /feedback/rules` エンドポイントを実装し、`List[FeedbackRuleResponse]` を返す
  - [x] 5.4 `DELETE /feedback/rules/{rule_id}` エンドポイントを実装し、存在しない場合は HTTP 404 を返す

- [-] 6. アプリケーション初期化への統合
  - [x] 6.1 `backend/main.py` の lifespan 関数に `FeedbackStore` の初期化を追加する（`backend/feedback.db`）
  - [x] 6.2 `RuleRetriever` を `FeedbackStore` と `embedding_backend` で初期化する
  - [x] 6.3 `Generator` を `rule_retriever` 付きで初期化する
  - [ ] 6.4 `backend/routers/dependencies.py` に `get_feedback_store` と `get_rule_retriever` 依存関数を追加する
  - [x] 6.5 `backend/main.py` の `create_app` 関数に `feedback_router` を `/api` プレフィックスで登録する

- [-] 7. フロントエンド フィードバック UI の実装
  - [x] 7.1 `frontend/index.html` の `assistantMessage` オブジェクトに `messageId`（タイムスタンプベース）フィールドを追加する
  - [x] 7.2 アシスタントメッセージの下部に `FeedbackButtons` コンポーネント（インライン関数）を追加する
  - [x] 7.3 👍/👎ボタンを実装し、クリック時に選択済み状態に変化させる
  - [x] 7.4 👎クリック時に改善リクエスト入力欄とキャンセルボタンを表示する
  - [x] 7.5 送信ボタンクリック時に `POST /api/feedback` を呼び出し、完了後に入力欄を非表示にしてボタンを無効化する
  - [x] 7.6 キャンセルボタンクリック時に入力欄を非表示にし、👎の選択状態を解除する
  - [x] 7.7 送信失敗時にエラーメッセージを表示し、ボタン状態を送信前に戻す
  - [ ] 7.8 `frontend/styles/components.css` にフィードバックボタンのスタイルを追加する

- [x] 8. ユニットテストの作成
  - [x] 8.1 `backend/tests/test_feedback_store.py` を作成し、`FeedbackStore` のユニットテストを実装する
    - テーブル自動作成の確認
    - ルール保存・取得・削除のテスト
    - フィードバックログ記録のテスト
  - [x] 8.2 `backend/tests/test_rule_retriever.py` を作成し、`RuleRetriever` のユニットテストを実装する
    - モック `EmbeddingBackend` を使ったコサイン類似度検索のテスト
    - 空ストア・top_k=0 での空リスト返却のテスト
    - 例外時の空リスト返却のテスト
  - [x] 8.3 `backend/tests/test_generator_rules.py` を作成し、ルール注入機能のユニットテストを実装する
    - ルールあり/なしのプロンプト構造テスト
    - `_trim_rules_to_fit` のトークン上限テスト
    - RuleRetriever 例外時の継続テスト
  - [x] 8.4 `backend/tests/test_feedback_router.py` を作成し、フィードバック API のテストを実装する
    - 各エンドポイントの正常系・異常系テスト

- [x] 9. プロパティベーステストの作成（hypothesis を使用）
  - [x] 9.1 `backend/tests/test_feedback_properties.py` を作成する
  - [x] 9.2 **Property 1**: ランダムなテキストトリプルと Embedding ベクトルで保存→取得ラウンドトリップを検証する（最低100回）
    - `Feature: feedback-driven-improvement, Property 1: 改善ルール保存ラウンドトリップ`
  - [x] 9.3 **Property 2**: FeedbackStore を複数回初期化してもエラーが発生せずテーブルが存在することを検証する（最低100回）
    - `Feature: feedback-driven-improvement, Property 2: FeedbackStore 初期化の冪等性`
  - [x] 9.4 **Property 3**: ランダムなクエリとルールセットで、返却リストが類似度降順かつ top_k 以下であることを検証する（最低100回）
    - `Feature: feedback-driven-improvement, Property 3: ルール取得の順序と件数制約`
  - [x] 9.5 **Property 4**: ランダムなルールリストで、プロンプトに IMPROVEMENT RULES セクションと「- 」形式のルールが含まれることを検証する（最低100回）
    - `Feature: feedback-driven-improvement, Property 4: プロンプトへのルール注入フォーマット`
  - [x] 9.6 **Property 5**: ランダムなルールリストとベースプロンプトで、最終プロンプトのトークン推定値が4096以下であることを検証する（最低100回）
    - `Feature: feedback-driven-improvement, Property 5: トークン上限の遵守`
  - [x] 9.7 **Property 6**: ランダムなルールを保存→削除→再取得で存在しないこと、再 DELETE で 404 が返ることを検証する（最低100回）
    - `Feature: feedback-driven-improvement, Property 6: ルール削除ラウンドトリップ`

- [x] 10. 依存パッケージの追加
  - [x] 10.1 `backend/requirements.txt` に `hypothesis` を追加する
  - [x] 10.2 `numpy` が requirements.txt に含まれていることを確認し、なければ追加する
