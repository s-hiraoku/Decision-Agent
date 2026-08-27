# Decision Agent 詳細設計書

> **実装同期メモ:** 本書には、実装済みの設計と採用されなかった歴史的な案が
> 混在する。現在の LLM レビューは Anthropic SDK や Claude CLI を直接使わず、
> `local-agent-gateway` の V2 API に委譲する。既定はリポジトリ不要の
> `/v2/inference/runs`、`DECISION_AGENT_GATEWAY_REPO` 設定時のみ互換用の
> `/v2/coding/runs` を使う。現行 CLI は §9 の「実装済み CLI」を正とし、
> 各節で「歴史的案」または「将来」と明記した内容は未実装である。

本書は [decision-agent-spec.md](decision-agent-spec.md) の「Still incomplete」を解消し、
実装可能なレベルまで設計を落とし込むための詳細設計書である。
仕様書がデータモデルと振る舞いの「何を」を定義するのに対し、本書は「どう作るか」を定義する。

対象読者: このリポジトリの実装者(人間または AI エージェント)。

## 1. 目的とスコープ

### 1.1 解消するギャップ

仕様書で未完了とされている 6 項目を、以下の設計で解消する。

| # | ギャップ | 本書での解決 |
|---|---------|------------|
| G1 | LLM ベースのレビュー | **実装済み:** `ReviewEngine` 抽象化 + Gateway 版 `LLMReviewEngine`(§4, §5) |
| G2 | 自由記述フィードバックからの耐久的ルール抽出 | **一部実装:** 候補ルールの昇格・競合解決フローは実装済み。自由記述からの LLM 抽出は未実装(§6) |
| G3 | 評価のセマンティックマッチング | **一部実装:** heuristic 側の文字 n-gram。LLM ジャッジは未実装(§7) |
| G4 | 生成エージェントとのオーケストレーション | Revise ループの JSON 契約定義(§8。実装は契約のみ、生成側は非スコープ) |
| G5 | 数値スコアでない、ユーザー整合の判断最適化 | **一部実装:** 構造化ルール、反復による昇格、限定的な矛盾フラグ、実績カウント。高度な最適化は未実装(§3, §6) |
| G6 | 日常の判断シグナル観察と訂正ループ | **未実装:** `observe -> decide -> log -> correct -> learn -> reuse` と Skill 契約を [設計思想](design-philosophy.md) / [Skill 設計](skill-design.md) に定義 |

### 1.2 設計原則(仕様書から継承)

1. **判断が責務、生成は責務外。**
2. **自然言語ファースト。** ルール・パターンは常に人間が読め、編集できる。
3. **LLM はプラガブル。** 既定の heuristic 経路は LLM なしで動作する。
   `--engine llm` を明示した場合は Gateway 障害時にも heuristic へ自動フォールバックしない。
4. **プロファイルは編集可能な要約、JSONL は通常時 append-only の生の証拠。**
   この分離は崩さない。ただし、ユーザーが明示した `memory forget` だけは例外とし、
   [Skill 設計](skill-design.md)のロック付き hard deletion 契約に従って対象証拠と
   依存表現を削除する。ライフサイクル処理による暗黙の削除は認めない。
5. **学習単位は「エージェントの判断とユーザーの判断の差分」。** スコアではない。
6. **LLM 抽出案は自動採用しない。** 将来 LLM が自由記述から抽出するルールは
   candidate 状態にとどめ、ユーザー承認を要求する。現在の明示フィードバック由来の
   candidate は、同じパターンが別レコードで反復すると自動昇格する。
7. **観察に明示的な記憶命令を要求しない。** 選択、却下、制約、トレードオフ、
   訂正は自然な作業中に Signal 候補として拾う。ただし Signal の保存と、広い範囲で
   再利用する Policy の有効化は分離する。
8. **訂正理由を高価値の差分として扱う。** 理由が会話にあれば再質問せず、なければ
   次の判断に必要な場合だけ自然に確認する。理由を得られないときは推測で補わない。

### 1.3 非スコープ

- Web UI、ベクトル DB、強化学習、マルチユーザー管理(仕様書の Out of Scope を踏襲)
- 生成エージェント本体の実装(§8 は契約定義のみ)
- Decision Agent 内での LLM プロバイダ固有対応。プロバイダとモデルの選択は
  local-agent-gateway の責務とする

## 2. アーキテクチャ全体像

### 2.1 モジュール構成(実装済みの主要部分)

```text
src/decision_agent/
  models.py          # データモデル(§3 で拡張)
  storage.py         # JSON / JSONL 永続化(変更小)
  cli.py             # CLI(§9 で拡張)
  agent.py           # DecisionAgent: ループの制御のみ担う(薄くする)
  engines/
    __init__.py      # ReviewEngine / FeedbackExtractor / AgreementJudge の Protocol
    heuristic.py     # 決定的レビューと heuristic AgreementJudge
    llm.py           # local-agent-gateway V2 API 版 ReviewEngine
```

`DecisionAgent` は「review → learn → evaluate のループ制御」と「エンジンへの委譲」だけを持ち、
判定ロジック本体は `engines/` に置く。既存の `agent.py` 内のヒューリスティック
(`_text_similarity`、`_matched_items` など)は `engines/heuristic.py` へ移設済み。
既存の option-ranking(`decide` / `train`)は `agent.py` に残す(現行 MVP としては凍結)。
将来の汎用判断層はこの数値プロトタイプを暗黙に拡張せず、
[Skill 設計](skill-design.md) の Signal / Policy / Decision / Correction 契約として
別途設計・実装する。

当初案の `prompts.py` と `rendering.py` は作成していない。Gateway 用プロンプトと
JSON Schema は現在 `engines/llm.py` にあり、プロバイダ固有のキャッシュや
レンダリングは Gateway 側の関心事とする。

### 2.2 抽象インターフェース

`engines/__init__.py` に 3 つの Protocol を定義する。

```python
class ReviewEngine(Protocol):
    def review(
        self,
        request: ArtifactReviewRequest,
        profile: DecisionProfile,
        records: tuple[DecisionRecord, ...],
    ) -> ArtifactReview: ...

class FeedbackExtractor(Protocol):
    """自由記述フィードバックから耐久的ルール候補を抽出する(§6)。"""
    def extract(
        self,
        request: ArtifactReviewRequest,
        agent_review: ArtifactReview,
        user_feedback: UserFeedback,
        profile: DecisionProfile,
    ) -> RuleProposalSet: ...

class AgreementJudge(Protocol):
    """評価時のセマンティック一致判定(§7)。

    heuristic / LLM の両実装が同じ監査契約(判定 + 根拠)を返す。
    heuristic 実装は evidence にマッチしたテキスト断片(なければ空文字)を入れる。
    """
    def judge(
        self, expected: UserFeedback, review: ArtifactReview
    ) -> AgreementJudgment: ...


@dataclass(frozen=True)
class CoreIssueJudgment:
    issue: str          # ユーザー judgment 側の core_issue 原文
    noticed: bool
    evidence: str       # 一致と判断した根拠(レビュー中の該当箇所の引用など)

@dataclass(frozen=True)
class AgreementJudgment:
    core_issues: tuple[CoreIssueJudgment, ...]
    revision_direction_match: bool | None   # expected が空なら None
    revision_direction_reasoning: str
```

`ReviewEngine` には heuristic と LLM の両実装がある。`AgreementJudge` は
heuristic 実装のみで、`FeedbackExtractor` の LLM 実装は将来課題である。
エンジンの選択は CLI の `--engine {heuristic,llm}` で行い、既定は
`heuristic`（API キー不要という性質を維持）とする。

### 2.3 依存関係

本体にも LLM 経路にも Python パッケージ依存を追加しない。
`engines/llm.py` は標準ライブラリの `urllib` で local-agent-gateway を呼ぶ。
認証、プロバイダ、モデル、ポリシー、監査は Gateway が所有する。

Decision Agent が参照する環境変数:

- `DECISION_AGENT_ENGINE`: CLI フラグ未指定時のエンジン
- `DECISION_AGENT_GATEWAY_URL`: Gateway URL（既定 `http://127.0.0.1:8787`）
- `DECISION_AGENT_GATEWAY_TOKEN`: 必須の owner bearer token
- `DECISION_AGENT_GATEWAY_TIMEOUT`: polling timeout 秒（既定 120）
- `DECISION_AGENT_GATEWAY_REPO`: 任意。設定時のみ互換用 coding run を使う

## 3. データモデル拡張

### 3.1 PreferenceRule の構造化

現在の `preference_rules: tuple[str, ...]` を構造化オブジェクトに拡張する。
G2(ルール承認フロー)と G5(実績に基づく昇格・降格)の土台になる。

```python
@dataclass(frozen=True)
class PreferenceRule:
    text: str                       # 自然言語ルール本体(これが主。常に人間可読)
    id: str = ""                    # 空なら採番。採番は決定的: "rule-" + sha256("preference_rule:" + text) 先頭 12 桁
    task_types: tuple[str, ...] = ()  # 空 = 全 task_type に適用
    status: str = "active"          # "active" | "candidate" | "retired"
    source: str = "user"            # "user" | "feedback" | "evaluation" | "extracted"
    source_record_ids: tuple[str, ...] = ()  # 由来する DecisionRecord / EvaluationCase の id(複数)。
                                     # 反復昇格(candidate -> active)の判定に distinct 件数を使う。
    hit_count: int = 0              # レビューで違反を検出できた回数(評価で加算)
    miss_count: int = 0             # このルールがあっても判断を外した回数
    created_at: str = ""
    last_used_at: str = ""          # このルールが最後にレビューで参照された DecisionRecord の created_at
```

**ID の決定性:** ID は uuid ではなく内容ハッシュ
(`"rule-" + sha256(kind + ":" + text).hexdigest()[:12]`)から導出する。
旧形式(文字列)プロファイルの読み込み時に採番しても、保存前に何度 load しても
同じ ID になる — これが §5.4 の決定的レンダリング(prompt caching)と、
learned_signals / agreement_evidence が参照する ID の安定性の前提になる。
同一 kind + 同一 text は定義上同一ルールなので、ハッシュ衝突は重複検出として機能する。
text を編集した場合は別ルール(新 ID)になり、旧ルールは retire する運用とする。

**後方互換:** `DecisionProfile.from_dict` は `preference_rules` の各要素が
文字列ならば `PreferenceRule(text=..., status="active", source="user")` として読む。
`to_dict` は常にオブジェクト形式で書き出す(初回の learn/iterate 実行時に自動移行される)。
`negative_patterns` / `positive_examples` も同じ構造(`PatternEntry`)に拡張し、
同じ互換規則を適用する。

**status の遷移:**

```text
candidate --(同一パターンが別レコードで 2 回以上)--> active
candidate --(ユーザー承認: rules approve)--> active
candidate --(ユーザー却下: rules reject)---> 削除
active    --(ユーザー操作 or 降格提案の承認)--> retired
```

retired はプロファイルに残す(削除しない)。review 時に参照されないが、
同じルールが再抽出されたときの重複検出に使う。
自動昇格は同一の fuzzy-matched text の反復だけを根拠にする。preference rule
同士の意味的な反対関係は検出しない。negative pattern と positive example の
同一パターン衝突は `contradicts_established_rule` で候補側にフラグを付けるが、
候補を approve しても反対側の active entry は自動 retire されない。置換する
場合は既存 entry に `rules retire` を別途実行する。

### 3.2 RuleProposalSet(ルール抽出の出力)

```python
@dataclass(frozen=True)
class RuleProposal:
    kind: str          # "preference_rule" | "negative_pattern" | "positive_example" | "known_mistake"
    text: str          # ルール本文(known_mistake の場合は pattern)
    correction: str = ""   # known_mistake のみ
    rationale: str = ""    # なぜこのフィードバックからこのルールが導かれるか
    duplicate_of: str = "" # 既存ルール id。空でなければ「既存の重複」提案

@dataclass(frozen=True)
class RuleProposalSet:
    proposals: tuple[RuleProposal, ...]
    source_record_id: str
```

### 3.3 DecisionProfile への追加フィールド

```python
schema_version: int = 2   # 旧形式(文字列ルール)は 1 として読み、書き出しで 2 に上げる
```

### 3.4 ArtifactReview / ReviewIssue への追加フィールド

```python
# ArtifactReview
engine: str = ""          # "heuristic" | "llm:claude-opus-4-8" — レビューの由来を記録に残す

# ReviewIssue
violated_rule_id: str = ""  # 違反した PreferenceRule / PatternEntry の id(該当なしは空)
```

`violated_rule_id` は**ドメインモデル側に持つ**。LLM 側の Pydantic モデル(§5.2)だけに
置くと `ArtifactReview` への変換時に脱落し、DecisionRecord に残らないため、
§7.4 の hit/miss 実績更新が成立しなくなる。`ReviewIssue.to_dict/from_dict` にも
含めて JSONL に永続化する。heuristic エンジンもルール由来の issue には
この id を設定する。

いずれも `from_dict` は欠損を空文字で許容する(既存レコードとの互換)。
DecisionRecord に engine が保存されるため、後から「LLM レビューと heuristic レビューで
delta の傾向がどう違うか」を JSONL から分析できる。

### 3.5 決定履歴の Source of Truth 一本化（実装済み）

**方針:** `DecisionProfile` から `decision_records` フィールドを削除し、
JSONL を履歴の唯一の Source of Truth とする。

```python
@dataclass(frozen=True)
class DecisionProfile:
    user_id: str
    criteria: dict[str, float]
    schema_version: int = 2
    examples: tuple[DecisionExample, ...] = ()
    preference_rules: tuple[PreferenceRule, ...] = ()
    negative_patterns: tuple[PatternEntry, ...] = ()
    positive_examples: tuple[PatternEntry, ...] = ()
    known_mistakes: tuple[KnownMistake, ...] = ()
    # decision_records は削除。履歴は常に JSONL からロードする。
```

- `DecisionAgent.learn` は更新済みプロファイルと新規 `DecisionRecord` を
  **別々の値として返す**。
  ```python
  def learn(
      self,
      request: ArtifactReviewRequest,
      agent_review: ArtifactReview,
      user_feedback: UserFeedback,
  ) -> tuple[DecisionProfile, DecisionRecord]: ...
  ```
- `DecisionAgent.review` / `evaluate` は `history_records` を明示引数で受け取り、
  省略時は空タプル（プロファイル内フォールバックなし）。
- **書き込み順序:** `learn` / `iterate` は (1) JSONL へ追記 (2) プロファイル保存。
- 旧形式プロファイルの `decision_records` は `from_dict` で無視する。埋もれた履歴は
  `migrate-history` が legacy loader で JSONL へ移す（論理 fingerprint で重複抑止）。

```bash
decision-agent migrate-history <old-profile.json> --records <records.jsonl>
```

移行後の `learn` / `iterate` はプロファイルへ履歴を再埋め込みしない。

**未実装の拡張:** `load_decision_records(path, limit=...)` による直近 N 件読み込み
（task_type 優先）は、レコード数が増えた段階で追加する。

### 3.6 task_type の拡張方法

**現状の問題:** `SUPPORTED_TASK_TYPES = {"blog_outline", "talk_outline",
"video_script"}` が `models.py` にハードコードされ、`ArtifactReviewRequest.from_dict`
がこの集合でバリデーションする。仕様書は「コアループを変えずに他の主観的成果物
(例: プレスリリース文、SNS 投稿文案)へ拡張できること」を求めているが、
現行実装では新しい成果物種別を足すたびにコード変更とリリースが要る。

**設計方針:** task_type の許可リストをコードからプロファイルへ移す。

```python
@dataclass(frozen=True)
class DecisionProfile:
    ...
    task_types: tuple[str, ...] = DEFAULT_TASK_TYPES  # 既定は現行 3 種を維持
```

- `ArtifactReviewRequest.from_dict` は単体では task_type を検証しない
  (リクエスト JSON だけでは何が有効かを判断できないため)。検証は
  `DecisionAgent` 生成時、または `review` / `learn` / `evaluate` の入口で
  `request.task_type in profile.task_types` として行う。
- 未知の task_type はエラーにする(自由文字列を許して黙って受理すると、
  タイプミスで履歴が `"blog_outline"` と `"blog_oultine"` のように分裂し、
  §4 の履歴選別が壊れる)。エラーメッセージは
  「`profile.task_types` に追加してください」と具体的な次のアクションを示す。
- 後方互換: `task_types` を持たない旧プロファイルは `DEFAULT_TASK_TYPES`
  (現行の 3 種)で読み込む。
- `decision-agent profile add-task-type <profile> <task_type> [--output F]`
  のような専用コマンドは設けない。task_type の追加はプロファイル JSON の
  直接編集で十分に低コストであり、コマンド化するとルール承認 CLI(§6.3)との
  一貫性(承認フローが必要なほど重要な変更ではない)が取れなくなる。

## 4. レビューパイプライン(エンジン共通の流れ)

`DecisionAgent.review` は次の手順に固定し、エンジン実装は手順 3 のみを差し替える。

1. **履歴選別(共通・決定的):** `_relevant_records` 相当のロジックで同一 task_type の
   レコードを類似度順に最大 `HISTORY_MATCH_LIMIT`(LLM エンジンでは 5 に拡大)件選ぶ。
   選別を決定的に保つことで、同じ入力に対する LLM プロンプトのバイト列が安定し、
   キャッシュが効く(§5.4)。
2. **プロファイル射影(共通):** status == "active" のルールのみ、かつ
   `task_types` が空 or リクエストの task_type を含むものだけをエンジンに渡す。
3. **エンジン実行:** `ReviewEngine.review(...)` を呼ぶ。
4. **後処理(共通):** verdict の妥当性検証、confidence の [0,1] クリップ、
   `engine` フィールドの付与。

## 5. LLMReviewEngine の設計

**§5.1〜§5.5 は実装されていない歴史的案である。実際の `LLMReviewEngine` は、本節が前提とする
`anthropic` Python SDK 直接呼び出しではなく、常時起動の local-agent-gateway
(Codex App Server をラップするローカル HTTP API) への委譲として実装された
(`src/decision_agent/engines/llm.py`)。レビューは `outputSchema` 付きの
Gateway V2 one-shot inference run として送られ、返ってきた `structuredOutput` を
ドメインの `ArtifactReview` に変換する。旧 Gateway との互換が必要な場合のみ、
`DECISION_AGENT_GATEWAY_REPO` を指定して read-only coding run を使う。認証・
ポリシー・監査・プロバイダ選択はすべて gateway 側の責務であり、Decision Agent は
判断モデリングに専念する、という責務分離が根拠。標準ライブラリ(urllib)のみを使い
pip 依存ゼロを維持する。
(経緯: 本節の SDK 案 → claude CLI サブプロセス案(短期間実装) → gateway 委譲、
の順に置き換えられた。) 以降の §5.1〜§5.5 は当初案の記録として残すが、
現状のコードとは一致しない。詳細は `decision-agent-spec.md` の
"Current Implementation Status" を参照。**

### 5.1 モデルとパラメータ

- モデル: `claude-opus-4-8`(固定既定。`--model` で上書き可)
- thinking: `{"type": "adaptive"}`
- `max_tokens`: 16000(非ストリーミング)
- sampling パラメータ(temperature 等)は送らない(Opus 4.8 では 400 になる)
- リトライ: SDK 既定(max_retries=2)に任せる

### 5.2 構造化出力

`client.messages.parse()` + Pydantic モデルを使い、`ArtifactReview` と同形の
スキーマを強制する。

```python
class LLMReviewIssue(BaseModel):
    severity: Literal["high", "medium", "low"]
    reason: str
    suggestion: str
    violated_rule_id: str = ""   # 違反した PreferenceRule の id(該当なしは空)

class LLMReviewOutput(BaseModel):
    verdict: Literal["accept", "revise", "reject"]
    confidence: float
    summary: str
    issues: list[LLMReviewIssue]
    revision_instruction: str
    learned_signals: list[str]
```

`violated_rule_id` はドメイン側 `ReviewIssue.violated_rule_id`(§3.4)へ
**そのまま写して永続化する**。これにより、どのルールが判定に効いたかが
DecisionRecord まで残り、§3.1 の `hit_count` 更新(§7.4)と `learned_signals` の生成
(`"checked preference rule: <id>"`)に使える。
parse 結果はドメイン側の `ArtifactReview` に変換してから返す
(Pydantic モデルを models.py に漏らさない)。

### 5.3 プロンプト構造

`prompts.py` に集約。system prompt は 2 ブロック構成にする。

```text
system[0](固定・全ユーザー共通): ジャッジ指示
  - 「あなたは特定ユーザーの判断を模倣するレビュアーである。一般的な良し悪しではなく、
     プロファイルに書かれたこのユーザーの基準だけで判定せよ」
  - verdict 3 値の定義(仕様書 §Verdicts をそのまま埋め込む)
  - issues には必ず violated_rule_id を付ける(該当ルールがない指摘は
    learned_signals 候補として扱う)こと
  - known_mistakes は preference_rules より強い証拠として扱うこと
  - プロファイルに根拠のない一般論での減点を禁止する

system[1](プロファイル・ユーザーごとに安定): レンダリング済みプロファイル + 選別済み履歴
  - §5.4 の決定的レンダリング
  - このブロック末尾に cache_control を置く

user(毎回変わる): レビュー対象
  - task_type / intent / context / artifact
```

### 5.4 Prompt caching 設計

プロファイルと履歴はリクエスト間でほぼ不変なので、キャッシュ対象にする。

- `rendering.py` の `render_profile_context(profile, records) -> str` が
  **決定的な**テキストを生成する: ルールは id 昇順、context の dict はキー昇順、
  タイムスタンプ・乱数を含めない。
- system prompt の第 2 ブロック(プロファイル + 履歴)の末尾に
  `cache_control: {"type": "ephemeral"}` を置く。第 1 ブロック(固定指示)は
  その prefix に含まれるので同時にキャッシュされる。
- 可変要素(レビュー対象の artifact)は必ず user message 側に置く。
  system prompt に日時や record id を入れてはならない。
- evaluate はケース数ぶん同一プロファイルで review を回すため、キャッシュ効果が最も大きい。
  **直列実行**とし、1 ケース目のレスポンス受信後に残りを投げる
  (並列にすると全リクエストがキャッシュ未作成のまま走り、書き込みを多重に払う)。
- 効果検証: `--verbose` 時に `usage.cache_read_input_tokens` をログ出力する。

### 5.5 エラー処理

| 事象 | 挙動 |
|------|------|
| `anthropic` 未インストール | 起動時エラー(§2.3) |
| 認証エラー / 4xx | エラーメッセージを stderr に出し終了コード 1。フォールバックしない(ユーザーは LLM レビューを明示要求しているため、黙って heuristic に落とすと結果の性質が変わる) |
| 5xx / 接続エラー | SDK リトライ後も失敗したら上と同じ |
| parse 失敗(スキーマ不一致) | 1 回だけ再リクエスト。再失敗で終了コード 1 |
| `stop_reason == "max_tokens"` | 終了コード 1(切り詰め出力を review として保存してはならない) |

## 6. 学習パイプライン強化(ルール抽出と承認)

### 6.1 現状の問題

現在の `learn` はユーザーが `preference_rules` フィールドに明示的に書いたルールしか
プロファイルに取り込めない。実運用のフィードバックは `notes` の自由記述に判断基準が
埋まっていることが多く、それが失われる(G2)。

### 6.2 抽出フロー

`learn` / `iterate` に `--propose-rules` フラグを追加する(LLM エンジン時のみ有効)。

1. 従来どおり明示フィールド(`preference_rules` 等)を取り込み、DecisionRecord を append。
2. `FeedbackExtractor.extract(...)` を呼ぶ。LLM への入力は
   request / agent_review / user_feedback / 既存ルール一覧(重複検出用、active + retired)。
   出力は `RuleProposalSet`(structured output、§3.2 のスキーマ)。
3. 抽出プロンプトの制約(prompts.py に定義):
   - ユーザーのフィードバックに**実際に書かれている根拠**からのみルール化する。推測での一般化を禁止
   - operation-guide の「良いルール/弱いルール」基準を埋め込み、
     観測可能・具体的な文言を要求する("make it better" 級の提案を禁止)
   - 既存ルールと同義なら `duplicate_of` に既存 id を入れ、新規提案にしない
4. 提案は `status="candidate"`, `source="extracted"`, `source_record_id=<record.id>` で
   プロファイルに追記する。**review では candidate は使われない**(§4 手順 2)。
5. `duplicate_of` 付き提案は新規追加せず、既存ルールの `hit_count` を +1 する
   (同じ判断基準が繰り返し現れた、という実績の記録)。

### 6.3 承認 CLI

```bash
decision-agent rules list   profiles/default.json [--status candidate]
decision-agent rules approve profiles/default.json <rule-id> [--output ...]
decision-agent rules reject  profiles/default.json <rule-id> [--output ...]
decision-agent rules retire  profiles/default.json <rule-id> [--output ...]
```

- `list` は id / status / source / hit・miss / text を表形式(または `--json`)で出す。
- `approve` は candidate → active。`reject` は candidate をプロファイルから削除。
- 反対 polarity の pattern candidate を `approve` しても、既存の反対 entry は
  active のまま残る。置換する場合は既存 entry を別途 `retire` する。
- 対話プロンプトは実装しない(スクリプタブルに保つ。対話はチャット層の仕事)。

### 6.4 known_mistakes の扱い

verdict 不一致からの known_mistake 昇格は現行ロジック(決定的)を維持する。
LLM 抽出はそれを置き換えず、`kind="known_mistake"` の提案として
より良い pattern / correction の**言い換え候補**を出せるのみとする
(採用はやはりユーザー承認)。

## 7. 評価のセマンティックマッチング

### 7.1 現状の問題

`_text_matches_signal` はトークン重複率 0.25 という粗い基準で、
言い換え(例: "concrete pain point is missing" と「具体的な課題提示がない」)を
一致と判定できない。日本語 artifact では特に破綻する(`\w+` トークナイズは
日本語で意味のある分割にならない)。

### 7.2 AgreementJudge(LLM 実装)

`evaluate --engine llm` のとき、一致判定を LLM ジャッジに置き換える。

- 1 ケースあたり 1 回の呼び出しに集約する(core_issues 全件 + revision_direction を
  1 プロンプトで判定させる)。呼び出し回数はケース数 × 2(review + judge)。
- モデル: review と同じ(既定 `claude-opus-4-8`)。判定タスクは軽いが、
  評価数値の信頼性がこのシステムの根幹なのでモデルを落とさない。
- structured output は §2.2 の `AgreementJudgment` と同形の Pydantic モデルとし、
  parse 後にそのまま `AgreementJudgment` へ変換する:

```python
class LLMAgreementOutput(BaseModel):
    core_issue_results: list[LLMCoreIssueResult]  # issue / noticed: bool / evidence: str
    revision_direction_match: bool
    revision_direction_reasoning: str
```

- プロンプト制約: 「エージェントのレビューが、ユーザーの指摘と**同じ問題を**
  指していれば表現が違っても noticed=true。関連するが別の問題なら false」
  という判定基準を明示し、evidence にレビュー中の該当箇所を引用させる。
- heuristic 実装も同じ `AgreementJudgment` を返す(evidence にはマッチした
  テキスト断片、なければ空文字)。両実装が同一の監査契約を満たすため、
  評価レポートの形はエンジンに依らず同じになる。
- evidence / reasoning は `EvaluationCaseResult` に新フィールド
  `agreement_evidence: tuple[str, ...]` として保存する(なぜ一致とされたかを
  ユーザーが検証できるようにする — 評価の評価が可能になる)。

### 7.3 決定性への注意

LLM ジャッジ導入により evaluate は非決定的になる。レポートに
`"judge": "llm:claude-opus-4-8"` を含め、heuristic 判定の数値と混ぜて
時系列比較しないよう明記する。回帰確認用に `--engine heuristic` の評価は常に併用可能。

### 7.4 評価 → プロファイル改善の接続(G5)

`evaluate` の各ケース結果からルール実績を更新・提案する。

- レビューの `violated_rule_id` が付いた issue がユーザー judgment と一致していれば、
  該当ルールの `hit_count` を +1 する**提案**を出す。
- verdict を外したケースで参照された active ルールは `miss_count` +1 の提案。
- `miss_count >= 3 && hit_count == 0` のルールは retire 候補としてレポートの
  `suggested_profile_updates` に載せる。
- いずれも自動適用しない。`evaluate --apply-stats profiles/default.json --output ...` を
  明示指定した場合のみ hit/miss カウントを書き戻す(ルールの追加・削除・status 変更は
  この経路でも行わない)。

### 7.5 heuristic エンジンの日本語対応(LLM 不要経路)

§7.1〜7.4 は `--engine llm` を前提にした解決だが、§1.2 の設計原則 3 が
「LLM なしでも全コマンドが動作する」と定めている以上、既定の `heuristic` エンジンでも
日本語プロファイル・日本語 artifact が最低限機能する必要がある。現状はここが未解決。

**現状の問題:** `review` の判定に使う `_text_similarity` / `_matched_items` /
`_relevant_records` はすべて `\w+` によるトークン化(`engines/heuristic.py` へ
移設後も同じロジック)を土台にしており、空白で分かち書きされない日本語では
文またはフレーズ全体が 1 トークンになる。結果として:

- `known_mistakes` の照合(閾値 0.2)、`preference_rules` / `negative_patterns` の
  照合(閾値 0.34)が、日本語入力では完全一致以外ほぼ発火しない
- `_relevant_records` の履歴類似度ランキングが日本語では機能せず、
  `learned_signals` に載る「使った過去レコード」が実質ランダムになる
- 仕様書(`decision-agent-spec.md`)のレビュー入出力例は日本語だが、
  そのサンプルをそのまま heuristic エンジンに通しても、ルール照合・履歴参照が
  意図どおりに働かない

`--engine llm` を使えばこの問題は AgreementJudge 側では回避できるが、それは
**evaluate の一致判定**に限った話であり、`review` 本体の日本語プロファイル照合
(known_mistakes、preference_rules、negative_patterns、履歴類似度)は
heuristic 経路である限り LLM の有無に関わらず影響を受ける
(`review` の既定エンジンは §2.2 のとおり heuristic のままなので、
API キーを持たないユーザーの主要な利用経路がこれに当たる)。

**設計方針:** `engines/heuristic.py` の文字列比較を、依存ゼロで動く
文字 n-gram Jaccard 係数に置き換える。

```python
def _char_ngrams(text: str, n: int = 2) -> set[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    if len(normalized) < n:
        return {normalized} if normalized else set()
    return {normalized[i : i + n] for i in range(len(normalized) - n + 1)}

def _ngram_similarity(left: str, right: str) -> float:
    left_grams, right_grams = _char_ngrams(left), _char_ngrams(right)
    if not left_grams or not right_grams:
        return 0.0
    return len(left_grams & right_grams) / len(left_grams | right_grams)
```

- 文字 2-gram は言語非依存で、日本語・英語のどちらでも最低限の部分一致を検出できる
  (既存の英語向けトークン一致は特殊ケースとして包含される)。
- `_text_similarity`(`containment` 用途: パターンが本文にどれだけ現れるか)と
  `_ngram_similarity`(対称的な類似度)は用途が異なるため、
  `engines/heuristic.py` 内で別関数として残す。既存の呼び出し箇所
  (known_mistakes 照合 0.2、preference_rules/negative_patterns 照合 0.34、
  履歴類似度、`_text_matches_signal` 0.25)を n-gram 版に差し替えるが、
  各閾値は英語コーパスで調整された値なので、置き換え後に
  `examples/blog-outline-cases.jsonl` 相当の日本語ケースで再チューニングする
  (Phase 2 のテストで検証する)。
- 形態素解析(`sudachipy` 等)への発展は本書のスコープ外とする。
  文字 n-gram は依存ゼロで §1.2 原則 3 を満たす最小限の改善であり、
  単語単位の精度が必要になった場合は `[ja]` extra として別途検討する。

**適用範囲:** この変更は `engines/heuristic.py` 内のプライベート関数の置き換えのみで、
`ReviewEngine` / `AgreementJudge` の外部契約(§2.2)には影響しない。
Phase 1(§11)の「既存ロジックを `engines/heuristic.py` へ移設」の直後、
Phase 2 着手前に行うのが最小コストになる
(移設後に置き換えれば、移設自体は純粋なコード移動のまま検証できる)。

### 7.6 評価の時系列トラッキング

**現状の問題:** 仕様書の成功基準は「反復によりエージェントの判断がユーザーの
判断に近づくこと」だが、`evaluate` は実行のたびにレポートを stdout へ出すだけで、
過去の実行結果を保存・比較する手段がない。運用ガイドは「5〜10 ケース追加ごとに
evaluate を実行する」運用リズムを推奨しているが、precision が改善しているか
悪化しているかを確認する方法が「過去の出力をユーザーが手元に残しているか」に
依存してしまっている。

**設計方針:** `evaluate` に `--history <path>` を追加し、実行結果を
append-only JSONL として記録する。

```bash
decision-agent evaluate profiles/default.json cases/blog_outline_cases.jsonl \
  --records records/blog_outline.jsonl \
  --history evals/blog_outline_evals.jsonl
```

追記される 1 行(`EvaluationRun`)の形:

```python
@dataclass(frozen=True)
class EvaluationRun:
    run_at: str                       # ISO 8601
    profile_fingerprint: str          # "sha256:" + プロファイル正規化 JSON のハッシュ
    cases_fingerprint: str            # "sha256:" + cases ファイル内容のハッシュ
    cases: int
    engine: str                       # "heuristic" | "llm:claude-opus-4-8"
    verdict_accuracy: float
    core_issue_accuracy: float | None
    revision_direction_accuracy: float | None
```

- **fingerprint を持つ理由:** ケースセット自体が変わった run 同士を比較しても
  精度の上下に意味がない(ケースが難化 / 易化しただけかもしれない)。
  `cases_fingerprint` が一致する run だけを時系列として扱う。
  同様に `profile_fingerprint` は「同じプロファイルに対して heuristic /
  llm 両エンジンで評価した」ケースを区別するために使う(§7.3 の注意と整合)。
  フィンガープリントの算出は §5.4 の `rendering.py` の決定的シリアライズを再利用し、
  プロファイルの読み込み順序やキー順に依存しないようにする。
- **レポートへの反映:** `evaluate` の標準出力に `delta_vs_previous` を追加する。
  `--history` で指定したファイルから同一 `cases_fingerprint` かつ同一 `engine` の
  直近 run を探し、`verdict_accuracy` 等の差分を表示する。該当する過去 run が
  なければ `null`(初回実行)。
- **ケース ID の安定性が前提になる:** `EvaluationCaseResult.id` は現行実装だと
  `case.id` が空の場合 `f"case-{index}"` にフォールバックし、行順に依存する。
  ケースファイルに行を追加・並べ替えると同じ artifact が別 ID として扱われ、
  時系列比較や `common_misses` の集計が壊れる。`load_evaluation_cases` は
  `id` が空の行を**警告付きで許容**し(現行の壊れやすい挙動を維持しない)、
  `evaluate --strict` 指定時は `id` 欠落をエラーにする。運用ガイドには
  「cases に追加する行には必ず `id` を振る」ことを明記する。
- **保存先は `--records` と同じ性質(append-only JSONL)** とし、
  `storage.append_evaluation_run(path, run)` を追加する。プロファイルや
  cases ファイルのような「編集可能な現在状態」ではないため、
  atomic write(§9)の対象にはしない(追記のみで上書きしないため)。

## 8. 生成エージェント連携(Revise ループ契約)

Decision Agent 側は「レビュー結果を生成エージェントに返す」ための JSON 契約だけ定義する。
生成側の実装・オーケストレーターの実装は非スコープ。

```text
┌──────────┐  artifact   ┌─────────────────┐
│ Generator │───────────▶│ decision-agent   │
│ (外部)    │◀───────────│   review         │
└──────────┘  revision   └─────────────────┘
      ▲        request            │ verdict == accept → 終了
      └───────────────────────────┘ verdict != accept → 再生成
```

- **入力契約:** 既存の `ArtifactReviewRequest` JSON。生成エージェントは
  `context.revision_of`(前回 artifact の記録 id)と `context.iteration`(回数)を
  付けてよい(context は任意 dict なので互換)。
- **出力契約:** 既存の `ArtifactReview` JSON。オーケストレーターは
  `revision_instruction` をそのまま次の生成プロンプトに渡すことを想定する。
  そのため LLM エンジンのプロンプトで revision_instruction を
  「生成エージェントへの単一の指示文として実行可能な形」で書かせる。
- **停止条件はオーケストレーター側の責務**(推奨: accept / 最大 N 回 / ユーザー中断)。
  Decision Agent は判断のみ返す。
- CLI はステートレスな `review` をそのまま使えるため、新コマンドは追加しない。
  docs/operation-guide.md にループ例(シェルスクリプト)を追記する。

## 9. CLI 変更一覧

### 9.1 実装済み CLI

```text
review   <profile> <request> [--records F] [--engine {heuristic,llm}]
learn    <profile> <request> <review> <feedback> --output F
         [--records F] [--engine {heuristic,llm}]
iterate  <profile> <request> --feedback F --records F --output F
         [--engine {heuristic,llm}]
evaluate <profile> <cases> [--records F] [--engine {heuristic,llm}]
rules list <profile> [--status {active,candidate,retired}] [--json]
rules {approve,reject,retire} <profile> <rule-id> [--output F]
migrate-history <old-profile> --records F [--output F]
decide / train   # 既存のまま(凍結)
```

- `--engine` 既定は `heuristic`。環境変数 `DECISION_AGENT_ENGINE` でも指定可
  (CLI フラグが優先)。
- `learn` は既に作成済みの review を記録するだけなので Gateway を呼ばない。
  `--engine` は値の検証にのみ使う。
- `evaluate --engine llm` はケースのレビュー生成に LLM を使うが、
  一致判定は現在も heuristic `AgreementJudge` を使う。
- `rules approve/reject/retire` で `--output` 省略時は入力プロファイルを上書きする
  (この 3 コマンドは編集が目的なので in-place を既定とする)。
- `migrate-history` は §3.5 の一回限りの移行コマンド。旧プロファイル内の
  `decision_records` を `--records` の JSONL へ追記し、`decision_records` を
  持たないプロファイルを `--output`(省略時は入力を上書き)に書き出す。
- **プロファイルの書き込みは常に原子的に行う。** `storage._save_json` を
  「同一ディレクトリの一時ファイルに書いてから `os.replace` で差し替える」実装に
  変更する(in-place 上書き時に書き込みが中断されてもプロファイルが
  切り詰められない。`os.replace` は同一ファイルシステム内でアトミック)。
  これは rules コマンドに限らず `save_profile` 全経路に適用する。
  `learn` / `iterate` は §3.5 の書き込み順序(JSONL 追記 → プロファイル保存)を守る。

### 9.2 未実装の設計案

`--model`、`--verbose`、`--propose-rules`、`evaluate --history`、
`--apply-stats`、`--strict` は現行 CLI に存在しない。モデル選択は Gateway 側の
ポリシーに移管したため `--model` は追加しない。その他は対応する機能を実装する
場合に、改めて CLI 契約を確定する。

## 10. テスト戦略

現在の自動テストは `tests/test_agent.py` に集約し、次を回帰対象とする。

1. heuristic レビューの決定性、日本語／混在テキストの文字 n-gram 照合、
   関連履歴の選別。
2. JSONL 履歴の追記と重複抑止、旧プロファイル履歴の移行、不正な評価ケースの
   fail-fast。
3. candidate の反復昇格、active ルールとの矛盾、approve/reject/retire、
   hit/miss と disagreement flag。
4. `learn` / `iterate` の非対話性、原子的なプロファイル保存、旧形式データの
   後方互換。
5. Gateway HTTP を Fake 注入した LLM エンジン単体テスト。inference/coding
   endpoint の選択、idempotency、polling、timeout/cancel、認証・タスク失敗、
   `structuredOutput` の検証を含み、通常のテストでは実ネットワークを使わない。

標準の検証コマンド:

```bash
PYTHONPATH=src python -m unittest discover -s tests
uv run pyright
```

実 Gateway のスモークテストは CI 外で行う。Gateway の `/readyz`、owner token、
専用 `CODEX_HOME` の認証を確認後、README の `review --engine llm` 例を実行する。

## 11. 実装フェーズ分割

当初の Phase 1〜3 のうち、次は実装済みである。

- engine 抽象化と heuristic ロジックの分離
- JSONL を履歴の唯一の Source of Truth（プロファイル埋め込みを廃止、`migrate-history` で移行）
- 構造化ルール、候補昇格、矛盾フラグ、rules CLI
- 日本語／混在テキストの文字 n-gram 照合
- Gateway V2 inference API を使う LLM レビュー

当初案から変更した点:

- LLM は Anthropic SDK 直接呼び出しではなく local-agent-gateway に委譲した。
- `[llm]` extra、`prompts.py`、`rendering.py`、`--model` は導入していない。
- 評価履歴、LLM AgreementJudge、自由記述からの LLM ルール抽出は未実装。

次の実装単位は、実データで優先度を確認してから独立に進める。

1. 自由記述フィードバックからの candidate ルール提案。
2. semantic AgreementJudge と、heuristic 評価との指標分離。
3. 評価履歴と同一ケース集合に対する時系列差分。
4. 生成エージェントとの revise-loop オーケストレーション。

### 見送り(将来課題として明記)

- 埋め込みベースの履歴検索(JSONL が数千件を超えたら再検討)
- 評価ケースの自動生成

## 12. 設計判断の記録(ADR 要約)

### 12.1 現在採用している判断

| 判断 | 理由 |
|------|------|
| 既定エンジンを heuristic のままにする | 「API キー不要で動く」という現在の性質を破壊しない。LLM はオプトイン |
| LLM 失敗時に heuristic へ自動フォールバックしない | レビュー品質の性質が黙って変わると、JSONL に混在した記録の解釈が壊れる |
| LLM transport を Gateway に委譲する | 認証・ポリシー・監査・provider/model 選択を Decision Agent から分離し、Python 依存ゼロを保つ |
| 明示フィードバック由来の candidate を反復で自動昇格する | 同一パターンが別レコードで 2 回以上現れたことを、active 化の最小証拠とする |
| 矛盾検出を限定的に扱う | known-mistake の verdict 競合と positive/negative の同一パターンだけを検出する。preference rule 間の意味的矛盾は未検出 |
| evaluate の一致判定は heuristic のままにする | LLM ReviewEngine を選んでも、現行の AgreementJudge は決定的な heuristic 実装だけである |
| rules コマンドは非対話 | スクリプタブルに保つ。対話 UI は将来のチャット層の責務 |

### 12.2 将来案・不採用案

- 自由記述からの LLM ルール抽出を実装する場合、抽出結果は candidate とし、
  自動採用しない。
- semantic AgreementJudge は将来案であり、導入時には heuristic 評価と指標を
  混在させない。
- Anthropic SDK 直接呼び出し、Pydantic 出力モデル、Decision Agent 側の prompt
  caching と直列 evaluate は不採用になった歴史的案である。現行の Gateway 実装の
  要件ではない。
