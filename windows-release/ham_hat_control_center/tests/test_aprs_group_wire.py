import unittest

from app.aprs_modem import (
    APRS_MESSAGE_TEXT_MAX,
    build_group_wire_text,
    build_intro_wire_text,
    build_aprs_message_payload,
    parse_aprs_message_info,
    parse_intro_wire_text,
    parse_group_wire_text,
    split_aprs_text_chunks,
)


class AprsGroupWireTests(unittest.TestCase):
    def test_group_wire_round_trip(self) -> None:
        wire = build_group_wire_text("ops_team", "hello world")
        parsed = parse_group_wire_text(wire)
        self.assertIsNotNone(parsed)
        group, body, part, total = parsed
        self.assertEqual(group, "OPS_TEAM")
        self.assertEqual(body, "hello world")
        self.assertIsNone(part)
        self.assertIsNone(total)

    def test_group_wire_round_trip_chunked(self) -> None:
        wire = build_group_wire_text("SQUAD1", "chunk body", part=2, total=5)
        parsed = parse_group_wire_text(wire)
        self.assertEqual(parsed, ("SQUAD1", "chunk body", 2, 5))

    def test_split_chunks_respect_limit(self) -> None:
        long_text = " ".join(["packet"] * 40)
        chunks = split_aprs_text_chunks(long_text, APRS_MESSAGE_TEXT_MAX)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= APRS_MESSAGE_TEXT_MAX for c in chunks))
        self.assertEqual(" ".join(chunks).replace("  ", " ").strip(), long_text)

    def test_group_wire_rejects_bad_group_name(self) -> None:
        with self.assertRaises(ValueError):
            build_group_wire_text("bad group", "hello")

    def test_parse_aprs_message_info_round_trip(self) -> None:
        payload = build_aprs_message_payload("VA7AYG-01", "hello test", "12345")
        parsed = parse_aprs_message_info(payload)
        self.assertEqual(parsed, ("VA7AYG-01", "hello test", "12345"))

    def test_intro_wire_round_trip(self) -> None:
        wire = build_intro_wire_text("VA7AYG-00", 49.2827, -123.1207, "online")
        parsed = parse_intro_wire_text(wire)
        self.assertIsNotNone(parsed)
        call, lat, lon, note = parsed
        self.assertEqual(call, "VA7AYG-00")
        self.assertAlmostEqual(lat, 49.2827, places=4)
        self.assertAlmostEqual(lon, -123.1207, places=4)
        self.assertEqual(note, "online")


if __name__ == "__main__":
    unittest.main()
