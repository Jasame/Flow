"""Small in-memory audio payloads only; no filesystem or remote URL inputs."""
import base64,binascii
MAX_AUDIO_BYTES=1_500_000
MIMES={'audio/webm','audio/ogg','audio/wav','audio/mpeg','audio/mp3','audio/mp4','audio/m4a','audio/flac'}
def validate_audio(audio):
 if not isinstance(audio,dict) or set(audio)!={'mime_type','data'}:raise ValueError('音频参数不正确')
 mime=audio['mime_type'];data=audio['data']
 if mime not in MIMES or not isinstance(data,str) or not 16<=len(data)<=2_000_000:raise ValueError('音频格式不支持或超过 1.5 MB')
 try:raw=base64.b64decode(data,validate=True)
 except (ValueError,binascii.Error):raise ValueError('音频编码不正确')
 if not 12<=len(raw)<=MAX_AUDIO_BYTES:raise ValueError('音频大小不正确')
 valid=(mime=='audio/webm' and raw.startswith(b'\x1aE\xdf\xa3') or mime=='audio/ogg' and raw.startswith(b'OggS') or mime=='audio/wav' and raw[:4]==b'RIFF' and raw[8:12]==b'WAVE' or mime in ('audio/mp4','audio/m4a') and raw[4:8]==b'ftyp' or mime in ('audio/mpeg','audio/mp3') and (raw.startswith(b'ID3') or raw[0]==255 and raw[1]&224==224) or mime=='audio/flac' and raw.startswith(b'fLaC'))
 if not valid:raise ValueError('音频内容与格式不匹配，请重新录制')
 return raw
