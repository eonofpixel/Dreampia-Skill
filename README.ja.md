<div align="center">

<img src="docs/assets/dreampia-hero-banner.svg" alt="Dreampia-Skill Hero Banner" width="100%" />

<br/>

**[🇺🇸 English](README.md)** | **[🇰🇷 한국어](README.ko.md)** | **[🇯🇵 日本語](README.ja.md)** | **[🇨🇳 简体中文](README.zh-CN.md)**

<br/>

[![Version](https://img.shields.io/badge/version-1.0.0-0ea5e9?style=for-the-badge)](package.json)
[![License](https://img.shields.io/badge/License-Apache_2.0-8b5cf6?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-10b981?style=for-the-badge&logo=python&logoColor=white)](pyproject.toml)
[![MCP Tools](https://img.shields.io/badge/MCP_Tools-23_Ready-f59e0b?style=for-the-badge)](harness/mcp_server.py)
[![Zero Warnings](https://img.shields.io/badge/Self_Audit-70_Files_0_Warnings-22c55e?style=for-the-badge)](harness/autopilot_engine.py)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero_(Stdlib_Only)-ec4899?style=for-the-badge)](pyproject.toml)

**プロンプト高度化ブリーフィング（`sharpen` + ソクラテス式逆質問 + 次の推奨アクション）、SDD + TDD 実行、2-Tier クリーンルーム・リバースエンジニアリング（内蔵パーサー + 外部ブースター）、自律メトリクス登攀（Metric-Climb）、影響範囲（Blast-Radius）解析、統合オートパイロットを1つにまとめた6大ホスト対応エージェントハーネス**

</div>

---

## ✨ なぜ Dreampia-Skill なのか？

一般的なAIコーディングアシスタントは、短いプロンプトを浅く解釈してエッジケースを漏らしたり、実行証拠なしに完了を主張したり、外部リバースエンジニアリングツールの導入失敗で停止しがちです。**Dreampia-Skill** は Dreampia 独自のクリーンルーム設計（**Apache-2.0**）による外部依存ゼロ（Python 3.9+ 標準ライブラリのみ）のハーネスであり、**Antigravity、Claude Code、Cursor、Codex、OpenCode、Gemini CLI** の6大AIホストへワンコマンドで導入できます。

1. **🧠 可視化プロンプト高度化 & ソクラテス式要件インタビュー (`expand-prompt` / `sharpen` / `next-actions`)**: 短いリクエストから即座にコーディングを始めるのではなく、SOLID 5原則・`any` 禁止・戻り値型明記・UI規約（`bg-transparent` ボタン、`lucide-react` アイコン）・防御的エッジケース・**Sage のソクラテス式事前確認質問3選**・**次の推奨アクション（Next Actions）**を自動生成して提示します。
2. **🔬 2-Tier クリーンルーム・リバースエンジニアリング & インストールプランナー (`reconstruct-doctor` / `reconstruct-spec`)**:
   - **Tier 1（外部依存ゼロ内蔵エンジン）**: 外部バイナリなしで `PE/ELF/Mach-O/WASM/ASAR/APK/ZIP/Source` のヘッダーと公開シンボルを即座に解析し、3領域分離（`contaminated-zone` / `approved-spec` / `implementation`）と再構築義務台帳（`Obligation Ledger`）100% カバレッジを強制します。
   - **Tier 2（外部ブースター自動連携 & インストールプランナー）**: OSパッケージマネージャー（`winget`, `scoop`, `choco`, `brew`, `apt-get`）を自動検出し、`rizin`, `jadx`, `ghidra`, `wasm2wat`, `objdump`, `nm`, `adb` のオプトインCLIインストール（`--install-tool <id|all> [--apply]`）と5秒タイムアウト保護付きの深層シンボル統合を提供します。
3. **⚔️ ファンタジーRPG主人公（Hero）＆ギルドパーティ & 13種類のマジック短縮コマンド**: ユーザーを主人公 **`Hero`** とし、`GuildMaster` 指揮の下、`Sage`, `Archmage`, `Bard`, `Paladin`, `Inquisitor`, `Cleric`, `Guardian`, `Alchemist`, `Archer` が連携し、13個の短縮キーワード（`sharpen`, `ulw`, `loop`, `climb`, `blast`, `interrogate`, `unslop`, `btw`, `sdd`, `tdd`, `re`, `audit`, `ui`）で起動します。
4. **🛡️ 100% セルフ・ドッグフーディング（全70ファイル・警告0件）**: 自身の静的ASTコード監査（`audit-code --project .`）において **全70ファイル・ブロッキング欠陥0件・警告0件（`findings: []`）** を達成しています。

---

## ⚡ 10秒ワンクリック・インストール（Windows / macOS / Linux 対応）

仮想環境（`venv`）や `pip install` は一切不要です。以下のいずれかの方法で即座に導入できます。

### 方法 1. `npx` ゼロクローン・グローバルセットアップ（推奨 ⭐）
ターミナル（Windows PowerShell または macOS / Linux）で以下の1行を実行すると、PC内の全AIホストのグローバルスキル経路と `dreampia-skill` MCPサーバーが自動登録されます：

```bash
npx github:eonofpixel/Dreampia-Skill setup --apply
```

### 方法 2. AIアシスタントに1行コピペでインストールさせる
お使いのAIチャット（Antigravity、Claude Code、Cursor、Codex、OpenCode、Gemini CLI）に以下の文をそのまま貼り付けてください：

> ```text
> https://github.com/eonofpixel/Dreampia-Skill をクローンし、python -m harness.team_cli setup --apply を実行して Dreampia-Skill と MCP サーバーをグローバルインストールしてください。
> ```

### 方法 3. 各ホストのネイティブプラグインコマンド & 手動クローン

| AI ホスト | ワンライナー・コマンド |
| :--- | :--- |
| **Claude Code** | `/plugin marketplace add eonofpixel/Dreampia-Skill` &#8594; `/plugin install dreampia-skill` |
| **Cursor** | `/add-plugin https://github.com/eonofpixel/Dreampia-Skill` (`.cursor-plugin/plugin.json` 対応) |
| **Gemini CLI** | `gemini extensions install https://github.com/eonofpixel/Dreampia-Skill` |
| **Git Clone (Windows / macOS)** | `git clone https://github.com/eonofpixel/Dreampia-Skill.git && cd Dreampia-Skill && python -m harness.team_cli setup --apply` |

---

## 🚀 13種類のマジック・プロンプト短縮コマンド

プロンプトの先頭や文中に以下の短縮キーワードを含めるだけで、専用パイプラインが即座に起動します：

| 短縮コマンド | 韓国語エイリアス | 起動するモードとパイプライン | プロンプト例 |
| :---: | :---: | :--- | :--- |
| **`sharpen`** / `boost` | `고도화`, `구체화`, `생각` | **プロンプト深層高度化 + ソクラテス式インタビュー質問3選**<br/>曖昧な指示を精密な仕様・エッジケース・逆質問・次の推奨アクションに拡張 | `"sharpen 決済ボタンを作って"` |
| **`ulw`** / `ultrawork` | `풀가동`, `오토파일럿` | **全ギルドパーティ稼働 + 統合 Autopilot Gate**<br/>強制 `controlled` プロファイル + 全段階検証をワンストップ実行 | `"ulw 認証モジュールをリファクタリングしてJWTローテーションを追加"` |
| **`loop`** / `until-pass` | `루프`, `완주`, `끝까지` | **自己修復 Pass/Fail ループ**<br/>テストと静的コード監査のブロッカーが `0` になるまで自動再試行 | `"loop 決済Webhookの失敗しているテストをすべて修正して"` |
| **`climb`** / `hillclimb` | `성능등반`, `자율실험` | **自律メトリクス登攀 (`metric-climb`)**<br/>不変評価ガード + SHA-256 重複排除 + モンテカルロ有意性検定 + TSV台帳 | `"climb パーサーのレイテンシを5ms以下に最適化して"` |
| **`re`** / `cleanroom` | `역설계`, `클린룸` | **2-Tier クリーンルーム・リバースエンジニアリング**<br/>Tier 1/2 静的解析 &#8594; 3領域分離 &#8594; 義務台帳 & Golden I/O 100% 検証 | `"re レガシーバイナリを解析してクリーンルーム再実装して"` |
| **`blast`** | `폭발반경`, `영향도` | **影響範囲解析 (`blast-radius`) & 5段階安全証明**<br/>1-Hop/2-Hop 呼び出し元追跡、システム境界交差、安全証明レベル算出 | `"blast route_planner.py 変更の影響範囲を検証して"` |
| **`interrogate`** | `심문`, `적대적리뷰` | **多角的・敵対的差分レビュー**<br/>Archmage・Inquisitor・Guardianの視点から同時にエッジケース欠陥を検証 | `"interrogate このPRの差分を厳格にレビューして"` |
| **`unslop`** / `deslop` | `군더더기제거`, `슬롭제거` | **AIスロップ除去サニタイザー**<br/>例外を握り潰す `bare except: pass` や偽アサーション、冗長コメントを除去 | `"unslop 新しいサービス層の冗長なコードを整理して"` |
| **`btw`** | `잠깐`, `빠르게` | **コンテキスト汚染ゼロのサイドリサーチ**<br/>ファイルを一切変更せず `Sage` が即座に調査・回答 | `"btw ルーター設定ファイルがどこにあるか教えて"` |
| **`sdd`** | `명세`, `설계` | **仕様駆動開発 (`sdd-ledger` / `sdd-check`)**<br/>`PRD-R*` &#8594; `TASK-*` &#8594; `TEST-*` 双方向トレーサビリティ台帳検証 | `"sdd マルチテナント課金APIの仕様書から設計して"` |
| **`tdd`** | `티디디` | **テスト駆動開発**<br/>失敗する実アサーションテスト作成 &#8594; 最小実装 &#8594; リファクタリング | `"tdd レートリミッター・ミドルウェアを実装して"` |
| **`audit`** | `감사`, `보안점검` | **Inquisitor 静的 AST コード監査 (`audit-code`)**<br/>SOLID原則、`any` 禁止、戻り値型明記、スロップ検出、ボタン/アイコン規約検査 | `"audit リポジトリ全体のSOLID原則とUIルール違反をチェック"` |
| **`ui`** | `화면`, `디자인` | **UI/UX 実装 & 視覚受入検証 (`visual-check`)**<br/>`bg-transparent` ボタン・`lucide-react` アイコン強制とPNGピクセル差分検証 | `"ui ダークモード対応のリアルタイム売上ダッシュボードを作成"` |

---

## 🔬 2-Tier クリーンルーム・リバースエンジニアリング (`reconstruct-doctor`)

```bash
# 1. OSパッケージマネージャー（winget/scoop/brew/apt）と Tier 1 & Tier 2 ツールの状態を診断
python -m harness.team_cli reconstruct-doctor

# 2. 未導入の Tier 2 外部ブースター（rizin, jadx, ghidra, wasm2wat, objdump, nm, adb, all）のインストール計画をプレビュー
python -m harness.team_cli reconstruct-doctor --install-tool rizin,jadx

# 3. CLIでのオプトイン・インストールを実行（--apply 指定時のみ実行）
python -m harness.team_cli reconstruct-doctor --install-tool rizin,jadx --apply
```

---

## 🛡️ 主要パイプライン CLI コマンド（セルフ・ドッグフーディング対応）

```bash
# 1. プロンプト高度化 & ソクラテス式インタビュー質問生成
python -m harness.team_cli expand-prompt --project . --goal "sharpen 決済ボタンを作って"

# 2. Inquisitor 静的 AST コード監査（全70ファイル・ブロッキング0件・警告0件）
python -m harness.team_cli audit-code --project .

# 3. 1-Hop/2-Hop 影響範囲（Blast Radius）と5段階安全証明解析
python -m harness.team_cli blast-radius --project . --target harness/route_planner.py

# 4. 長期セッションの文脈維持用コンテキストパック生成
python -m harness.team_cli context-pack --project . --goal "クリーンルームエンジンの高度化"

# 5. 統合オートパイロット・ゲート
python -m harness.team_cli autopilot-gate --project . --allow-doc-only

# 6. プロジェクト自己学習メモリ登録（以降の audit-code と expand-prompt に自動反映）
python -m harness.team_cli learn-rule --project . --rule "金額計算での float 使用禁止" --forbidden-regex "\bfloat\s*\(" --apply

# 7. Sage インタビュー回答 ➔ SDD 3種仕様書（PRD/BACKLOG/TEST_PLAN）と台帳を自動生成
python -m harness.team_cli interview-compile --project . --goal "決済ボタン作成" --answers "1440px,トースト通知,0.01" --apply

# 8. クリーンルーム仕様書（00_CLEANROOM_SPEC.md）+ Golden I/O ベクトル草案の自動合成
python -m harness.team_cli reconstruct-spec --project . --source contaminated-zone --apply

# 9. Git Worktree ベースの並列ギルドパーティ（Paladin/Archer/Inquisitor）隔離ワークスペース編成
python -m harness.team_cli squad-worktree --project . --mode plan --goal "大規模決済リファクタリング"

# 10. プロジェクト状態に基づく次の推奨アクション（Next Actions 1〜3位）ガイド
python -m harness.team_cli next-actions --project . --goal "決済ボタン作成"
```

---

## 🔌 23種類のネイティブ MCP サーバーツール (`harness/mcp_server.py`)

`setup --apply` 実行時、MCP対応IDEやエージェントから直接呼び出せる **23個の標準MCPツール** が登録されます：

| カテゴリ | MCP ツール名 | 説明 |
| :--- | :--- | :--- |
| **プロンプト高度化 & ルーティング** | `dreampia_expand_prompt` | 短い目標をエンジニアリングプロンプト、制約条件（学習済みルール含む）、エッジケース、ソクラテス式逆質問3選、次の推奨アクション（`echo_markdown_ko`）に拡張 |
| | `dreampia_next_actions` | プロジェクト状態（Git、SDD仕様/台帳、クリーンルーム、監査結果、学習ルール）を解析し、1〜3位の次の推奨アクションと短縮プロンプト・CLIコマンドを案内 |
| | `dreampia_interview_compile` | 目標（`goal`）とインタビュー回答（`answers`）から `PRD-R*`、`TASK-*`、`TEST-*` 仕様書と SDD 台帳を自動生成 |
| | `dreampia_route_plan` | 13種類のマジック短縮コマンドを解析し、最適クエストランク・ギルドパーティ編成・必須ゲートを算出 |
| | `dreampia_router_discover` | システム内で利用可能なマルチエージェントハーネスCLIとスキル同期状態を探索 |
| | `dreampia_squad_worktree` | `Paladin`・`Archer`・`Inquisitor` 並列ギルドパーティ用の隔離 Git Worktree を計画（`plan`）・作成（`create`）・整理（`cleanup`） |
| **2-Tier クリーンルーム RE** | `dreampia_reconstruct_doctor` | Tier 1 & Tier 2 リバースエンジニアリングツールの診断とオプトイン自動インストール（`install_tool`, `apply`） |
| | `dreampia_reconstruct_inspect` | `PE/ELF/Mach-O/WASM/ASAR/APK/ZIP/Source` の構造および Tier 1 + Tier 2 深層シンボルの静的解析 |
| | `dreampia_reconstruct_spec` | アーティファクト解析と義務台帳からクリーンルーム仕様書（`00_CLEANROOM_SPEC.md`）と `golden-io.json` 草案を自動合成 |
| | `dreampia_reconstruct_ledger` | 参照領域（`contaminated-zone`）から再構築義務台帳（`Obligation Ledger`）を導出・保存 |
| | `dreampia_reconstruct_verify` | 再構築義務台帳に対する実装（`implementation`）の100%カバレッジと3領域非汚染境界を検証 |
| | `dreampia_reconstruct_compare` | 参照元と再構築対象の公開シンボル・ルート・IPCチャネルの一致率（`Parity Ratio`）を比較 |
| | `dreampia_golden_io` | `approved-spec/golden-io.json` の入出力ベクトルに基づくブラックボックス同等性検証 |
| **オートパイロット & 静的監査** | `dreampia_autopilot_gate` | 指針同期、SDD+TDD、コード監査、クリーンルーム/Golden I/O/視覚受入の統合判定書を発行 |
| | `dreampia_audit_code` | Inquisitor 静的 AST 監査（偽テスト、`any` 禁止、戻り値型明記、スロップ遮断、`bg-transparent` ボタン、`lucide-react` アイコン、自己学習正規表現） |
| | `dreampia_learn_rule` | プロジェクト固有の教訓・禁止正規表現（`forbidden_regex`）を `.dreampia/memory/project-rules.json` に永続化 |
| | `dreampia_blast_radius` | 変更ファイルの 1-Hop/2-Hop 呼び出し依存関係、システム境界交差、5段階安全証明レベルを算出 |
| | `dreampia_metric_climb` | 不変評価ガード、SHA-256 重複排除、モンテカルロ有意性検定に基づく自律メトリクス登攀エンジン |
| | `dreampia_context_pack` | 長期セッションの文脈維持用・超圧縮アーキテクチャ＆未完了タスクパケットをコンパイル |
| **SDD & 視覚・品質ゲート** | `dreampia_sdd_ledger` | `PRD-R*`、`REQ-*`、`TASK-*`、`TEST-*` の双方向トレーサビリティ台帳（`evidence/sdd-ledger.json`）を生成 |
| | `dreampia_sdd_check` | 孤立要件、仕様ドリフト（`STALE`）、実TDDテストコードの存在を Fail-Closed で検証 |
| | `dreampia_visual_check` | UI 視覚受入マニフェストおよび PNG スクリーンショットの解像度・ビューポート予算・ピクセル差分率を検証 |
| | `dreampia_verify_gate` | 段階別品質ゲート（`before-dev-start`, `before-claim-complete`, `before-client-send`, `app-static`, `ui-evidence`）を検証 |

---

## 📜 ライセンス (Apache License 2.0)

本プロジェクトは **[Apache License 2.0](LICENSE)** の下で公開されています。特許権の明示的な許諾（第3条）および再配布時の帰属表示保護（第4条）が含まれます。詳細は [LICENSE](LICENSE) および [NOTICE](NOTICE) をご参照ください。
