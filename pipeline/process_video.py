import json
import subprocess
import os
import sys
import argparse

from openai import OpenAI
import anthropic
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from config import (
    OPENAI_API_KEY, ANTHROPIC_API_KEY,
    CLIP_PADDING_SEC, MIN_PHRASE_LENGTH, OUTPUT_FORMAT,
    SPREADSHEET_ID, SHEET_NAME,
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME, R2_PUBLIC_URL,
)

openai_client = OpenAI(api_key=OPENAI_API_KEY)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ============================================================
# Step 1: 音声抽出
# ============================================================

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


# ============================================================
# Step 2: Whisper API で文字起こし
# ============================================================

def transcribe(audio_path: str) -> list[dict]:
    """Whisper API で文字起こし（タイムスタンプ付き）"""
    with open(audio_path, "rb") as f:
        response = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language="en",
            response_format="verbose_json",
            timestamp_granularities=["segment"]
        )

    phrases = []
    for segment in response.segments:
        text = segment.text.strip()

        # 短すぎるもの、日本語が混ざっているものを除外
        if len(text.split()) < MIN_PHRASE_LENGTH:
            continue
        if any('\u3040' <= c <= '\u9fff' for c in text):
            continue

        phrases.append({
            "text": text,
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
        })

    print(f"抽出されたフレーズ数: {len(phrases)}")
    return phrases


# ============================================================
# Step 3: 動画分割
# ============================================================

def split_video(video_path: str, phrases: list[dict], output_dir: str):
    """タイムスタンプに基づいて動画をフレーズごとに分割"""
    os.makedirs(output_dir, exist_ok=True)

    for i, phrase in enumerate(phrases):
        start = max(0, phrase["start"] - CLIP_PADDING_SEC)
        end = phrase["end"] + CLIP_PADDING_SEC
        duration = end - start

        output_file = os.path.join(output_dir, f"clip_{i:03d}.{OUTPUT_FORMAT}")

        subprocess.run([
            "ffmpeg",
            "-i", video_path,
            "-ss", str(start),
            "-t", str(duration),
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-y",
            output_file
        ], check=True, capture_output=True)

        phrase["video_file"] = f"clip_{i:03d}.{OUTPUT_FORMAT}"
        print(f"  [{i+1}/{len(phrases)}] {phrase['text'][:40]}... → {output_file}")

    print(f"\n動画分割完了: {len(phrases)}本のクリップ")
    return phrases


# ============================================================
# Step 4: Claude API で解説生成
# ============================================================

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

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]

        try:
            lesson = json.loads(raw)
        except json.JSONDecodeError:
            print(f"  [WARN] JSON解析失敗: {phrase['text'][:40]}... → スキップ")
            continue

        lesson["video"] = phrase.get("video_file", "")
        lesson["start"] = phrase["start"]
        lesson["end"] = phrase["end"]
        lesson["original_text"] = phrase["text"]

        results.append(lesson)
        print(f"  [{i+1}/{len(phrases)}] {phrase['text'][:40]}... → 解説生成OK")

    print(f"\n解説生成完了: {len(results)}フレーズ")
    return results


# ============================================================
# Step 5: Google Spreadsheet にアップロード
# ============================================================

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
            "未確認",
            teacher_id,
            lesson.get("enPlain", ""),
            lesson.get("ja", ""),
            lesson.get("category", ""),
            choices[0] if len(choices) > 0 else "",
            choices[1] if len(choices) > 1 else "",
            choices[2] if len(choices) > 2 else "",
            choices[3] if len(choices) > 3 else "",
            lesson.get("explain", ""),
            lesson.get("video", ""),
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


# ============================================================
# Step 6: Cloudflare R2 にアップロード
# ============================================================

def upload_to_r2(clips_dir: str, lessons: list[dict]):
    """動画クリップをCloudflare R2にアップロードし、URLを更新"""
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )

    for i, lesson in enumerate(lessons):
        video_file = lesson.get("video", "")
        if not video_file:
            continue

        local_path = os.path.join(clips_dir, video_file)
        if not os.path.exists(local_path):
            print(f"  [SKIP] {video_file} が見つかりません")
            continue

        r2_key = f"clips/{video_file}"
        s3.upload_file(
            local_path, R2_BUCKET_NAME, r2_key,
            ExtraArgs={"ContentType": "video/mp4"},
        )

        if R2_PUBLIC_URL:
            lesson["video_url"] = f"{R2_PUBLIC_URL}/{r2_key}"

        print(f"  [{i+1}/{len(lessons)}] {video_file} → R2 アップロード完了")

    print(f"\nR2アップロード完了: {len(lessons)}本")


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Swallow コンテンツ自動生成")
    parser.add_argument("video", help="入力動画ファイルのパス")
    parser.add_argument("--teacher", default="masa", help="先生ID（masa / miki / masaki）")
    parser.add_argument("--no-upload", action="store_true", help="スプレッドシートにアップロードしない")
    parser.add_argument("--r2", action="store_true", help="Cloudflare R2に動画をアップロード")
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

    # 確認用CSV出力
    csv_path = os.path.join("output", f"{base_name}_review.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("英語,日本語訳,カテゴリ,解説(冒頭50字),動画ファイル\n")
        for lesson in lessons:
            explain_short = lesson.get("explain", "")[:50].replace("\n", " ")
            f.write(f'"{lesson.get("enPlain","")}","{lesson.get("ja","")}","{lesson.get("category","")}","{explain_short}","{lesson.get("video","")}"\n')
    print(f"確認用CSV: {csv_path}")

    # R2にアップロード
    if args.r2:
        print("\nCloudflare R2にアップロード中...")
        upload_to_r2(output_dir, lessons)
        # R2 URL付きのJSONを再保存
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(lessons, f, ensure_ascii=False, indent=2)

    # スプレッドシートにアップロード
    if not args.no_upload:
        print("\nスプレッドシートにアップロード中...")
        upload_to_spreadsheet(lessons, teacher_id)

    print("\n" + "=" * 60)
    print(f"完了！ {len(lessons)} フレーズのレッスンカードが生成されました")
    print("=" * 60)


if __name__ == "__main__":
    main()
