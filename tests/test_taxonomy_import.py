import unittest

from scripts.import_taxonomy import AREA_HEADERS, parse_matrix_text


def synthetic_matrix():
    lines = []
    competency_counts = {"LC": 9, "CH": 6, "CN": 8, "MT": 7}
    for code, area_name in AREA_HEADERS:
        lines.append(area_name)
        count = competency_counts[code]
        for competency_index in range(count):
            competency_number = competency_index + 1
            lines.append(f"Competência de área {competency_number} - Competência {code} {competency_number}.")
            first_skill = competency_index * 30 // count + 1
            last_skill = (competency_index + 1) * 30 // count
            for skill_number in range(first_skill, last_skill + 1):
                lines.append(f"H{skill_number} - Descrição oficial de teste da habilidade {skill_number} na área {code}.")
    return "\n".join(lines)


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
        text = synthetic_matrix().replace("H30 - Descrição oficial de teste da habilidade 30 na área MT.", "")
        with self.assertRaisesRegex(ValueError, "Matriz extraída incompleta"):
            parse_matrix_text(text)


if __name__ == "__main__":
    unittest.main()
