"""Server-only ElevenLabs batch transcription; audio is never persisted."""

from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ValidationError

from .config import setting

router = APIRouter()
MAX_AUDIO_BYTES = 10 * 1024 * 1024
ALLOWED_AUDIO = {"audio/webm": "webm", "audio/mp4": "m4a", "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/ogg": "ogg"}


def api_key() -> str:
    key = setting("ELEVENLABS_API_KEY")
    if key:
        return key
    raise HTTPException(503, "Chưa cấu hình ElevenLabs trên máy chủ.")


class ElevenTranscript(BaseModel):
    text: str
    language_code: str | None = None


class Transcript(ElevenTranscript):
    provider: Literal["elevenlabs"] = "elevenlabs"


@router.post("/api/search/transcribe", response_model=Transcript)
async def transcribe(request: Request) -> Transcript:
    if request.headers.get('x-media-consent')!='true':
        raise HTTPException(422,'Cần đồng ý gửi bản ghi tới dịch vụ phiên âm.')
    key = api_key()
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_AUDIO:
        raise HTTPException(415, "Hãy cung cấp âm thanh WebM, MP4, MP3, WAV hoặc OGG.")
    audio = bytearray()
    async for chunk in request.stream():
        audio.extend(chunk)
        if len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Âm thanh vượt quá 10 MB. Hãy ghi âm ngắn hơn.")
    if len(audio) < 100:
        raise HTTPException(422, "Âm thanh trống hoặc quá ngắn. Hãy ghi âm lại.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
            result = await client.post(
                "https://api.elevenlabs.io/v1/speech-to-text",
                headers={"xi-api-key": key},
                data={"model_id": "scribe_v2", "language_code": "vie", "tag_audio_events": "false", "diarize": "false"},
                files={"file": ("search." + ALLOWED_AUDIO[content_type], bytes(audio), content_type)},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "ElevenLabs phản hồi quá lâu. Hãy thử lại.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(503, "Không kết nối được ElevenLabs. Kiểm tra Internet rồi thử lại.") from exc
    if result.status_code in {401, 403}:
        raise HTTPException(502, "ElevenLabs từ chối xác thực. Kiểm tra API key và quyền Speech-to-Text trên máy chủ.")
    if result.status_code == 429:
        raise HTTPException(429, "ElevenLabs đang giới hạn yêu cầu hoặc tài khoản đã hết hạn mức. Hãy thử lại sau.")
    if not result.is_success:
        raise HTTPException(502, f"ElevenLabs không xử lý được âm thanh (HTTP {result.status_code}). Hãy thử bản ghi khác.")
    try:
        transcript = ElevenTranscript.model_validate_json(result.content)
    except ValidationError as exc:
        raise HTTPException(502, "ElevenLabs trả về dữ liệu phiên âm không hợp lệ.") from exc
    if not transcript.text.strip():
        raise HTTPException(422, "Không nhận được lời nói trong bản ghi. Hãy nói rõ tên sản phẩm rồi thử lại.")
    return Transcript(text=transcript.text.strip(), language_code=transcript.language_code)


async def synthesize(text: str) -> bytes:
    key = api_key()
    voice = setting("ELEVENLABS_VOICE_ID")
    if not voice:
        raise HTTPException(503, "Chưa chọn giọng ElevenLabs cho Ami trên máy chủ.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
            response = await client.post(
                "https://api.elevenlabs.io/v1/text-to-speech/" + voice,
                headers={"xi-api-key": key},
                params={"output_format": "mp3_44100_128"},
                json={"text": text, "model_id": "eleven_flash_v2_5", "language_code": "vi",
                      "voice_settings": {"similarity_boost": 0.5, "stability": 0.55}},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(504, "ElevenLabs tạo giọng nói quá lâu. Bạn vẫn có thể đọc câu trả lời.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(503, "Không kết nối được ElevenLabs để tạo giọng nói.") from exc
    if response.status_code in {401, 403}:
        raise HTTPException(502, "ElevenLabs từ chối xác thực hoặc quyền tạo giọng nói. Kiểm tra API key phía máy chủ.")
    if response.status_code == 429:
        raise HTTPException(429, "ElevenLabs đang giới hạn yêu cầu hoặc tài khoản hết hạn mức.")
    if not response.is_success:
        raise HTTPException(502, f"ElevenLabs không tạo được giọng nói (HTTP {response.status_code}).")
    if not response.headers.get("content-type", "").startswith("audio/") or not response.content or len(response.content) > 8 * 1024 * 1024:
        raise HTTPException(502, "ElevenLabs trả về âm thanh không hợp lệ.")
    return response.content
