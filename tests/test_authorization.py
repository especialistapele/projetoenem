import unittest
from unittest.mock import patch

from fastapi import HTTPException

import app.api.learning as learning
import app.api.scoring as scoring
import app.supabase_auth as supabase_auth


class AuthorizationTests(unittest.TestCase):
    def test_teacher_role_from_user_metadata_is_not_trusted(self):
        with patch.object(learning, "get_current_supabase_user", return_value={
            "id": "student-1",
            "user_metadata": {"role": "teacher"},
            "app_metadata": {},
        }):
            with self.assertRaises(HTTPException) as error:
                learning.require_teacher("Bearer test-token")
        self.assertEqual(error.exception.status_code, 403)

    def test_teacher_role_from_app_metadata_is_accepted(self):
        with patch.object(learning, "get_current_supabase_user", return_value={
            "id": "teacher-1",
            "user_metadata": {},
            "app_metadata": {"role": "teacher"},
        }):
            user = learning.require_teacher("Bearer test-token")
        self.assertEqual(user["id"], "teacher-1")

    def test_admin_role_from_user_metadata_is_not_trusted(self):
        with patch.object(supabase_auth, "get_current_supabase_user", return_value={
            "id": "student-1",
            "user_metadata": {"role": "admin"},
            "app_metadata": {},
        }):
            with self.assertRaises(HTTPException) as error:
                supabase_auth.require_admin("Bearer test-token")
        self.assertEqual(error.exception.status_code, 403)

    def test_prediction_generation_route_requires_admin(self):
        route = next(route for route in scoring.router.routes if getattr(route, "path", None) == "/scoring/predict")
        dependency_callables = {dependency.call for dependency in route.dependant.dependencies}
        self.assertIn(supabase_auth.require_admin, dependency_callables)


if __name__ == "__main__":
    unittest.main()
