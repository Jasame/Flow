"""隐式标识 in synthesized audio (aigc_label, 2026-11-25): an ID3 TXXX "AIGC" frame with {"Label":"1","ContentProducer",
"ProduceID"}, added to the tag CosyVoice's MP3s already have (LAME's, ID3v2.3) or in a new v2.4 tag; the audio bytes
are never touched; a file is labelled once; a tag it cannot safely extend is left alone."""
import struct, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aigc_label as al  # noqa: E402

AUDIO = b'\xff\xfb\x90\x64' + bytes(range(256)) * 4  # MPEG frames stand-in


def v23(*frames):
    body = b''.join(fid + struct.pack('>I', len(d)) + b'\x00\x00' + d for fid, d in frames)
    return b'ID3\x03\x00\x00' + al._syncsafe(len(body)) + body


LAME = v23((b'TSSE', b'\x00LAME 64bits version 3.100'), (b'COMM', b'\x00eng\x00LAME3.100'))


class AigcLabelTests(unittest.TestCase):
    def test_a_cosyvoice_style_file_gets_the_frame_in_its_own_tag(self):
        x = al.mp3(LAME + AUDIO, 'flow-tts-abc')
        self.assertEqual(al.read(x), {'Label': '1', 'ContentProducer': 'FlowLang', 'ProduceID': 'flow-tts-abc'})
        self.assertEqual(x[3], 3)  # still one ID3v2.3 tag, not a second tag in front
        self.assertEqual(x.count(b'ID3'), 1)
        end = 10 + al._unsync(x[6:10])
        self.assertEqual(x[end:], AUDIO)  # the audio is byte for byte the same
        self.assertIn(b'LAME 64bits', x[:end])  # LAME's frames kept

    def test_a_file_without_a_tag_gets_a_new_v24_tag(self):
        x = al.mp3(AUDIO, 'flow-tts-def')
        self.assertEqual(x[:5], b'ID3\x04\x00')
        self.assertEqual(al.read(x)['ProduceID'], 'flow-tts-def')
        self.assertEqual(x[10 + al._unsync(x[6:10]):], AUDIO)

    def test_labelled_once(self):
        x = al.mp3(LAME + AUDIO, 'one')
        self.assertEqual(al.mp3(x, 'two'), x)
        self.assertTrue(al.has_label(x))
        self.assertFalse(al.has_label(LAME + AUDIO))

    def test_values_are_visible_ascii_only(self):
        with self.assertRaises(ValueError):
            al.value('id', provider='语流 Flow')
        self.assertEqual(al.value('x-1'), b'{"Label":"1","ContentProducer":"FlowLang","ProduceID":"x-1"}')

    def test_a_tag_that_cannot_be_extended_safely_is_left_alone(self):
        unsync = b'ID3\x03\x00\x80' + LAME[6:]
        self.assertEqual(al.mp3(unsync + AUDIO, 'x'), unsync + AUDIO)


if __name__ == '__main__':
    unittest.main()
