import unittest

from scripts.import_taxonomy import AREA_HEADERS, parse_matrix_text


def synthetic_matrix():
    lines = []
    competency_counts = {"LC": 9, "CH": 6, "CN": 8, "MT": 7}
    for code, area_name in AREA_HEADERS:
        lines.append(area_name)
        skill_number = 1
        for competency_number in range(1, competency_counts[code] + 1):
            lines.append(f"Competência de área {competency_number} - Competência {code} {competency_number}.")
            skill_count = 4 if skill_number <= 28 else 2
            for _ in range(skill_count):
                if skill_number > 30:
                    break
                lines.append(f"H{skill_number} - Descrição oficial de teste da habilidade {skill_number} na área {code}.")
                skill_number += 1
        assert skill_number == 31, (code, skill_number)
    return "\\n".join(lines)


class TaxonomyParserTests(unittest.TestCase):
    def test_parses_four_areas_and_all_official_code_ranges(self):
        parsed = parse_matrix_text(synthetic_matrix())
        self.assertTrue(parsed["diagnostics"]["valid"])
        self.assertEqual(parsed["diagnostics"]["competencies"], 30)
        self.assertEqual(parsed["diagnostics"]["skills"], 120)
        for area in parsed["areas"]:
            codes = {skill["code"] for competency in area["competencies"] for skill in competency["skills"]}
            self.assertEqual(codes, {f"H{i}" for i in range(1, 31)})

    def test_rejects_matrix_with_missing_area_or_skill(self):
        text = synthetic_matrix().replace("H30 - Descrição oficial de teste da habilidade 30 na área MT.\\n", "")
        with self.assertRaisesRegex(ValueError, "Matriz extraída incompleta"):
            parse_matrix_text(text)


if __name__ == "__main__":
    unittest.main()
