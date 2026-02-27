# Swallow - 英語学習アプリ

## 概要
Swallowは、Instagram風UIの英語リスニング学習アプリ。先生ごとの動画フレーズをショート動画形式で学習し、クイズ・復習・ストリーク管理などの機能を備える。

## 技術構成
- **フロントエンド**: 単一HTMLファイル（`index.html`）、バニラJS、CSS
- **デプロイ**: Vercel（静的サイト）
- **データ保存**: localStorage（現状）
- **本番URL**: https://swallow-up.vercel.app

## デプロイ方法
```bash
cd swallow
vercel --yes --prod
```

---

## 実装済み機能

### コア機能
- ショート動画形式のレッスン（上下スワイプ / ホイールで切替）
- 先生ごとのフレーズ管理（まさ・みき・まさき）
- クイズ形式（4択）+ 解答表示 + 解説パネル
- 先生プロフィール画面（IGスタイル）
- フォロー / 非表示機能
- コメント機能（AI自動返信付き）
- 学習履歴（レビュー画面）- ステータス切替（聞き取れた / 要復習 / 保存）
- オンボーディング（ヒアリング → おすすめ先生）
- スプラッシュ画面アニメーション

### 2025/02/27 実装: UI/機能改善（10項目）

#### 1. ストリーク（連続学習日数）
- localStorage で日付を追跡、連続日数を計算・表示
- レッスン完了時に `updateStreak()` で更新
- ホーム画面の `#streakNumber` に動的表示

#### 2. 学習済み/残りカウント
- ハードコード値を撤廃
- `reviewData.length`（学習済み）と `phrases.length - reviewData.length`（残り）で動的計算

#### 3. フレーズ数設定（1/3/5/8）
- 設定で選択した `dailyCount` に従い、フォロー中の先生からラウンドロビンで選択
- `dailyCount` を localStorage に永続化
- 設定画面の選択状態も起動時に復元

#### 4. ミュート状態の保存
- localStorage に保存
- `startLesson()` / `startSingleLesson()` / `startReviewLesson()` での強制ミュート解除を削除
- ユーザーの選択を尊重

#### 5. クイズ質問の日本語化
- `What did you hear?` → `何が聞こえましたか？`（全箇所）

#### 6. データリセット機能
- 設定画面に「学習データをリセット」ボタン追加
- `confirm()` で確認後、全 localStorage データをクリア
- ストリーク、学習履歴、フォロー状態、ヒアリング結果すべて初期化

#### 7. 動画ローディングインジケーター
- 動画読み込み中にCSSスピナーを表示
- `canplay` イベントで非表示
- 5秒フォールバックタイマー付き

#### 8. フォロー状態の永続化
- `localStorage` で `teachers` の `following` 状態を保存/復元
- `toggleFollow()` 時に自動保存

#### 9. 非表示先生の永続化
- `localStorage` で `hiddenTeachers` を保存/復元
- `hideTeacher()` 時に自動保存

#### 10. ヒアリング結果に基づくデフォルトフォロー
- `completeHearing()` でスコア上位の先生を自動フォロー
- ヒアリングの目的・レベルに合った先生を推薦

---

## 次の開発予定: Googleログイン + Firestore連携

### 目的
- ユーザー認証によるアクセス制御
- 端末をまたいだ学習データの同期（クラウド保存）

### 技術スタック
- **Firebase Authentication**: Googleログイン
- **Cloud Firestore**: 学習データのクラウド保存

### 実装計画

#### Firebase セットアップ（手動）
1. [Firebase Console](https://console.firebase.google.com/) でプロジェクト作成（`swallow-app`）
2. ウェブアプリ追加 → Firebase設定情報（apiKey, authDomain等）を取得
3. Authentication → Google ログインプロバイダを有効化
4. Firestore Database → `asia-northeast1`（東京）で作成（テストモード）

#### フロントエンド実装
1. **Firebase SDK読み込み**（CDN）
   - `firebase-app.js`
   - `firebase-auth.js`
   - `firebase-firestore.js`

2. **ログイン画面追加**
   - アプリ起動時に認証状態チェック
   - 未ログインならログイン画面表示（Googleログインボタン）
   - ログイン済みならホーム画面へ

3. **データ同期**
   - 現在の localStorage ベースの保存を Firestore に移行
   - 保存対象:
     - ストリークデータ（`streak`）
     - 学習履歴（`reviewData`）
     - フォロー状態（`following`）
     - 非表示先生（`hiddenTeachers`）
     - ミュート設定（`muted`）
     - フレーズ数設定（`dailyCount`）
     - ヒアリング結果（`hearing`）
   - Firestoreパス: `users/{uid}/settings`, `users/{uid}/reviews`

4. **ログアウト機能**
   - 設定画面にログアウトボタン追加

#### Firestoreセキュリティルール
```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId}/{document=**} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

### 認証フロー
```
アプリ起動
  → Firebase Auth 状態チェック
  → 未認証 → ログイン画面（Googleボタン）
           → Google認証ポップアップ
           → 成功 → Firestoreからデータ読み込み
                   → ホーム画面表示
  → 認証済み → Firestoreからデータ読み込み
             → ホーム画面表示
```

---

## ファイル構成
```
swallow/
├── index.html          # メインアプリ（全UI/JS/CSS含む）
├── vercel.json          # Vercelデプロイ設定
├── README.md            # このファイル
├── masa_avatar.png      # 先生アバター画像
├── masa1.MOV            # 動画ファイル
├── masa2.MOV
├── masa3.MOV
├── miki1.MOV
├── miki2.MOV
├── masaki1.MOV
├── masaki2.MOV
├── masaki3.MOV
└── .vercel/             # Vercelプロジェクト設定
```

## localStorage キー一覧
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
