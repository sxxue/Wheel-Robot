import unittest
from backend.services.gemini_service import gemini_service

class TestCantoneseReasoning(unittest.TestCase):
    def setUp(self):
        self.som_meta = [
            {"id": 1, "label": "Obstacle (Red Box)"},
            {"id": 2, "label": "Target (Blue Door)"},
            {"id": 3, "label": "Free Corridor"},
            {"id": 4, "label": "Yellow Traffic Cone"},
            {"id": 5, "label": "Charging Station"},
            {"id": 6, "label": "Orange Barrel"},
            {"id": 7, "label": "Lab Tool Bench"}
        ]

    def test_cantonese_commands(self):
        # 1. Door command in Cantonese
        res = gemini_service._mock_reasoning("行去藍色門", 420, self.som_meta)
        self.assertEqual(res["user_intent"], "REACH_TARGET")
        self.assertIn("[2]", res["identified_target"])

        # 2. Charging station in Cantonese ("叉電位")
        res = gemini_service._mock_reasoning("避開個障礙物行去叉電位", 420, self.som_meta)
        self.assertEqual(res["user_intent"], "REACH_TARGET")
        self.assertIn("[5]", res["identified_target"])

        # 3. Traffic cone avoidance in Cantonese ("雪糕筒", "紫色枱")
        res = gemini_service._mock_reasoning("避開黃色雪糕筒去紫色枱", 420, self.som_meta)
        self.assertEqual(res["user_intent"], "REACH_TARGET")
        self.assertIn("[7]", res["identified_target"])

        # 4. Loop around obstacle in Cantonese ("兜個圈")
        res = gemini_service._mock_reasoning("兜個圈去藍色門", 420, self.som_meta)
        self.assertEqual(res["user_intent"], "COMPOUND_CIRCUIT_AND_TARGET")
        self.assertEqual(len(res["commands"]), 9)

        # 5. Directional turns
        res = gemini_service._mock_reasoning("轉左", 420, self.som_meta)
        self.assertEqual(res["user_intent"], "DIRECTIONAL_MOTION")
        self.assertEqual(res["commands"][0]["action"], "TURN_LEFT")

        res = gemini_service._mock_reasoning("轉右", 420, self.som_meta)
        self.assertEqual(res["user_intent"], "DIRECTIONAL_MOTION")
        self.assertEqual(res["commands"][0]["action"], "TURN_RIGHT")

        res = gemini_service._mock_reasoning("停低", 420, self.som_meta)
        self.assertEqual(res["user_intent"], "DIRECTIONAL_MOTION")
        self.assertEqual(res["commands"][0]["action"], "STOP")

        res = gemini_service._mock_reasoning("退後", 420, self.som_meta)
        self.assertEqual(res["user_intent"], "DIRECTIONAL_MOTION")
        self.assertEqual(res["commands"][0]["action"], "BACKWARD")

if __name__ == "__main__":
    unittest.main()
