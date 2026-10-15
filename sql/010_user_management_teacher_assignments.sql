CREATE TABLE IF NOT EXISTS public.user_profiles (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  role text NOT NULL DEFAULT 'student' CHECK (role IN ('admin','teacher','student')),
  program_id integer REFERENCES public.programs(id) ON DELETE SET NULL,
  display_name text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.teacher_students (
  teacher_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  student_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  assigned_at timestamptz NOT NULL DEFAULT now(),
  active boolean NOT NULL DEFAULT true,
  PRIMARY KEY (teacher_id, student_id),
  CHECK (teacher_id <> student_id)
);
CREATE INDEX IF NOT EXISTS idx_teacher_students_teacher ON public.teacher_students(teacher_id, active);
CREATE INDEX IF NOT EXISTS idx_teacher_students_student ON public.teacher_students(student_id, active);

CREATE OR REPLACE FUNCTION public.current_app_role()
RETURNS text LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT COALESCE((auth.jwt()->'app_metadata'->>'role'), 'student') $$;
CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT public.current_app_role() = 'admin' $$;
CREATE OR REPLACE FUNCTION public.is_teacher_or_admin()
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT public.current_app_role() IN ('teacher','admin') $$;

ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.teacher_students ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_profiles_self_or_admin ON public.user_profiles;
CREATE POLICY user_profiles_self_or_admin ON public.user_profiles FOR SELECT TO authenticated
USING (user_id = auth.uid() OR public.is_admin());
DROP POLICY IF EXISTS user_profiles_admin_write ON public.user_profiles;
CREATE POLICY user_profiles_admin_write ON public.user_profiles FOR ALL TO authenticated
USING (public.is_admin()) WITH CHECK (public.is_admin());
DROP POLICY IF EXISTS teacher_students_self_or_admin ON public.teacher_students;
CREATE POLICY teacher_students_self_or_admin ON public.teacher_students FOR SELECT TO authenticated
USING (teacher_id = auth.uid() OR student_id = auth.uid() OR public.is_admin());
DROP POLICY IF EXISTS teacher_students_admin_write ON public.teacher_students;
CREATE POLICY teacher_students_admin_write ON public.teacher_students FOR ALL TO authenticated
USING (public.is_admin()) WITH CHECK (public.is_admin());

DROP POLICY IF EXISTS essays_teacher_read ON public.essay_submissions;
CREATE POLICY essays_teacher_read ON public.essay_submissions FOR SELECT TO authenticated
USING (public.is_admin() OR EXISTS (
  SELECT 1 FROM public.teacher_students ts WHERE ts.teacher_id = auth.uid() AND ts.student_id = essay_submissions.user_id AND ts.active
));
DROP POLICY IF EXISTS reviews_teacher_assigned ON public.essay_reviews;
CREATE POLICY reviews_teacher_assigned ON public.essay_reviews FOR SELECT TO authenticated
USING (public.is_admin() OR reviewer_id = auth.uid() OR EXISTS (
  SELECT 1 FROM public.essay_submissions e JOIN public.teacher_students ts ON ts.student_id=e.user_id
  WHERE e.id=essay_reviews.essay_id AND ts.teacher_id=auth.uid() AND ts.active
));
