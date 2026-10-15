from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class KnowledgeArea(Base):
    __tablename__ = "knowledge_areas"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    code = Column(String(20), unique=True)

    subjects = relationship("Subject", back_populates="knowledge_area")


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("knowledge_area_id", "name"),)

    id = Column(Integer, primary_key=True)
    knowledge_area_id = Column(Integer, ForeignKey("knowledge_areas.id"), nullable=False)
    name = Column(String(100), nullable=False)

    knowledge_area = relationship("KnowledgeArea", back_populates="subjects")
    topics = relationship("Topic", back_populates="subject")


class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("knowledge_area_id", "code"),)

    id = Column(Integer, primary_key=True)
    knowledge_area_id = Column(Integer, ForeignKey("knowledge_areas.id"), nullable=False)
    code = Column(String(10), nullable=False)
    description = Column(Text, nullable=False)


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("subject_id", "name"),)

    id = Column(Integer, primary_key=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    parent_topic_id = Column(Integer, ForeignKey("topics.id"))
    name = Column(String(200), nullable=False)
    description = Column(Text)

    subject = relationship("Subject", back_populates="topics")


class Exam(Base):
    __tablename__ = "exams"
    __table_args__ = (UniqueConstraint("year", "edition", "color", "day"),)

    id = Column(Integer, primary_key=True)
    year = Column(Integer, nullable=False)
    edition = Column(String(20), nullable=False, default="regular")
    color = Column(String(20), default="azul")
    day = Column(Integer)
    application_date = Column(Date)

    questions = relationship("Question", back_populates="exam")


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("exam_id", "number"),)

    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    number = Column(Integer, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"))
    skill_id = Column(Integer, ForeignKey("skills.id"))
    taxonomy_competency_id = Column(Integer, ForeignKey("competencies.id"))
    taxonomy_skill_id = Column(Integer, ForeignKey("skill_definitions.id"))
    source_text = Column(Text)
    statement_text = Column(Text, nullable=False)
    image_url = Column(Text)
    difficulty_estimate = Column(Numeric(4, 3))
    search_vector = Column(TSVECTOR)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    exam = relationship("Exam", back_populates="questions")
    alternatives = relationship("Alternative", back_populates="question")


class Alternative(Base):
    __tablename__ = "alternatives"
    __table_args__ = (UniqueConstraint("question_id", "letter"),)

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    letter = Column(String(1), nullable=False)
    text = Column(Text, nullable=False)
    is_correct = Column(Boolean, nullable=False, default=False)

    question = relationship("Question", back_populates="alternatives")


class QuestionTopic(Base):
    __tablename__ = "question_topics"

    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True)
    relevance = Column(Numeric(3, 2), default=1.0)


class TopicEdge(Base):
    __tablename__ = "topic_edges"
    __table_args__ = (
        UniqueConstraint("topic_a_id", "topic_b_id", "edge_type"),
        CheckConstraint("topic_a_id < topic_b_id"),
    )

    id = Column(Integer, primary_key=True)
    topic_a_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    topic_b_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    edge_type = Column(String(30), nullable=False, default="co_occurrence")
    weight = Column(Numeric(6, 3), nullable=False, default=1.0)


class TopicYearFrequency(Base):
    __tablename__ = "topic_year_frequency"
    __table_args__ = (UniqueConstraint("topic_id", "year"),)

    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    year = Column(Integer, nullable=False)
    question_count = Column(Integer, nullable=False, default=0)


class Institution(Base):
    __tablename__ = "institutions"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    acronym = Column(String(20))

    programs = relationship("Program", back_populates="institution")


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (UniqueConstraint("institution_id", "name"),)

    id = Column(Integer, primary_key=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)

    institution = relationship("Institution", back_populates="programs")
    weights = relationship("ProgramWeight", back_populates="program")


class ProgramWeight(Base):
    __tablename__ = "program_weights"
    __table_args__ = (UniqueConstraint("program_id", "knowledge_area_id", "source_year"),)

    id = Column(Integer, primary_key=True)
    program_id = Column(Integer, ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    knowledge_area_id = Column(Integer, ForeignKey("knowledge_areas.id"), nullable=False)
    weight = Column(Numeric(5, 2), nullable=False)
    source_year = Column(Integer)

    program = relationship("Program", back_populates="weights")

class TaxonomyVersion(Base):
    __tablename__ = "taxonomy_versions"

    id = Column(Integer, primary_key=True)
    code = Column(String(30), nullable=False, unique=True)
    name = Column(String(150), nullable=False)
    source_url = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Competency(Base):
    __tablename__ = "competencies"
    __table_args__ = (UniqueConstraint("taxonomy_version_id", "knowledge_area_id", "code"),)

    id = Column(Integer, primary_key=True)
    taxonomy_version_id = Column(Integer, ForeignKey("taxonomy_versions.id", ondelete="CASCADE"), nullable=False)
    knowledge_area_id = Column(Integer, ForeignKey("knowledge_areas.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(10), nullable=False)
    name = Column(Text, nullable=False)


class SkillDefinition(Base):
    __tablename__ = "skill_definitions"
    __table_args__ = (UniqueConstraint("competency_id", "code"),)

    id = Column(Integer, primary_key=True)
    competency_id = Column(Integer, ForeignKey("competencies.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(10), nullable=False)
    description = Column(Text)
    source_status = Column(String(30), nullable=False, default="official")


class KnowledgeObject(Base):
    __tablename__ = "knowledge_objects"
    __table_args__ = (UniqueConstraint("taxonomy_version_id", "knowledge_area_id", "name"),)

    id = Column(Integer, primary_key=True)
    taxonomy_version_id = Column(Integer, ForeignKey("taxonomy_versions.id", ondelete="CASCADE"), nullable=False)
    knowledge_area_id = Column(Integer, ForeignKey("knowledge_areas.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text)


class QuestionClassification(Base):
    __tablename__ = "question_classifications"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    taxonomy_version_id = Column(Integer, ForeignKey("taxonomy_versions.id", ondelete="RESTRICT"), nullable=False)
    predicted_area_id = Column(Integer, ForeignKey("knowledge_areas.id"))
    predicted_subject_id = Column(Integer, ForeignKey("subjects.id"))
    predicted_competency_id = Column(Integer, ForeignKey("competencies.id"))
    predicted_skill_id = Column(Integer, ForeignKey("skill_definitions.id"))
    confidence = Column(Numeric(5, 4), nullable=False, default=0)
    method = Column(String(40), nullable=False, default="heuristic")
    status = Column(String(30), nullable=False, default="candidate")
    evidence = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TopicPredictionResult(Base):
    __tablename__ = "topic_prediction_results"
    id = Column(BigInteger, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    program_id = Column(Integer, ForeignKey("programs.id", ondelete="SET NULL"))
    score = Column(Numeric(10, 6), nullable=False, default=0)
    probability = Column(Numeric(8, 6), nullable=False, default=0)
    rank = Column(Integer)
    model_version = Column(String(50), nullable=False, default="predictor-v1")
    factors = Column(Text, nullable=False, default="{}")
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    topic = relationship("Topic")
    explanations = relationship("TopicPredictionExplanation", back_populates="prediction", cascade="all, delete-orphan")


class TopicPredictionExplanation(Base):
    __tablename__ = "topic_prediction_explanations"
    id = Column(BigInteger, primary_key=True)
    prediction_id = Column(Integer, ForeignKey("topic_prediction_results.id", ondelete="CASCADE"), nullable=False)
    factor = Column(String(50), nullable=False)
    contribution = Column(Numeric(10, 6), nullable=False, default=0)
    explanation = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    prediction = relationship("TopicPredictionResult", back_populates="explanations")


class PredictionModelConfig(Base):
    __tablename__ = "prediction_model_configs"
    id = Column(BigInteger, primary_key=True)
    name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    recency_weight = Column(Numeric(8, 4), nullable=False, default=0.30)
    trend_weight = Column(Numeric(8, 4), nullable=False, default=0.25)
    frequency_weight = Column(Numeric(8, 4), nullable=False, default=0.25)
    graph_weight = Column(Numeric(8, 4), nullable=False, default=0.20)
    active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class PredictionRun(Base):
    __tablename__ = "prediction_runs"
    id = Column(BigInteger, primary_key=True)
    program_id = Column(Integer, ForeignKey("programs.id", ondelete="SET NULL"))
    model_config_id = Column(Integer, ForeignKey("prediction_model_configs.id", ondelete="SET NULL"))
    status = Column(String(20), nullable=False, default="completed")
    question_count = Column(Integer, nullable=False, default=0)
    topic_count = Column(Integer, nullable=False, default=0)
    model_version = Column(String(50), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)

class QuestionAttempt(Base):
    __tablename__ = 'question_attempts'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(UUID(as_uuid=False), nullable=False)
    question_id = Column(Integer, ForeignKey('questions.id', ondelete='CASCADE'), nullable=False)
    selected_letter = Column(String(1), nullable=False)
    is_correct = Column(Boolean, nullable=False, default=False)
    seconds_spent = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class StudentTopicPerformance(Base):
    __tablename__ = 'student_topic_performance'
    id = Column(BigInteger, primary_key=True)
    user_id = Column(UUID(as_uuid=False), nullable=False)
    topic_id = Column(Integer, ForeignKey('topics.id', ondelete='CASCADE'), nullable=False)
    attempt_count = Column(Integer, nullable=False, default=0)
    correct_count = Column(Integer, nullable=False, default=0)
    accuracy = Column(Numeric(6,5), nullable=False, default=0)
    last_attempt_at = Column(DateTime(timezone=True))
    topic = relationship('Topic')


class ProficiencyAssessment(Base):
    __tablename__ = "proficiency_assessments"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False, default="Teste de proficiência inicial")
    status = Column(String(20), nullable=False, default="draft")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    question_count = Column(Integer, nullable=False, default=0)

class ProficiencyAssessmentItem(Base):
    __tablename__ = "proficiency_assessment_items"
    id = Column(BigInteger, primary_key=True)
    assessment_id = Column(BigInteger, ForeignKey("proficiency_assessments.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, nullable=False)
    selected_letter = Column(String(1))
    is_correct = Column(Boolean)
    answered_at = Column(DateTime(timezone=True))

class ProficiencyResult(Base):
    __tablename__ = "proficiency_results"
    id = Column(BigInteger, primary_key=True)
    assessment_id = Column(BigInteger, ForeignKey("proficiency_assessments.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    knowledge_area_id = Column(Integer, ForeignKey("knowledge_areas.id", ondelete="SET NULL"))
    theta = Column(Numeric(10,5))
    estimated_score = Column(Numeric(8,2))
    item_count = Column(Integer, nullable=False, default=0)
    accuracy = Column(Numeric(8,5))
    model_version = Column(String(50), nullable=False, default="tri-estimate-v1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class StudyPriority(Base):
    __tablename__ = "study_priorities"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    priority_score = Column(Numeric(10,5), nullable=False, default=0)
    priority_level = Column(String(20), nullable=False, default="medium")
    rationale = Column(Text)
    completed = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    topic = relationship("Topic")

class Simulation(Base):
    __tablename__ = "simulations"
    id = Column(BigInteger, primary_key=True)
    cycle_year = Column(Integer, nullable=False)
    sequence = Column(Integer, nullable=False)
    title = Column(Text, nullable=False)
    scheduled_at = Column(DateTime(timezone=True))
    question_count = Column(Integer, nullable=False, default=180)
    status = Column(String(20), nullable=False, default="scheduled")


class SimulationAttempt(Base):
    __tablename__ = "simulation_attempts"
    id = Column(BigInteger, primary_key=True)
    simulation_id = Column(BigInteger, ForeignKey("simulations.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, nullable=False)
    user_id = Column(UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"))
    selected_letter = Column(String(1))
    is_correct = Column(Boolean)
    seconds_spent = Column(Integer)
    answered_at = Column(DateTime(timezone=True))


class EssaySubmission(Base):
    __tablename__ = "essay_submissions"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    content_text = Column(Text, nullable=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String(20), nullable=False, default="pending")
    review = relationship("EssayReview", back_populates="essay", uselist=False, cascade="all, delete-orphan")


class EssayReview(Base):
    __tablename__ = "essay_reviews"
    id = Column(BigInteger, primary_key=True)
    essay_id = Column(BigInteger, ForeignKey("essay_submissions.id", ondelete="CASCADE"), unique=True, nullable=False)
    reviewer_id = Column(UUID(as_uuid=False), ForeignKey("auth.users.id", ondelete="SET NULL"))
    score = Column(Numeric(6,2), nullable=False, default=0)
    competency_1 = Column(Numeric(6,2), nullable=False, default=0)
    competency_2 = Column(Numeric(6,2), nullable=False, default=0)
    competency_3 = Column(Numeric(6,2), nullable=False, default=0)
    competency_4 = Column(Numeric(6,2), nullable=False, default=0)
    competency_5 = Column(Numeric(6,2), nullable=False, default=0)
    strengths = Column(Text)
    improvements = Column(Text)
    feedback = Column(Text)
    reviewed_at = Column(DateTime(timezone=True))
    essay = relationship("EssaySubmission", back_populates="review")
