# Requirements Document

## Introduction

本プロダクトは、ホームサーバー上で動作するObsidian-firstなプライベートRAGチャットアプリケーションである。「Obsidian Vaultとチャットする」というプロダクトアイデンティティを中心に据え、個人の日記・ノート・知識管理をAIで検索・参照できるようにする。

プライバシーファースト・ローカルファーストを設計原則とし、VaultデータはホームサーバーのLAN境界内に留まる。ローカルLLM（Ollama、LM Studio等のOpenAI互換ローカルAPIサーバー）とクラウドLLM（OpenAI等）の両方をサポートし、ユーザーが選択できる。インターフェースはローカルウェブUIとローカルAPIレイヤーで提供する。

将来的にはMCPサーバーとして公開し、Tailscaleを経由したスマートフォンからのプライベートアクセスを可能にするアーキテクチャへの拡張を見据えた設計とする。

## Glossary

- **Chatbot**: ユーザーの自然言語による質問を受け付け、Vaultの内容を根拠に回答するシステム全体
- **Vault**: Obsidianのノートディレクトリのルートフォルダ。Markdownファイル群を含む
- **Note**: Vault内の個々のMarkdownファイル（.md）
- **Frontmatter**: NoteのYAMLヘッダーブロック（`---`で囲まれた部分）。タイトル・タグ・日付などのメタデータを含む
- **Ingestor**: VaultのNoteを読み込み、メタデータを抽出し、Indexerに渡すコンポーネント。他のデータソースへの拡張を考慮して独立した層として定義する
- **Indexer**: Ingestorから受け取ったNoteをチャンク分割・Embedding生成・Vector_Storeへの保存を行うコンポーネント
- **Vector_Store**: Noteのチャンクをベクトル形式で保存・検索するデータベース（例: ChromaDB）
- **Retriever**: ユーザーのクエリに対してVector_Storeから関連Chunkを検索するコンポーネント
- **LLM**: 回答生成に使用する大規模言語モデル。ローカルLLM（Ollama、LM Studio等）またはクラウドLLM（OpenAI等）
- **Embedding_Model**: テキストをベクトルに変換するモデル。ローカルモデルまたはクラウドAPIを使用
- **Chunk**: NoteをRAG処理のために分割したテキスト単位
- **Embedding**: テキストを数値ベクトルに変換したもの
- **Citation**: 回答の根拠となったNoteのファイルパス・タイトル・関連スニペットを含む引用情報
- **Web_UI**: ブラウザからアクセスするローカルウェブインターフェース
- **API_Server**: チャット機能をHTTP経由で提供するサーバーコンポーネント。将来のMCP連携の基盤となる
- **Scope**: チャットや検索の対象をフォルダまたはタグで絞り込む条件
- **MCP_Server**: Model Context Protocol に準拠したサーバー。AIエージェントからツール・リソース・プロンプトとして本システムを利用可能にする（将来機能）
- **Tailscale**: プライベートVPNネットワーク。外出先のスマートフォンからホームサーバーへの安全なアクセスを提供する（将来機能）

---

## Requirements

### Requirement 1: Vault設定

**User Story:** ユーザーとして、ローカルのObsidian VaultパスをシステムUIから設定したい。そうすることで、コードを変更せずに自分のVaultを対象としたRAGを利用できる。

#### Acceptance Criteria

1. THE Web_UI SHALL Vaultディレクトリパスを入力・保存できる設定画面を提供する
2. WHEN Vaultパスが保存されたとき、THE API_Server SHALL 指定されたパスが存在するディレクトリであることを検証する
3. IF 指定されたパスが存在しない場合、THEN THE API_Server SHALL エラーメッセージをレスポンスに含めてVaultパスを保存しない
4. THE API_Server SHALL 設定値を`.env`ファイルおよび環境変数から読み込む
5. THE API_Server SHALL APIキー等の機密情報について、`keyring`ライブラリを使用したOSネイティブのキーチェーン（macOS Keychain、Windows Credential Locker、Linux Secret Service）への保存・取得をオプションとしてサポートする
6. WHEN キーチェーンが利用可能な環境でAPIキーが設定されたとき、THE API_Server SHALL `.env`への平文保存の代わりにキーチェーンへの保存を選択できるようにする
7. THE API_Server SHALL 少なくとも以下の設定項目をサポートする: Vaultディレクトリパス、LLMプロバイダー種別、LLMモデル名、Embedding_Modelプロバイダー種別、Embedding_Modelモデル名、Vector_Storeの保存パス、APIキー（クラウドLLM使用時）
8. IF 必須設定項目が未設定の場合、THEN THE API_Server SHALL 未設定の項目名を列挙したエラーメッセージを出力して起動を中断する

---

### Requirement 2: Vaultインジェスト（Ingestor層）

**User Story:** ユーザーとして、ObsidianのVaultをインジェストしたい。そうすることで、ノートの内容とメタデータをRAGの検索対象として利用できる。

#### Acceptance Criteria

1. WHEN インジェスト処理が開始されたとき、THE Ingestor SHALL 指定されたVaultディレクトリ配下のすべての`.md`ファイルを再帰的に読み込む
2. WHEN Noteが読み込まれたとき、THE Ingestor SHALL 以下のメタデータを抽出する: ファイルパス（Vaultルートからの相対パス）、ノートタイトル（Frontmatterの`title`フィールド、存在しない場合はファイル名から拡張子を除いたもの）、タグ（Frontmatterの`tags`フィールド）、Frontmatter全体のキーと値、ファイルの最終更新日時
3. WHEN NoteにFrontmatterが存在する場合、THE Ingestor SHALL Frontmatterブロックをノート本文から分離し、本文テキストとFrontmatterメタデータをそれぞれ独立して保持する
4. IF 個別のNoteの読み込みに失敗した場合、THEN THE Ingestor SHALL 該当ファイルのパスと失敗理由をログに記録し、残りのNoteの処理を継続する
5. WHEN インジェスト処理が完了したとき、THE Ingestor SHALL 処理したNoteの総数・スキップしたNoteの総数をログに出力する
6. THE Ingestor SHALL Indexerとは独立したインターフェースを持ち、将来のObsidian以外のデータソースへの拡張を可能にする

---

### Requirement 3: Vaultインデックス化（Indexer層）

**User Story:** ユーザーとして、インジェストされたNoteをインデックス化したい。そうすることで、意味的な類似検索が可能になる。

#### Acceptance Criteria

1. WHEN Ingestorからノートデータが渡されたとき、THE Indexer SHALL NoteをChunkサイズ1000文字・オーバーラップ200文字の単位に分割する
2. WHEN ChunkへのEmbedding生成が要求されたとき、THE Indexer SHALL 設定で指定されたEmbedding_Modelを使用してベクトルを生成する
3. WHEN すべてのChunkのEmbeddingが生成されたとき、THE Indexer SHALL Ingestorが抽出したメタデータ（ファイルパス、タイトル、タグ、Frontmatter、更新日時）をChunkに付与してVector_Storeへ永続化する
4. WHEN インデックス化が完了したとき、THE Indexer SHALL 処理したNoteの総数とChunkの総数をログに出力する
5. IF Vaultディレクトリが存在しない場合、THEN THE Indexer SHALL エラーメッセージを出力して処理を中断する
6. WHEN インデックス化が再実行されたとき、THE Indexer SHALL 既存のVector_Storeを上書きして最新のVaultの状態を反映する

---

### Requirement 4: LLMバックエンドの選択

**User Story:** ユーザーとして、ローカルLLMとクラウドLLMを設定で切り替えたい。そうすることで、プライバシー要件やコスト要件に応じて最適なバックエンドを選択できる。

#### Acceptance Criteria

1. THE API_Server SHALL ローカルLLMバックエンド（OpenAI互換ローカルAPIサーバー：Ollama、LM Studio等）とクラウドLLMバックエンド（OpenAI互換API）の両方をサポートする
2. WHEN LLMプロバイダーとして`local`が設定されている場合、THE API_Server SHALL 設定されたエンドポイントURL（例: `http://localhost:11434`、`http://localhost:1234`）とモデル名を使用してローカルLLMに接続する
3. WHEN LLMプロバイダーとして`openai`が設定されている場合、THE API_Server SHALL OpenAI APIキーを使用してクラウドLLMに接続する
4. THE API_Server SHALL Embedding_Modelについても同様に、ローカルモデル（OpenAI互換ローカルAPI）とクラウドモデル（OpenAI互換API）の両方をサポートする
5. IF LLMへの接続が失敗した場合、THEN THE API_Server SHALL エラーの内容をレスポンスに含め、ユーザーに通知する
6. THE API_Server SHALL LLMおよびEmbedding_Modelのバックエンドを抽象化したインターフェースを定義し、将来の新しいプロバイダー追加を容易にする

---

### Requirement 5: 自然言語によるチャット検索

**User Story:** ユーザーとして、ウェブUIから自然言語で質問を入力したい。そうすることで、Vaultの内容に基づいた回答とCitationを得られる。

#### Acceptance Criteria

1. WHEN ユーザーがWeb_UIに質問を入力したとき、THE Retriever SHALL Vector_Storeから意味的に関連する上位5件のChunkを検索する
2. WHEN 関連Chunkが取得されたとき、THE Chatbot SHALL 取得したChunkをコンテキストとしてLLMに渡し、回答を生成する
3. WHEN 回答が生成されたとき、THE Chatbot SHALL 回答テキストとともにCitationとして根拠となったNoteのファイルパス・タイトル・関連スニペットを返す
4. WHEN ユーザーが追加の質問を入力したとき、THE Chatbot SHALL 直近5ターン分の会話履歴をコンテキストに含めて回答を生成する
5. IF Vector_Storeにインデックスが存在しない場合、THEN THE Chatbot SHALL 「先にインデックス化を実行してください」というメッセージを返す
6. IF LLMへのAPI呼び出しが失敗した場合、THEN THE Chatbot SHALL エラーの内容をユーザーに通知し、再試行を促すメッセージを返す
7. WHEN Vaultの内容に関連情報が存在しない場合、THE Chatbot SHALL 「Vaultに関連する情報が見つかりませんでした」と回答し、推測による回答を行わない

---

### Requirement 6: フォルダ/タグスコーピング

**User Story:** ユーザーとして、チャットの検索対象をフォルダまたはタグで絞り込みたい。そうすることで、特定のトピックや期間のノートに限定した質問ができる。

#### Acceptance Criteria

1. WHEN ユーザーがScopeとしてフォルダパスを指定したとき、THE Retriever SHALL 指定されたフォルダ配下のNoteから生成されたChunkのみを検索対象とする
2. WHEN ユーザーがScopeとしてタグを指定したとき、THE Retriever SHALL 指定されたタグを持つNoteから生成されたChunkのみを検索対象とする
3. WHEN Scopeが指定されていない場合、THE Retriever SHALL Vault全体を検索対象とする
4. THE Web_UI SHALL フォルダパスまたはタグをScopeとして指定できるUIコンポーネントを提供する
5. IF 指定されたScopeに該当するNoteが存在しない場合、THEN THE Chatbot SHALL 「指定されたスコープに該当するノートが見つかりませんでした」というメッセージを返す
6. THE System SHALL 検索モード判定より前に、UIまたはテキストコマンドから与えられたScopeを決定論的に解釈し、確定した検索条件としてRetrieval処理に渡す
7. THE System SHALL 将来的なテキストコマンド入力において、`#tag` をタグスコープ、`@folder` をフォルダスコープとして解釈できるように設計される

---

### Requirement 7: ローカルウェブUI

**User Story:** ユーザーとして、ブラウザからチャットUIにアクセスしたい。そうすることで、CLIを使わずに直感的にVaultと対話できる。

#### Acceptance Criteria

1. THE Web_UI SHALL ローカルネットワーク上のブラウザからアクセス可能なウェブアプリケーションとして提供される
2. THE Web_UI SHALL チャット入力フォーム・会話履歴表示・Citation表示を含むチャット画面を提供する
3. WHEN 回答が生成されたとき、THE Web_UI SHALL 回答テキストとCitationリスト（ファイルパス・タイトル・スニペット）を画面に表示する
4. THE Web_UI SHALL インデックス化の実行状況（進捗・完了・エラー）をリアルタイムで表示する
5. THE Web_UI SHALL Vault設定・LLMバックエンド設定を変更できる設定画面を提供する
6. THE Web_UI SHALL 設定されたポート番号でリッスンし、ローカルネットワーク内からアクセス可能とする
7. THE Web_UI SHALL 構造化されたフロントエンドアーキテクチャを採用し、保守性と拡張性を確保する

#### フロントエンドアーキテクチャ

**ディレクトリ構成:**

```
frontend/
├── index.html                 # メインHTMLファイル
├── styles/
│   ├── globals.css           # グローバルスタイルとCSS変数
│   └── components.css        # コンポーネントスタイル
├── components/
│   └── App.jsx              # メインReactコンポーネント
├── utils/
│   └── http.js              # HTTPユーティリティ関数
└── assets/
    └── images/              # 画像ファイル用
```

**技術スタック:**

- React 18 (CDN)
- Babel Standalone (JSX変換)
- Fetch API (HTTP通信)
- CSS Variables (テーマ管理)
- レスポンシブデザイン

**コンポーネント構成:**

- **App.jsx**: メインアプリケーションコンポーネント
- **globals.css**: リセット、タイポグラフィ、CSS変数
- **components.css**: すべてのUIコンポーネントスタイル
- **http.js**: HTTP通信ユーティリティ（GET/POST/PUT）

**CSS変数によるテーマ管理:**

```css
:root {
  --primary-color: #3498db;
  --secondary-color: #2c3e50;
  --success-color: #27ae60;
  --error-color: #e74c3c;
  /* その他テーマ変数 */
}
```

---

### Requirement 8: APIレイヤー

**User Story:** 開発者として、チャット機能をHTTP API経由で呼び出せるようにしたい。そうすることで、将来的にMCPサーバーや外部クライアントから本システムを利用できる。

#### Acceptance Criteria

1. THE API_Server SHALL `/api/chat`エンドポイントをPOSTメソッドで提供する
2. WHEN `/api/chat`エンドポイントにリクエストが送信されたとき、THE API_Server SHALL リクエストボディのJSONから`query`フィールドと任意の`scope`フィールドを読み取り、チャット処理を実行する
3. WHEN 回答が生成されたとき、THE API_Server SHALL `answer`フィールドと`citations`フィールドを含むJSONレスポンスを返す
4. THE API_Server SHALL `/api/index`エンドポイントをPOSTメソッドで提供し、インデックス化処理をトリガーできるようにする
5. THE API_Server SHALL `/api/status`エンドポイントをGETメソッドで提供し、インデックス化の状態・Vector_Storeの統計情報を返す
6. IF リクエストボディに`query`フィールドが存在しない場合、THEN THE API_Server SHALL HTTPステータスコード400とエラーメッセージを返す
7. IF 内部処理でエラーが発生した場合、THEN THE API_Server SHALL HTTPステータスコード500とエラーの概要を含むJSONレスポンスを返す
8. THE API_Server SHALL 設定ファイルで指定されたポート番号でリッスンする

---

### Requirement 9: プライバシーとデータ境界

**User Story:** ユーザーとして、Vaultのデータがホームサーバーの外部に送信されないことを保証したい。そうすることで、個人の日記や機密ノートを安心して利用できる。

#### Acceptance Criteria

1. WHILE ローカルLLMバックエンドが設定されている場合、THE API_Server SHALL Vaultのテキストデータを外部ネットワークに送信しない
2. THE API_Server SHALL デフォルト設定でローカルネットワーク（localhost または LAN）のみにバインドし、パブリックインターネットへの公開を行わない
3. THE API_Server SHALL 使用するLLMバックエンドの種別（ローカル/クラウド）と、クラウド使用時のデータ送信先をログに明示する
4. WHERE クラウドLLMバックエンドが設定されている場合、THE API_Server SHALL 起動時にクラウドへのデータ送信が発生する旨の警告をログに出力する

---

### Requirement 10: ラウンドトリップ整合性（インデックス品質保証）

**User Story:** 開発者として、インデックス化されたデータが元のNoteの内容を正確に保持していることを確認したい。そうすることで、検索結果の品質を保証できる。

#### Acceptance Criteria

1. WHEN NoteがIndexerによってChunkに分割されたとき、THE Indexer SHALL すべてのChunkを結合した結果が元のNoteの本文テキストを包含することを保証する
2. WHEN Vector_StoreにChunkが保存されたとき、THE Retriever SHALL 保存されたChunkのテキストと元のChunkのテキストが一致することを保証する
3. FOR ALL 有効なNoteに対して、インジェスト・インデックス化・検索を経たChunkのSourceメタデータが元のNoteのファイルパスと一致することを保証する（ラウンドトリップ特性）
4. FOR ALL 有効なNoteに対して、Ingestorが抽出したFrontmatterメタデータがVector_Storeに保存されたChunkのメタデータと一致することを保証する

---

### Requirement 11: 検索モードの選択

#### Acceptance Criteria

1. THE Web_UI SHALL チャット入力UIに `Auto` / `Diary` / `General` の検索モードを選択できるコンポーネントを提供する
2. WHEN ユーザーが検索モードを指定してチャットを送信したとき、THE API_Server SHALL その検索モードを `ChatRequest` に含めて処理する
3. THE System SHALL 検索モードをRetrieval分岐の最上流入力として扱い、UIまたは将来のテキストコマンドで明示されたモードを推測より優先する
4. WHEN 検索モードが `Diary` のとき、THE Retriever SHALL 日付正規化および日記ファイル名ベース検索を優先しつつ、日記スコープ内で Proposition Chunk と通常Chunkを統合して検索する
5. WHEN 検索モードが `General` のとき、THE Retriever SHALL 汎用ノート群を対象とした検索を優先し、Proposition Chunk と通常Chunkをクエリ意図に応じて統合する
6. WHEN 検索モードが `Auto` のとき、THE System SHALL まず日付意図・日記意図・日記型時系列意図を判定し、その後に fact/context 判定を行って適切な検索戦略へルーティングする
7. IF 検索モードが省略された場合、THEN THE API_Server SHALL `Auto` をデフォルト値として扱う
8. WHEN 検索モードが `Diary` で相対日付表現を含む質問が送信されたとき、THE Chatbot SHALL 解決済みの絶対日付を用いて検索と回答生成を行う
9. THE System SHALL 将来的なテキストコマンド入力において、`/auto`、`/diary`、`/general` を検索モード指定として決定論的に解釈できるように設計される

---

### Requirement 12: メタデータ活用型ハイブリッド検索

**User Story:** ユーザーとして、「初めて登場したのはいつか」「いつ頃よく登場するか」のような質問を通じて、Vault全体にまたがる時系列的な変化や集中期間を把握したい。そうすることで、単なる類似検索だけでなく、メタデータを活用した探索や分析ができる。

#### Acceptance Criteria

1. WHEN ユーザーが「初めて」「最初」「最後」「いつ」などの時系列意図を含むクエリを送信したとき、THE Retriever SHALL クエリから主対象キーワードを抽出し、関連Chunkを時系列順に並べ替えて返す
2. THE Retriever SHALL `Chunk.last_modified` および利用可能な日付系メタデータを用いて、検索結果の時系列ソートと絞り込みを行う
3. WHEN ユーザーが特定キーワードの出現傾向を尋ねたとき、THE Retriever または THE Chatbot SHALL 出現頻度と集中期間を推定するための集約結果を回答生成に利用できる
4. THE Retriever SHALL 時系列クエリに対して、まず広めの意味検索を行い、その後にPython側でメタデータによる再順位付けと分析を行う
5. THE Chatbot SHALL 時系列分析の結果を、元のChunkに対応するCitationとともに回答に含める
6. IF 時系列分析に必要なメタデータまたは該当Chunkが存在しない場合、THEN THE Chatbot SHALL 根拠不足であることを明示し、推測で補完しない
7. THE System SHALL 既存のフォルダスコープ・タグスコープ・検索モード指定と両立する形でメタデータ活用型検索を適用する
8. WHEN 時系列クエリが日記意図を伴う場合、THE Retriever SHALL diary-scoped Proposition Chunk と通常Chunkを統合し、日付メタデータを用いて再順位付けする
9. THE System SHALL 検索精度向上を現時点の最優先目標とし、日付一致・ファイル名一致・日記スコープ・命題/本文の両立を検索品質向上の主要手段として扱う

---

### Requirement 13: 検索入力の決定論的解析

**User Story:** ユーザーとして、将来的にチャット入力欄で検索モードやスコープをテキストとして指定したい。そうすることで、UI操作に依存せず、検索条件を明示的かつ再現可能に指定できる。

#### Acceptance Criteria

1. THE System SHALL 生のユーザー入力を最初に解析し、検索モード・スコープ・自然文クエリ本文を分離する
2. WHEN ユーザーが `/diary 最後にビールを飲んだのはいつ？ #飲み会` のような入力を送信したとき、THE System SHALL `search_mode=diary`、`tags=["飲み会"]`、`query="最後にビールを飲んだのはいつ？"` として解釈する
3. THE System SHALL UIで指定された検索モード・スコープとテキストコマンドから抽出された条件を統合し、一貫したRetrieval planを生成する
4. IF UI指定とテキストコマンド指定が競合する場合、THEN THE System SHALL 明示的なテキストコマンド指定を優先する
5. THE Retrieval layer SHALL 推測に依存する前に、上流で確定した検索モード・スコープ・正規化済みクエリを受け取って実行する

---

## 将来の展望

### Requirement 14: MCPセキュリティとレート制限

**User Story:** システム管理者として、AIエージェントによるMCP経由のリクエストが暴走したり不具合でエンドレスに続いたりするのを防ぎたい。そうすることで、システムの安定性とリソース保護を確保できる。

#### Acceptance Criteria

1. THE MCP_Server SHALL AIエージェントごとにリクエストレート制限を実装する
2. WHEN 単一のAIエージェントが短時間に過剰なリクエストを送信した場合、THE MCP_Server SHALL HTTPステータスコード429（Too Many Requests）を返す
3. THE MCP_Server SHALL リクエスト頻度の異常検知を自動的に行い、急激なリクエスト増加を検出した場合にアラートを生成する
4. THE MCP_Server SHALL グローバルなリクエスト制限（例: 全エージェント合わせて1時間1000リクエスト）を設定可能にする
5. WHEN リクエスト制限に達した場合、THE MCP_Server SHALL レート制限情報とリセット時間をレスポンスヘッダーに含める
6. THE MCP_Server SHALL 持続的な暴走を検知した場合、該当エージェントを一時的にブラックリストに追加する
7. THE MCP_Server SHALL セッションごとのリクエスト追跡と異常検知を実装する
8. THE MCP_Server SHALL 管理者がレート制限パラメータを実行時に調整できる設定インターフェースを提供する
9. THE MCP_Server SHALL レート制限違反のログを詳細に記録し、監査証跡として保持する

#### レート制限仕様

**デフォルト制限値:**

- **単一エージェント**: 1分あたり10リクエスト、1時間あたり100リクエスト
- **グローバル**: 1分あたり50リクエスト、1時間あたり500リクエスト
- **バースト許容**: 1分あたり最大20リクエスト（短期スパイク対応）

**異常検知アルゴリズム:**

- 5分間のリクエストレートが平常時の300%を超えた場合に警告
- 10分間の継続的な高レートリクエストで自動制限強化
- 同一パターンのリクエストが繰り返される場合にフラグ立て

**セキュリティ対策:**

- IPアドレスとエージェントIDの組み合わせで追跡
- Exponential Backoffによる自動リトライ制御
- 管理者による手動ブロック機能

---

### MCP統合（将来機能）

本システムは将来的にMCPサーバーとして公開し、Tailscaleを経由したスマートフォンからのプライベートアクセスを可能にするアーキテクチャへの拡張を見据えた設計とする。以下は候補となるMCPインターフェースである。

**候補tools:**

- `search_vault`: クエリとオプションのScopeを受け取り、関連ChunkとCitationを返す
- `get_note`: ファイルパスを受け取り、Noteの全文とメタデータを返す
- `list_notes`: フォルダまたはタグでフィルタリングしたNoteの一覧を返す
- `index_vault`: インデックス化処理をトリガーし、完了状態を返す

**候補resources:**

- `vault://notes/{path}`: 指定パスのNoteの内容をリソースとして公開する
- `vault://tags`: Vault内のすべてのタグ一覧をリソースとして公開する
- `vault://index/status`: インデックス化の状態と統計情報をリソースとして公開する

**候補prompts:**

- `ask_vault`: Vaultに対する質問を構造化されたプロンプトとして提供する
- `summarize_note`: 指定したNoteの要約を生成するプロンプトを提供する

### Tailscaleによるプライベートアクセス（将来機能）

Tailscaleを使用することで、外出先のスマートフォンからホームサーバー上の本システムにプライベートかつ安全にアクセスできるようにする。Web_UIおよびAPI_ServerはTailscaleネットワーク上のIPアドレスでアクセス可能とし、パブリックインターネットへの公開は行わない。
