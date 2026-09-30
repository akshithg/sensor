from __future__ import annotations

import unittest

from sensor_lite import AnalysisError, analyze_source, build_change_graph, mine_patterns
from sensor_lite.analyzer import score_against_patterns

PROTOTYPES = """extern int open(const char *, int);
extern int read(int, char *, int);
extern int close(int);
"""
SAFE = (
    PROTOTYPES
    + """
int load(const char *path, char *buffer) {
    int fd = open(path, 0);
    if (fd < 0) return -1;
    int size = read(fd, buffer, 16);
    close(fd);
    return size;
}
"""
)
LEAK = (
    PROTOTYPES
    + """
int load(const char *path, char *buffer) {
    int fd = open(path, 0);
    if (fd < 0) return -1;
    return read(fd, buffer, 16);
}
"""
)


class AnalyzerTests(unittest.TestCase):
    def test_extracts_action_guard_and_data_nodes(self) -> None:
        analysis = analyze_source(SAFE)
        kinds = {node["kind"] for node in analysis["graph"]["nodes"]}

        self.assertEqual(analysis["calls"], ["open", "read", "close"])
        self.assertEqual(kinds, {"action", "guard", "data"})
        self.assertTrue(any(edge["kind"] == "data" for edge in analysis["graph"]["edges"]))

    def test_flags_missing_cleanup_pattern(self) -> None:
        trusted = analyze_source(SAFE)
        candidate = analyze_source(LEAK)
        patterns = mine_patterns([trusted])

        score = score_against_patterns(candidate, patterns)

        self.assertGreaterEqual(score["risk"], 70)
        self.assertTrue(any(item["expected"] == "open -> close" for item in score["findings"]))

    def test_change_graph_marks_restored_close_as_added(self) -> None:
        change = build_change_graph(analyze_source(LEAK), analyze_source(SAFE))

        close_nodes = [node for node in change["nodes"] if node["label"] == "close"]
        self.assertEqual(close_nodes[0]["status"], "added")
        self.assertEqual(change["summary"]["added"], 2)  # close action and size result

    def test_flags_missing_fix_derived_guard(self) -> None:
        guard_pattern = {
            "kind": "required-guard",
            "label": "validate count before shift",
            "contains": ["count", "SHIFT"],
            "support": 1.0,
            "detail": "The shift needs a range guard.",
        }
        unsafe = analyze_source(
            "#define SHIFT 2\n"
            "int touch(int);\n"
            "int scale(int count) { if (count < 0) return 0; return touch(count << SHIFT); }"
        )

        score = score_against_patterns(unsafe, [guard_pattern])

        self.assertEqual(score["risk"], 82)
        self.assertEqual(score["findings"][0]["title"], "Unchecked shift may overflow")

    def test_rejects_invalid_source(self) -> None:
        with self.assertRaisesRegex(AnalysisError, "clang could not parse"):
            analyze_source("int broken( {")


if __name__ == "__main__":
    unittest.main()
