# Swallow - 英語リスニング学習アプリ

## 概要
Instagram風UIの英語リスニング学習アプリ。先生の動画をショート動画形式で視聴し、クイズ・復習・ストリーク管理で学習を継続できる。

**本番URL**: https://swallow-up.vercel.app

---

## 技術構成
| 項目 | 内容 |
|------|------|
| フロントエンド | 単一HTMLファイル（`index.html`）、バニラJS、CSS |
| ホスティング | Vercel（静的サイト） |
| データ保存 | Firestore（ログイン時） + localStorage（フォールバック） |
| 認証 | Firebase Authentication（Googleログイン） |
| App ID | `com.masaenglishcompany.swallow` |

---

## ファイル構成
```
swallow/
├── index.html              # メインアプリ（全UI/JS/CSS含む）
├── vercel.json              # Vercelデプロイ設定
├── README.md                # このファイル
├── content-pipeline.md      # コンテンツ自動量産パイプライン仕様（詳細）
├── manual.html              # アプリ化手順マニュアル（Step 1〜8）
├── spec.html                # コンテンツパイプライン実装仕様書
├── 河野さんへの依頼.html      # iOSアプリ化依頼書（Step 7〜8）
├── docs/index.html          # アプリ化手順書（Step 1〜23）
├── masa_avatar.png          # 先生アバター画像
├── swallow_icon.png         # アプリアイコン
├── *.MOV                    # 動画ファイル（.gitignore対象）
└── .gitignore
```

---

## 実装済み機能

### コア機能
- ショート動画形式のレッスン（上下スワイプ / ホイールで切替）
- 先生ごとのフレーズ管理（まさ・みき・まさき）
- クイズ形式（4択「何が聞こえましたか？」）+ 解答表示 + 解説パネル
- 先生プロフィール画面（IGスタイル）
- フォロー / 非表示機能（localStorage永続化）
- コメント機能（AI自動返信付き）
- 学習履歴画面 — ステータス切替（聞き取れた / 要復習 / 保存）
- オンボーディング（ヒアリング → スコアに基づく先生の自動フォロー）
- スプラッシュ画面アニメーション
- Googleログイン（Firebase Authentication）
- Firestore連携（端末間データ同期）
- localStorage → Firestore 自動マイグレーション（初回ログイン時）

### UI/機能改善（2025/02/27 実装）

| # | 改善内容 | 詳細 |
|---|---------|------|
| 1 | ストリーク | localStorageで日付追跡、連続日数を計算しホーム画面に表示 |
| 2 | 学習カウント | `reviewData.length` と `phrases.length` から動的計算 |
| 3 | フレーズ数設定 | 1/3/5/8の設定が実際に動作。フォロー中先生からラウンドロビン選択。永続化 |
| 4 | ミュート保存 | localStorageに保存。レッスン開始時の強制ミュート解除を廃止 |
| 5 | クイズ日本語化 | `What did you hear?` → `何が聞こえましたか？` |
| 6 | データリセット | 設定画面にリセットボタン追加（confirm付き） |
| 7 | ローディング | 動画読み込み中にスピナー表示。canplayで非表示、5秒フォールバック |
| 8 | フォロー永続化 | teachers の following 状態を localStorage に保存/復元 |
| 9 | 非表示永続化 | hiddenTeachers を localStorage に保存/復元 |
| 10 | 自動フォロー | ヒアリング完了時にスコア上位の先生を自動フォロー |

### localStorage キー一覧
| キー | 用途 |
|------|------|
| `swallow_hearing_done` | ヒアリング完了フラグ + 回答データ |
| `swallow_review_data` | 学習履歴（JSON配列） |
| `swallow_streak` | ストリークデータ（count, lastDate） |
| `swallow_muted` | ミュート状態 |
| `swallow_daily_count` | 1日のフレーズ数設定 |
| `swallow_following` | 先生のフォロー状態 |
| `swallow_hidden` | 非表示の先生 |
| `swallow_daily_YYYY-M-D` | 当日の学習完了フラグ |

---

## コンテンツ量産パイプライン

> 詳細は `content-pipeline.md` / `spec.html` を参照

### フロー
```
先生が10分動画を撮影
  → Whisper API（文字起こし + タイムスタンプ）
  → ffmpeg（フレーズごとに動画分割、MOV → MP4 軽量化）
  → Claude API（日本語訳・解説・4択クイズ・例文を自動生成）
  → Google Spreadsheet に自動登録
  → Masaさんが確認・修正
  → アプリに反映
```

**10分の撮影 → 20〜30レッスンカード自動生成**

### 必要なAPI
| API | 用途 | 月額目安（100フレーズ） |
|-----|------|----------------------|
| OpenAI Whisper | 音声文字起こし | 約30円 |
| Claude API | 解説・クイズ生成 | 約45円 |

### 使い方
```bash
cd pipeline
python process_video.py input/masa_recording.MOV --teacher masa
```

### 撮影ルール（Masaさん向け）
- スマホ縦向き固定
- フレーズ → 2秒以上の間 → 次のフレーズ
- 言い直しOK、日本語混じりOK（Whisperが英語だけ抽出）
- 1回10分で20〜30フレーズが目安

---

## iOSアプリ化

> 詳細は `manual.html` / `docs/index.html` / `河野さんへの依頼.html` を参照

### 方針
- Capacitor でWebアプリをiOSネイティブアプリ化
- Step 1〜6（Capacitorセットアップ）はMasaさん側で対応
- Step 7〜8（Xcode署名・App Store提出）は河野さんに依頼

### 河野さんへの依頼事項
- **Step 7**: Xcode での署名設定、Bundle ID確認、実機ビルド・動作確認
- **Step 8**: Archive → App Store Connect へのアップロード

### 必要なもの（河野さん側）
- Mac + Xcode
- Apple Developer アカウントへのアクセス権限
- 実機 iPhone

---

## 次の開発予定

### パイプライン Phase 2〜4

| Phase | 内容 |
|-------|------|
| Phase 2 | スプレッドシート → アプリ自動反映（GAS JSON API） |
| Phase 3 | 動画のクラウドホスティング（Cloudflare R2 / Vercel Blob） |
| Phase 4 | Webベースの管理画面（フレーズの追加・編集・プレビュー） |

---

## デプロイ

### Vercel（Webアプリ）
```bash
cd swallow
vercel --yes --prod
```
- プロジェクト名: `swallow-up`
- ビルド不要（静的ファイル配信）

---

## 担当分け
| 担当 | やること |
|------|---------|
| Masaさん | 動画撮影、生成コンテンツの確認・修正、アプリの方針決定 |
| 健人さん | パイプライン構築・運用、Firebase実装、アプリ開発 |
| 河野さん | iOSアプリのXcode署名・App Store提出 |
