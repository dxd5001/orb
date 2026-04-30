# 要件定義書: フィードバック駆動型自己改善機能

## はじめに

本機能は、Orbチャットシステムに対してユーザーが回答品質のフィードバック（👍/👎）を送れるようにし、👎の場合は改善リクエストを入力できる仕組みを提供する。収集したフィードバックは改善ルールとしてSQLiteデータベースに保存され、次回以降のチャットでは関連するルールをRAG（Retrieval-Augmented Generation）で動的に取得してプロンプトに注入することで、回答精度を継続的に自己改善していく。

## 用語集

- **Feedback（フィードバック）**: ユーザーが特定のチャット回答に対して送る評価。Positive（👍）またはNegative（👎）の2種類がある
- **ImprovementRule（改善ルール）**: 👎フィードバックから生成される、将来の回答を改善するための指示テキスト。クエリの文脈と改善内容をペアで保持する
- **FeedbackStore**: 改善ルールを永続化するSQLiteデータベース（`backend/feedback.db`）
- **RuleRetriever**: クエリに関連する改善ルールをFeedbackStoreからRAGで取得するコンポーネント
- **Generator**: 既存のプロンプト構築・LLM呼び出しを担当するコンポーネント（`backend/generation/generator.py`）
- **Dynamic Instruction Injection**: チャット時にクエリ関連の改善ルールをプロンプトに動的注入する仕組み
- **EmbeddingBackend**: テキストをベクトルに変換する既存の抽象インターフェース

---

## 要件

### 要件1: フィードバックUIの提供

**ユーザーストーリー:** チャットユーザーとして、アシスタントの回答に対して👍または👎でフィードバックを送りたい。そうすることで、回答品質を評価し改善に貢献できる。

#### 受け入れ基準

1. WHEN アシスタントの回答がチャット画面に表示される THEN THE Frontend SHALL 各回答の下部に👍ボタンと👎ボタンを表示する
2. WHEN ユーザーが👍ボタンをクリックする THEN THE Frontend SHALL そのボタンを選択済み状態に視覚的に変化させ、同一回答への再クリックを無効化する
3. WHEN ユーザーが👎ボタンをクリックする THEN THE Frontend SHALL 改善リクエスト入力欄とキャンセルボタンを表示する
4. WHEN 改善リクエスト入力欄が表示されている THEN THE Frontend SHALL 入力欄にプレースホルダーテキストを表示し、ユーザーが改善内容を入力できるようにする
5. WHEN ユーザーが改善リクエストを入力して送信する THEN THE Frontend SHALL フィードバックをバックエンドに送信し、送信完了後に入力欄を非表示にする
6. WHEN ユーザーがキャンセルボタンをクリックする THEN THE Frontend SHALL 改善リクエスト入力欄を非表示にし、👎ボタンの選択状態を解除する
7. WHEN フィードバックの送信が完了する THEN THE Frontend SHALL 送信済みフィードバックボタンを非活性化し、再送信を防止する
8. IF フィードバックの送信が失敗する THEN THE Frontend SHALL エラーメッセージをユーザーに表示し、ボタンの状態を送信前に戻す

---

### 要件2: フィードバック受信APIの提供

**ユーザーストーリー:** システム管理者として、フロントエンドからのフィードバックを受け取るAPIエンドポイントが欲しい。そうすることで、フィードバックデータを確実に収集・保存できる。

#### 受け入れ基準

1. THE API_Server SHALL `/api/feedback` エンドポイントをPOSTメソッドで提供する
2. WHEN `/api/feedback` にリクエストが送信される THEN THE API_Server SHALL リクエストボディから `message_id`、`query`、`answer`、`feedback_type`（`positive` または `negative`）、および任意の `improvement_request` を受け取る
3. WHEN `feedback_type` が `positive` のリクエストを受信する THEN THE API_Server SHALL フィードバックを記録し、HTTP 200 を返す
4. WHEN `feedback_type` が `negative` かつ `improvement_request` が存在するリクエストを受信する THEN THE API_Server SHALL フィードバックと改善ルールを保存し、HTTP 200 を返す
5. WHEN `feedback_type` が `negative` かつ `improvement_request` が空文字列または未指定のリクエストを受信する THEN THE API_Server SHALL フィードバックのみを記録し、HTTP 200 を返す
6. IF リクエストボディに `query` または `feedback_type` が含まれない THEN THE API_Server SHALL HTTP 422 を返す
7. IF `feedback_type` が `positive` でも `negative` でもない値の場合 THEN THE API_Server SHALL HTTP 422 を返す

---

### 要件3: 改善ルールの永続化

**ユーザーストーリー:** システムとして、収集した改善ルールを永続化したい。そうすることで、アプリケーション再起動後もルールが保持され、継続的な改善が可能になる。

#### 受け入れ基準

1. THE FeedbackStore SHALL SQLiteデータベース（`backend/feedback.db`）に `improvement_rules` テーブルを作成する
2. THE `improvement_rules` テーブル SHALL `id`（INTEGER PRIMARY KEY）、`query_text`（TEXT）、`answer_text`（TEXT）、`improvement_request`（TEXT）、`rule_embedding`（BLOB）、`created_at`（DATETIME）のカラムを持つ
3. WHEN 改善ルールが保存される THEN THE FeedbackStore SHALL `query_text`、`answer_text`、`improvement_request` を `improvement_rules` テーブルに挿入する
4. WHEN 改善ルールが保存される THEN THE FeedbackStore SHALL `query_text` と `improvement_request` を結合したテキストのEmbeddingベクトルを `rule_embedding` カラムにBLOBとして保存する
5. THE FeedbackStore SHALL アプリケーション起動時に `improvement_rules` テーブルが存在しない場合は自動的に作成する
6. THE FeedbackStore SHALL `feedback_logs` テーブルを作成し、すべてのフィードバック（👍/👎）を `message_id`、`query_text`、`feedback_type`、`created_at` とともに記録する

---

### 要件4: 関連改善ルールの動的取得

**ユーザーストーリー:** システムとして、チャット時にクエリに関連する改善ルールをRAGで取得したい。そうすることで、過去のフィードバックに基づいた回答改善が可能になる。

#### 受け入れ基準

1. THE RuleRetriever SHALL クエリテキストを受け取り、`improvement_rules` テーブルから関連するルールを返す `retrieve_rules(query: str, top_k: int) -> List[ImprovementRule]` メソッドを提供する
2. WHEN `retrieve_rules` が呼び出される THEN THE RuleRetriever SHALL クエリのEmbeddingベクトルと各ルールの `rule_embedding` のコサイン類似度を計算し、類似度の高い順に最大 `top_k` 件を返す
3. WHEN `improvement_rules` テーブルが空の場合 THEN THE RuleRetriever SHALL 空のリストを返す
4. WHEN `top_k` に0以下の値が指定された場合 THEN THE RuleRetriever SHALL 空のリストを返す
5. THE RuleRetriever SHALL 既存の `EmbeddingBackend` インターフェースを使用してクエリのEmbeddingを生成する

---

### 要件5: プロンプトへの改善ルール注入

**ユーザーストーリー:** システムとして、取得した改善ルールをLLMへのプロンプトに注入したい。そうすることで、過去のフィードバックを反映した回答が生成される。

#### 受け入れ基準

1. WHEN `Generator.generate` が呼び出される THEN THE Generator SHALL `RuleRetriever` を使用してクエリに関連する改善ルールを取得する
2. WHEN 関連する改善ルールが1件以上取得された場合 THEN THE Generator SHALL プロンプトの「CONTEXT」セクションの前に「IMPROVEMENT RULES」セクションとして改善ルールを注入する
3. WHEN 関連する改善ルールが0件の場合 THEN THE Generator SHALL 改善ルールセクションを追加せず、既存のプロンプト構造を維持する
4. THE Generator SHALL 注入する改善ルールの件数を最大3件に制限する
5. WHEN 改善ルールが注入される THEN THE Generator SHALL 各ルールを「- [改善リクエスト内容]」の形式でリスト表示する
6. THE Generator SHALL 改善ルール取得に失敗した場合でも、ルールなしで通常の回答生成を継続する

---

### 要件6: コンテキスト長の管理

**ユーザーストーリー:** システムとして、改善ルール注入後もプロンプトのコンテキスト長が上限を超えないようにしたい。そうすることで、ローカルLLMのコンテキストウィンドウ制限による生成失敗を防止できる。

#### 受け入れ基準

1. THE Generator SHALL 改善ルールを含むプロンプト全体のトークン数を推定し、設定された上限（デフォルト: 4096トークン）を超えないようにする
2. WHEN プロンプトが上限を超える場合 THEN THE Generator SHALL 改善ルールの件数を削減してプロンプトを短縮する
3. WHEN 改善ルールを0件にしてもプロンプトが上限を超える場合 THEN THE Generator SHALL 改善ルールなしで既存のチャンク削減ロジックを適用する
4. THE Generator SHALL トークン数の推定に文字数ベースの近似（1トークン ≈ 2文字）を使用する

---

### 要件7: フィードバックデータの管理API

**ユーザーストーリー:** システム管理者として、蓄積された改善ルールを確認・削除したい。そうすることで、不適切なルールを除去してシステムの品質を維持できる。

#### 受け入れ基準

1. THE API_Server SHALL `/api/feedback/rules` エンドポイントをGETメソッドで提供し、保存済みの改善ルール一覧を返す
2. WHEN `/api/feedback/rules` にリクエストが送信される THEN THE API_Server SHALL `id`、`query_text`、`improvement_request`、`created_at` を含むルール一覧をJSON形式で返す
3. THE API_Server SHALL `/api/feedback/rules/{rule_id}` エンドポイントをDELETEメソッドで提供する
4. WHEN 存在する `rule_id` に対してDELETEリクエストが送信される THEN THE API_Server SHALL 該当ルールを削除し、HTTP 200 を返す
5. IF 存在しない `rule_id` に対してDELETEリクエストが送信される THEN THE API_Server SHALL HTTP 404 を返す
