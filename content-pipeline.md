# Swallow コンテンツ自動量産パイプライン — 実装ガイド

## 概要

先生が動画を撮影するだけで、英会話レッスンカードを自動生成するシステム。

```
先生が10分動画を撮影
    ↓
Whisper API（文字起こし + タイムスタンプ）
    ↓
英語フレーズを自動抽出・動画をフレーズごとに分割
    ↓
Claude API（日本語訳・解説・4択クイズ・例文を自動生成）
    ↓
Google Spreadsheet に自動登録
    ↓
Masaさんが内容を確認・修正
    ↓
アプリ（Swallow）に反映
```

**10分の撮影 → 20〜30レッスンカード自動生成**

---

## 担当分け

| 担当 | やること |
|---|---|
| **Masaさん** | 動画撮影、生成された解説の最終チェック・修正 |
| **健人さん** | このドキュメントに沿ってシステム構築・運用 |

---

## 必要なもの

### APIキー
| API | 用途 | 取得先 | 料金目安 |
|---|---|---|---|
| OpenAI API | Whisper（音声文字起こし） | https://platform.openai.com/api-keys | 10分動画で約$0.06（6円） |
| Anthropic API | Claude（解説生成） | https://console.anthropic.com/ | 1フレーズ約$0.003（0.4円） |

**月100フレーズ量産しても月220円程度。**

### ツール（ローカルPC）
| ツール | 用途 | インストール |
|---|---|---|
| Python 3.10+ | スクリプト実行 | https://www.python.org/ |
| ffmpeg | 動画分割・MP4変換 | `brew install ffmpeg`（Mac） |
| pip パッケージ | API連携 | 下記参照 |

### pip パッケージ
```bash
pip install openai anthropic google-api-python-client google-auth-oauthlib
```

---

## システム構成

```
swallow/
├── pipeline/                    ← 新規作成（コンテンツ生成システム）
│   ├── process_video.py         ← メインスクリプト（これ1本で全部やる）
│   ├── config.py                ← APIキー・設定
│   ├── requirements.txt         ← pip パッケージ一覧
│   ├── input/                   ← 撮影した動画を入れるフォルダ
│   │   └── (masa_recording.MOV)
│   ├── output/                  ← 分割された動画・JSONが出力される
│   │   ├── clips/               ← フレーズごとの動画クリップ（MP4）
│   │   ├── phrases.json         ← 生成されたフレーズデータ
│   │   └── review.csv           ← Masaさん確認用CSV
│   └── prompts/                 ← Claude APIに送るプロンプト
│       └── generate_lesson.txt
├── index.html                   ← アプリ本体（最終的にここにデータを反映）
└── ...
```

---

## 実装手順

### Step 1: プロジェクトセットアップ

```bash
cd 教材/swallow
mkdir -p pipeline/input pipeline/output/clips pipeline/prompts
```

#### `pipeline/requirements.txt`
```
openai>=1.0.0
anthropic>=0.18.0
google-api-python-client>=2.0.0
google-auth-oauthlib>=1.0.0
```

#### `pipeline/config.py`
```python
import os

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-ここにキーを入れる")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "sk-ant-ここにキーを入れる")

# Google Spreadsheet の設定（Step 5 で設定）
SPREADSHEET_ID = "ここにスプレッドシートIDを入れる"
SHEET_NAME = "フレーズ一覧"

# 動画分割の設定
CLIP_PADDING_SEC = 0.3       # フレーズ前後に余白を付ける秒数
MIN_PHRASE_LENGTH = 3        # 最低3単語以上のフレーズだけ採用
OUTPUT_FORMAT = "mp4"        # 出力フォーマット（MOV → MP4 に変換）
```

---

### Step 2: Whisper API で文字起こし + タイムスタンプ取得

#### 処理内容
- 動画ファイル（MOV）を Whisper API に送信
- 英語フレーズごとにタイムスタンプ付きで返ってくる
- 日本語（「えーっと」「次は」等）は自動的に除外

#### コード: `pipeline/process_video.py`（Part 1: 文字起こし）

```python
import json
import subprocess
import os
from openai import OpenAI
from config import OPENAI_API_KEY, MIN_PHRASE_LENGTH

client = OpenAI(api_key=OPENAI_API_KEY)


def extract_audio(video_path: str, audio_path: str):
    """動画から音声を抽出（Whisper API用）"""
    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-vn",                    # 映像なし
        "-acodec", "pcm_s16le",   # WAV形式
        "-ar", "16000",           # 16kHz（Whisper推奨）
        "-ac", "1",               # モノラル
        "-y",                     # 上書き
        audio_path
    ], check=True, capture_output=True)
    print(f"音声抽出完了: {audio_path}")


def transcribe(audio_path: str) -> list[dict]:
    """Whisper API で文字起こし（タイムスタンプ付き）"""
    with open(audio_path, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="en",              # 英語として認識
            response_format="verbose_json",
            timestamp_granularities=["segment"]
        )

    # 英語フレーズだけフィルタリング
    phrases = []
    for segment in response.segments:
        text = segment.text.strip()

        # 短すぎるもの、日本語が混ざっているものを除外
        if len(text.split()) < MIN_PHRASE_LENGTH:
            continue
        if any('\u3040' <= c <= '\u9fff' for c in text):
            continue  # 日本語が含まれていたらスキップ

        phrases.append({
            "text": text,
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
        })

    print(f"抽出されたフレーズ数: {len(phrases)}")
    return phrases
```

#### Whisper API の戻り値イメージ
```json
[
    {"text": "What do you wanna do?", "start": 0.5, "end": 2.8},
    {"text": "I'm gonna grab a coffee.", "start": 8.2, "end": 10.5},
    {"text": "Can I get a large latte?", "start": 22.1, "end": 24.3}
]
```

**ポイント:**
- `language="en"` を指定することで、日本語の「えーっと」「次は」等を無視してくれる
- 間が10秒あろうが30秒あろうが、英語が話されている区間だけ正確に拾う
- 言い直しも別セグメントとして返ってくるので、後で不要なものを除外可能

---

### Step 3: ffmpeg でフレーズごとに動画を分割

#### コード: `pipeline/process_video.py`（Part 2: 動画分割）

```python
from config import CLIP_PADDING_SEC, OUTPUT_FORMAT


def split_video(video_path: str, phrases: list[dict], output_dir: str):
    """タイムスタンプに基づいて動画をフレーズごとに分割"""
    os.makedirs(output_dir, exist_ok=True)

    for i, phrase in enumerate(phrases):
        # フレーズ前後に余白を追加（自然な切り出し）
        start = max(0, phrase["start"] - CLIP_PADDING_SEC)
        end = phrase["end"] + CLIP_PADDING_SEC
        duration = end - start

        output_file = os.path.join(output_dir, f"clip_{i:03d}.{OUTPUT_FORMAT}")

        subprocess.run([
            "ffmpeg",
            "-i", video_path,
            "-ss", str(start),          # 開始位置
            "-t", str(duration),        # 長さ
            "-c:v", "libx264",          # H.264エンコード（MP4用・軽量化）
            "-crf", "23",               # 品質（18=高品質, 28=低品質）
            "-preset", "fast",
            "-c:a", "aac",              # 音声コーデック
            "-b:a", "128k",
            "-movflags", "+faststart",  # Web再生向け最適化
            "-y",
            output_file
        ], check=True, capture_output=True)

        phrase["video_file"] = f"clip_{i:03d}.{OUTPUT_FORMAT}"
        print(f"  [{i+1}/{len(phrases)}] {phrase['text'][:40]}... → {output_file}")

    print(f"\n動画分割完了: {len(phrases)}本のクリップ")
    return phrases
```

**ポイント:**
- MOV → MP4（H.264）に変換するので、ファイルサイズが**1/5〜1/10**に
- `CLIP_PADDING_SEC` で前後に0.3秒の余白をつけて自然なカットに
- `-movflags +faststart` でWeb/アプリでの再生開始を高速化

---

### Step 4: Claude API で解説・クイズ・例文を自動生成

#### プロンプト: `pipeline/prompts/generate_lesson.txt`

```
あなたは英語教育の専門家です。以下の英語フレーズについて、日本人の英語学習者向けにレッスンカードのデータを生成してください。

## 入力フレーズ
{phrase}

## 出力形式（JSONで返してください）
{
  "en": "英語フレーズ（重要な表現を<span class=\"hl\">タグ</span>で囲む）",
  "enPlain": "英語フレーズ（HTMLタグなし）",
  "ja": "自然な日本語訳",
  "category": "カテゴリ（日常会話 / 旅行 / ビジネス / レストラン / 空港 / ショッピング / 自己紹介 / 感情表現 のいずれか）",
  "choices": ["正解の日本語訳", "紛らわしい誤訳1", "紛らわしい誤訳2", "紛らわしい誤訳3"],
  "correctIndex": 0,
  "explain": "<p>このフレーズの文法・ニュアンス・使われる場面の解説をHTML形式で。<b>重要な単語</b>はboldに。口語表現がある場合はその説明も。2〜3段落。</p>",
  "examples": [
    {"en": "例文1の英語", "ja": "例文1の日本語訳"},
    {"en": "例文2の英語", "ja": "例文2の日本語訳"},
    {"en": "例文3の英語", "ja": "例文3の日本語訳"}
  ]
}

## ルール
- choicesの正解は必ずindex 0に入れること（システム側でシャッフルする）
- 誤訳は「ありそうで間違い」なものにする（全く違う訳ではなく、微妙にニュアンスが違うもの）
- 解説は中学〜高校レベルの学習者がわかる言葉で書く
- 例文は日常で実際に使えるものを選ぶ
- カテゴリはフレーズの内容から最も適切なものを選ぶ
- JSONのみ返すこと（説明文は不要）
```

#### コード: `pipeline/process_video.py`（Part 3: 解説生成）

```python
import anthropic
from config import ANTHROPIC_API_KEY

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def load_prompt_template() -> str:
    """プロンプトテンプレートを読み込む"""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "generate_lesson.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def generate_lesson_data(phrases: list[dict]) -> list[dict]:
    """Claude API でフレーズごとに解説・クイズ・例文を生成"""
    template = load_prompt_template()
    results = []

    for i, phrase in enumerate(phrases):
        prompt = template.replace("{phrase}", phrase["text"])

        response = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        # JSONをパース
        raw = response.content[0].text.strip()
        # ```json ... ``` で囲まれている場合に対応
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]

        try:
            lesson = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  [WARN] JSON解析失敗: {phrase['text'][:40]}... → スキップ")
            continue

        # 動画ファイル名と先生情報を追加
        lesson["video"] = phrase.get("video_file", "")
        lesson["start"] = phrase["start"]
        lesson["end"] = phrase["end"]
        lesson["original_text"] = phrase["text"]

        results.append(lesson)
        print(f"  [{i+1}/{len(phrases)}] {phrase['text'][:40]}... → 解説生成OK")

    print(f"\n解説生成完了: {len(results)}フレーズ")
    return results
```

---

### Step 5: Google Spreadsheet に自動登録

#### 事前準備
1. Google Cloud Console でプロジェクト作成
2. Google Sheets API を有効化
3. サービスアカウント作成 → JSONキーをダウンロード
4. スプレッドシートを作成し、サービスアカウントのメールアドレスに編集権限を付与

#### スプレッドシートの列構成
| A | B | C | D | E | F | G | H | I | J | K |
|---|---|---|---|---|---|---|---|---|---|---|
| ステータス | 先生ID | 英語 | 日本語訳 | カテゴリ | 選択肢1(正解) | 選択肢2 | 選択肢3 | 選択肢4 | 解説 | 動画ファイル |

- **ステータス列**: 「未確認」「確認済み」「修正済み」でMasaさんが管理
- Masaさんは**このスプレッドシートだけ見ればOK**

#### コード: `pipeline/process_video.py`（Part 4: スプレッドシート連携）

```python
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import SPREADSHEET_ID, SHEET_NAME


def upload_to_spreadsheet(lessons: list[dict], teacher_id: str):
    """生成されたレッスンデータをスプレッドシートに追加"""
    creds = Credentials.from_service_account_file(
        os.path.join(os.path.dirname(__file__), "credentials.json"),
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = build("sheets", "v4", credentials=creds)

    rows = []
    for lesson in lessons:
        choices = lesson.get("choices", ["", "", "", ""])
        rows.append([
            "未確認",                    # ステータス
            teacher_id,                  # 先生ID
            lesson.get("enPlain", ""),    # 英語
            lesson.get("ja", ""),         # 日本語訳
            lesson.get("category", ""),   # カテゴリ
            choices[0] if len(choices) > 0 else "",  # 選択肢1（正解）
            choices[1] if len(choices) > 1 else "",  # 選択肢2
            choices[2] if len(choices) > 2 else "",  # 選択肢3
            choices[3] if len(choices) > 3 else "",  # 選択肢4
            lesson.get("explain", ""),    # 解説
            lesson.get("video", ""),      # 動画ファイル
        ])

    body = {"values": rows}
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:K",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()

    print(f"スプレッドシートに {len(rows)} 行追加しました")
```

---

### Step 6: メインスクリプト（全部つなげる）

#### コード: `pipeline/process_video.py`（Part 5: main）

```python
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(description="Swallow コンテンツ自動生成")
    parser.add_argument("video", help="入力動画ファイルのパス")
    parser.add_argument("--teacher", default="masa", help="先生ID（masa / miki / masaki）")
    parser.add_argument("--no-upload", action="store_true", help="スプレッドシートにアップロードしない")
    args = parser.parse_args()

    video_path = args.video
    teacher_id = args.teacher
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    output_dir = os.path.join("output", "clips", base_name)
    audio_path = os.path.join("output", f"{base_name}_audio.wav")

    print("=" * 60)
    print(f"Swallow コンテンツ自動生成")
    print(f"入力: {video_path}")
    print(f"先生: {teacher_id}")
    print("=" * 60)

    # Step 1: 音声抽出
    print("\n[1/4] 音声抽出中...")
    extract_audio(video_path, audio_path)

    # Step 2: Whisper で文字起こし
    print("\n[2/4] 文字起こし中（Whisper API）...")
    phrases = transcribe(audio_path)

    if not phrases:
        print("英語フレーズが検出されませんでした。動画を確認してください。")
        sys.exit(1)

    # Step 3: 動画分割
    print("\n[3/4] 動画分割中（ffmpeg）...")
    phrases = split_video(video_path, phrases, output_dir)

    # Step 4: Claude で解説生成
    print("\n[4/4] 解説生成中（Claude API）...")
    lessons = generate_lesson_data(phrases)

    # 結果をJSON保存
    json_path = os.path.join("output", f"{base_name}_lessons.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(lessons, f, ensure_ascii=False, indent=2)
    print(f"\nJSON保存: {json_path}")

    # 確認用CSV出力（Masaさんが目視チェックしやすいように）
    csv_path = os.path.join("output", f"{base_name}_review.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("英語,日本語訳,カテゴリ,解説(冒頭50字),動画ファイル\n")
        for l in lessons:
            explain_short = l.get("explain", "")[:50].replace("\n", " ")
            f.write(f'"{l.get("enPlain","")}","{l.get("ja","")}","{l.get("category","")}","{explain_short}","{l.get("video","")}"\n')
    print(f"確認用CSV: {csv_path}")

    # スプレッドシートにアップロード
    if not args.no_upload:
        print("\nスプレッドシートにアップロード中...")
        upload_to_spreadsheet(lessons, teacher_id)

    print("\n" + "=" * 60)
    print(f"完了！ {len(lessons)} フレーズのレッスンカードが生成されました")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

---

## 使い方

### 基本コマンド（これだけ覚えればOK）

```bash
cd 教材/swallow/pipeline

# まさ先生の動画を処理
python process_video.py input/masa_recording.MOV --teacher masa

# みき先生の動画を処理
python process_video.py input/miki_recording.MOV --teacher miki

# スプレッドシートに上げずにローカルだけで確認
python process_video.py input/test.MOV --teacher masa --no-upload
```

### 実行結果イメージ

```
============================================================
Swallow コンテンツ自動生成
入力: input/masa_recording.MOV
先生: masa
============================================================

[1/4] 音声抽出中...
音声抽出完了: output/masa_recording_audio.wav

[2/4] 文字起こし中（Whisper API）...
抽出されたフレーズ数: 24

[3/4] 動画分割中（ffmpeg）...
  [1/24] What do you wanna do?... → output/clips/masa_recording/clip_000.mp4
  [2/24] I'm gonna grab a coffee.... → output/clips/masa_recording/clip_001.mp4
  ...

[4/4] 解説生成中（Claude API）...
  [1/24] What do you wanna do?... → 解説生成OK
  [2/24] I'm gonna grab a coffee.... → 解説生成OK
  ...

JSON保存: output/masa_recording_lessons.json
確認用CSV: output/masa_recording_review.csv
スプレッドシートに 24 行追加しました

============================================================
完了！ 24 フレーズのレッスンカードが生成されました
============================================================
```

---

## Masaさんの作業フロー

### 撮影時
1. スマホを縦向きで固定
2. フレーズを1つ言う → 少し間を空ける → 次のフレーズ
3. **言い直しOK、日本語が混ざってもOK、間が長くてもOK**
4. 10分くらい撮影したら終了
5. 動画ファイルを `pipeline/input/` に入れる（AirDrop等で）

### 確認時
1. スプレッドシートを開く
2. 「未確認」のフレーズを上から見る
3. 日本語訳・解説がおかしければ修正
4. OKなら「確認済み」に変更
5. **以上。**

### 撮影のコツ
- **1回の撮影で20〜30フレーズ**が目安（10分程度）
- 背景はシンプルに（毎回同じ場所でOK）
- カメラ目線で話す（アプリ上で先生が話しかけてくる感覚になる）
- フレーズの間は**2秒以上**空ければ十分（Whisperが区切りを判定する）

---

## 次のステップ（Phase 2 以降）

### Phase 2: スプレッドシート → アプリ自動反映
- GASでスプレッドシートのデータをJSON APIとして公開
- Swallowアプリが起動時にAPIからフレーズデータを取得
- index.htmlのハードコードを廃止

### Phase 3: 動画のクラウドホスティング
- 分割されたMP4をCloudflare R2 or Vercel Blobにアップロード
- アプリは動画URLを参照（アプリ本体に動画を含めない）
- これでApp Storeの200MB制限を回避

### Phase 4: 管理画面
- Webベースの管理画面でフレーズの追加・編集・並べ替え
- プレビュー機能（アプリでどう見えるか確認）
- 公開/非公開の切り替え

---

## コスト見積もり

### API料金（月100フレーズ量産の場合）
| API | 月額 |
|---|---|
| Whisper API | 約$0.20（30円） |
| Claude API（Sonnet） | 約$0.30（45円） |
| **合計** | **約$0.50（75円/月）** |

### その他
| 項目 | 料金 |
|---|---|
| Vercel（ホスティング） | 無料枠内 |
| Google Spreadsheet | 無料 |
| Cloudflare R2（Phase 3以降） | 無料枠 10GB/月 |

---

## トラブルシューティング

### 「フレーズが検出されませんでした」
- 動画に英語の音声が入っているか確認
- 音声が小さすぎないか確認（スマホのマイクに近づいて話す）
- `language="en"` が原因で日本語のみの区間が除外されている（正常動作）

### 「JSON解析失敗」が出る
- Claude APIの応答がJSON以外を含んでいる場合に発生
- `prompts/generate_lesson.txt` の最後に「JSONのみ返すこと」を強調
- 失敗したフレーズは手動でスプレッドシートに追加

### 動画クリップの前後が切れている
- `config.py` の `CLIP_PADDING_SEC` を 0.3 → 0.5 に増やす

### ffmpegエラー
- `brew install ffmpeg` でインストール済みか確認
- `ffmpeg -version` で動作確認
